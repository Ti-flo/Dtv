"""
Passive HDV / average-price collector driven by observed WebSocket frames.

Unlike HdvCollector (which actively SENDS requests and waits), this consumes
frames captured from the REAL client via CDP (see cdp_client.py). The human
plays normally; every item they open in the HDV and every average-price snapshot
sent at login is recorded.

Correlation model (HDV is request→response, the response has no GID of its own):
  Client SENDS  ExchangeBidHouseListMessage{id: GID}    ← the item you clicked
  Server REPLIES ExchangeTypesItemsExchangerDescriptionForUserMessage{prices}
We keep a FIFO of GIDs from the sent requests and pop the oldest when a price
reply arrives. The game answers in order on a single socket, so FIFO is correct.

Durability: HDV rows are appended to a per-day CSV as they arrive (a play session
can last hours — we never want to lose what's already captured). Average-price
snapshots are written as a fresh file each time one is seen.

Reuses hdv._aggregate_offers so the HDV row format is identical to the bot path.
"""
import csv
import json
import logging
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

from .hdv import _aggregate_offers, _get_session_name, QUANTITY_TIERS, DATA_DIR
from .. import config

log = logging.getLogger(__name__)

# Dossier des catalogues résolu par la config centrale (DTV_SCRAPER_DIR / SDK / repo).
_SCRAPER_DIR = config.scraper_dir()
_CATALOG_FILES = list(config.CATALOG_FILES.values())


def _load_name_map(scraper_dir: Path = _SCRAPER_DIR) -> dict[int, str]:
    """GID -> Nom_FR depuis les 3 catalogues scrapers. Silencieux si absent."""
    names: dict[int, str] = {}
    for fname in _CATALOG_FILES:
        path = scraper_dir / fname
        if not path.exists():
            continue
        try:
            with open(path, encoding="utf-8") as f:
                items = json.load(f)
            for it in items:
                try:
                    gid = int(float(it.get("GID") or 0))
                except (ValueError, TypeError):
                    continue
                if gid and gid not in names:
                    names[gid] = str(it.get("Nom_FR") or "")
        except Exception as e:
            log.debug("Catalogue %s non chargeable : %s", fname, e)
    log.info("Noms charges : %d items depuis les catalogues", len(names))
    return names


_RUNE_GIDS_PATH = config.rune_gids_path()


def _load_rune_gid_to_code(path: Path = _RUNE_GIDS_PATH) -> dict[int, str]:
    """GID de rune -> code rune, en inversant rune_gids.json (code -> gid)."""
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            code2gid = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    out = {}
    for code, gid in code2gid.items():
        if gid is not None:
            try:
                out[int(gid)] = code
            except (ValueError, TypeError):
                continue
    return out


class PassiveCollector:
    """
    Feed it WebSocket frames via handle_frame(); it writes CSVs as data arrives.

    Usage:
        pc = PassiveCollector(account="main")
        cdp.on_frame(pc.handle_frame)   # direction, payload, ws_url
        cdp.run_forever()
    """

    def __init__(self, account: str = "main", data_dir: Optional[Path] = None,
                 scraper_dir: Optional[Path] = None, dump_raw: bool = False):
        self._account = account
        self._data_dir = data_dir or DATA_DIR
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._names = _load_name_map(scraper_dir or _SCRAPER_DIR)
        self._rune_codes = _load_rune_gid_to_code()   # GID rune -> code (vi, fo, …)

        # HDV state, learned passively as the player interacts.
        self._quantities: list[int] = list(QUANTITY_TIERS)
        self._economics: dict = {}
        self._current_type: Optional[int] = None        # last ExchangeBidHouseTypeMessage
        self._pending_gids: deque[int] = deque()         # GIDs awaiting a price reply

        # Stats for the operator.
        self.items_captured = 0
        self.snapshots_captured = 0
        self.brisages_captured = 0

        # One HDV CSV per day, appended to. Path + writer created lazily.
        self._hdv_csv_path: Optional[Path] = None
        self._lock = threading.Lock()

        # Optional raw frame dump: writes EVERY decoded game message to a JSONL.
        # Used to reverse-engineer unknown flows (ex : brisage / Concasseur) —
        # on rejoue le dump ensuite pour identifier le message + ses champs.
        self._dump_raw = dump_raw
        self._raw_path: Optional[Path] = None
        self._raw_seen_types: set = set()

    # ------------------------------------------------------------------ #
    # Frame entry point                                                  #
    # ------------------------------------------------------------------ #

    def handle_frame(self, direction: str, payload: str, ws_url: str = ""):
        """Route one raw Primus frame. Safe to call from the CDP recv thread."""
        try:
            msg = json.loads(payload)
        except json.JSONDecodeError:
            return
        # Primus control frames arrive as bare strings ("primus::ping::…") — skip.
        if not isinstance(msg, dict):
            return

        if self._dump_raw:
            self._dump_frame(direction, msg)

        if direction == "sent":
            self._on_sent(msg)
        else:
            self._on_recv(msg)

    def _dump_frame(self, direction: str, msg: dict):
        """Append one decoded game message to the daily raw JSONL (debug/RE)."""
        # Identifie le type : envoi = {call:sendMessage,data:{type}}, réception = {_messageType}
        if direction == "sent" and msg.get("call") == "sendMessage":
            mtype = (msg.get("data") or {}).get("type")
        else:
            mtype = msg.get("_messageType")
        day = datetime.now().strftime("%Y%m%d")
        path = self._data_dir / f"ws_raw_{day}.jsonl"
        with self._lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"dir": direction, "type": mtype, "msg": msg},
                                   ensure_ascii=False) + "\n")
            self._raw_path = path
            if mtype and mtype not in self._raw_seen_types:
                self._raw_seen_types.add(mtype)
                log.info("RAW nouveau message [%s] %s", direction, mtype)

    # ------------------------------------------------------------------ #
    # Outgoing frames (what the player asked for)                        #
    # ------------------------------------------------------------------ #

    def _on_sent(self, frame: dict):
        # Game messages are wrapped: {"call":"sendMessage","data":{"type",[ "data"]}}
        if frame.get("call") != "sendMessage":
            return
        inner = frame.get("data") or {}
        mtype = inner.get("type")
        data = inner.get("data") or {}

        if mtype == "ExchangeBidHouseTypeMessage":
            # Player selected a category tab — remember it to label the rows.
            self._current_type = data.get("type")
        elif mtype == "ExchangeBidHouseListMessage":
            # Player clicked an item → the client asks for its offers. Queue the GID.
            gid = data.get("id")
            if gid is not None:
                with self._lock:
                    self._pending_gids.append(gid)
                log.info(">> you opened item GID=%s (type=%s)", gid, self._current_type)

    # ------------------------------------------------------------------ #
    # Incoming frames (the data)                                         #
    # ------------------------------------------------------------------ #

    def _on_recv(self, msg: dict):
        mtype = msg.get("_messageType")
        if not mtype:
            return

        if mtype == "ObjectAveragePricesMessage":
            self._save_avg_snapshot(msg)

        elif mtype == "ExchangeStartedBidBuyerMessage":
            descriptor = msg.get("buyerDescriptor") or {}
            quantities = descriptor.get("quantities")
            if quantities:
                self._quantities = quantities
            self._economics = {
                k: descriptor.get(k)
                for k in ("taxPercentage", "maxItemLevel", "maxItemPerAccount", "unsoldDelay")
                if descriptor.get(k) is not None
            }
            log.info("HDV opened (passive). quantities=%s economics=%s",
                     self._quantities, self._economics)

        elif mtype == "ExchangeTypesItemsExchangerDescriptionForUserMessage":
            self._record_item_offers(msg)

        elif mtype == "ExchangeCraftResultRunicRecyclingMessage":
            # Brisage : LE message résultat. frequencyBonus = coefficient réel,
            # resultObjects = runes obtenues, objectGID = item brisé.
            self._record_brisage(msg)

        elif mtype == "TextInformationMessage":
            # Journal comptable : ventes (msgId 65 en jeu, 73 hors jeu) + achats HDV (252).
            self._record_transaction(msg)

        elif mtype == "ExchangeLeaveMessage":
            log.debug("HDV closed (passive)")

    def _record_item_offers(self, msg: dict):
        offers = msg.get("itemTypeDescriptions", []) or []
        with self._lock:
            gid = self._pending_gids.popleft() if self._pending_gids else None
        if gid is None:
            # A price reply with no matching request we observed (we attached
            # mid-interaction). Record it without a GID rather than dropping it.
            log.debug("Offers received with no pending GID (attached mid-session?)")

        record = _aggregate_offers(
            offers,
            gid if gid is not None else -1,
            self._quantities,
            datetime.now().isoformat(),
            _get_session_name(),
            self._account,
        )
        # hdv_type defaults to the GID inside _aggregate_offers; prefer the real
        # category the player was browsing when we know it.
        if self._current_type is not None:
            record["hdv_type"] = self._current_type
        record["nom"] = self._names.get(gid, "") if gid is not None else ""

        self._append_hdv_row(record)
        self.items_captured += 1
        log.info("OK recorded item GID=%s (%d offers) - prix_x1=%s",
                 gid, len(offers), record.get("prix_x1"))

    def _record_brisage(self, msg: dict):
        """
        Auto-collecte du brisage depuis ExchangeCraftResultRunicRecyclingMessage.

        Pour chaque item brisé :
          - objectGID      = item brisé
          - frequencyBonus = coefficient de brisage RÉEL (en %, ex 8) au moment du cast
          - resultObjects  = runes obtenues (liste d'ObjectItem : objectGID rune + quantity)

        Écrit dans data/raw/brisage_observations.csv (colonnes GID, coefficient_reel,
        dernier_brisage compatibles avec brisage.py --observations ; + runes_obtenues
        et nom pour valider la formule). resultObjects vide = aucune rune (coeff bas).
        """
        results = msg.get("recyclingResults") or []
        if not results:
            return
        day = datetime.now().strftime("%Y-%m-%d")
        ts = datetime.now().isoformat()
        for r in results:
            gid = r.get("objectGID")
            coeff = r.get("frequencyBonus")
            # Runes obtenues : code rune (via rune_gids) × quantité ; sinon GID brut.
            runes = []
            for ro in r.get("resultObjects") or []:
                rgid = ro.get("objectGID")
                qty = ro.get("quantity", 1)
                code = self._rune_codes.get(rgid, f"gid{rgid}")
                runes.append(f"{code}×{qty}")
            runes_str = ", ".join(runes)
            row = {
                "GID": gid,
                "coefficient_reel": coeff,
                "dernier_brisage": day,
                "runes_obtenues": runes_str,
                "nom": self._names.get(gid, ""),
                "timestamp": ts,
                "compte_collecteur": self._account,
            }
            self._append_brisage_row(row)
            self.brisages_captured += 1
            log.info("BRISAGE GID=%s coeff=%s%% runes=[%s] (%s)",
                     gid, coeff, runes_str or "aucune", row["nom"])

    def _record_transaction(self, msg: dict):
        """
        Journal comptable des transactions HDV depuis TextInformationMessage.

        msgId 65  : vente en jeu         params=[kamas, gid, gid, qty]
        msgId 73  : vente hors jeu       params=[kamas, gid, gid, qty]
        msgId 252 : achat HDV            params=[gid, uid, qty, kamas_total]

        Template Dofus (%1 = params[0], %2 = params[1], …) :
          65/73 : "Banque : + %1 Kamas (vente de %4 $item%3[hors jeu].)"
          252   : "%3 x {item,%1,%2} (%4 kamas)"
        """
        msg_id = msg.get("msgId")
        if msg_id not in (65, 73, 252):
            return
        params = msg.get("parameters") or []
        try:
            if msg_id in (65, 73):
                kamas_total = int(params[0])
                gid = int(params[2])
                qty = int(params[3])
                tx_type = "vente" if msg_id == 65 else "vente_hors_jeu"
            else:  # 252 = achat
                gid = int(params[0])
                qty = int(params[2])
                kamas_total = int(params[3])
                tx_type = "achat"
        except (IndexError, ValueError):
            return

        nom = self._names.get(gid, "")
        kamas_unitaire = round(kamas_total / qty, 2) if qty else 0
        row = {
            "timestamp": datetime.now().isoformat(),
            "type": tx_type,
            "gid": gid,
            "nom": nom,
            "quantite": qty,
            "kamas_total": kamas_total,
            "kamas_unitaire": kamas_unitaire,
            "compte_collecteur": self._account,
        }
        self._append_transaction_row(row)
        log.info("TX %s GID=%s (%s) qty=%s kamas=%s", tx_type, gid, nom or "?", qty, kamas_total)

    def _append_transaction_row(self, row: dict):
        path = self._data_dir / "transactions_observations.csv"
        fields = ["timestamp", "type", "gid", "nom", "quantite",
                  "kamas_total", "kamas_unitaire", "compte_collecteur"]
        is_new = not path.exists()
        with self._lock:
            with open(path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
                if is_new:
                    writer.writeheader()
                writer.writerow(row)

    def _append_brisage_row(self, row: dict):
        """Append une observation de brisage (header écrit une fois)."""
        path = self._data_dir / "brisage_observations.csv"
        fields = ["GID", "coefficient_reel", "dernier_brisage", "runes_obtenues",
                  "nom", "timestamp", "compte_collecteur"]
        is_new = not path.exists()
        with self._lock:
            with open(path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
                if is_new:
                    writer.writeheader()
                writer.writerow(row)

    # ------------------------------------------------------------------ #
    # CSV writers                                                        #
    # ------------------------------------------------------------------ #

    def _hdv_fieldnames(self) -> list[str]:
        price_cols = [f"prix_x{q}" for q in self._quantities]
        return (
            ["timestamp", "session", "item_gid", "nom", "hdv_type"]
            + price_cols
            + ["nb_offres", "all_prices_x1", "compte_collecteur"]
        )

    def _append_hdv_row(self, record: dict):
        """Append one item row to the per-day HDV CSV (header written once)."""
        day = datetime.now().strftime("%Y%m%d")
        path = self._data_dir / f"hdv_passive_{day}.csv"
        is_new = not path.exists()
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self._hdv_fieldnames(), extrasaction="ignore")
            if is_new:
                writer.writeheader()
            writer.writerow(record)
        self._hdv_csv_path = path

    def _save_avg_snapshot(self, msg: dict):
        """Write a fresh average-price snapshot CSV (one per login)."""
        ids = msg.get("ids", []) or []
        prices = msg.get("avgPrices", []) or []
        if len(ids) != len(prices):
            log.warning("avg snapshot ids/prices mismatch: %d vs %d", len(ids), len(prices))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self._data_dir / f"avgprices_{timestamp}.csv"
        now = datetime.now().isoformat()
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "item_gid", "nom", "avg_price_x1", "compte_collecteur"])
            for gid, price in zip(ids, prices):
                writer.writerow([now, gid, self._names.get(gid, ""), price, self._account])
        self.snapshots_captured += 1
        log.info("OK average-price snapshot saved: %d items -> %s", len(ids), path.name)
