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

log = logging.getLogger(__name__)


class PassiveCollector:
    """
    Feed it WebSocket frames via handle_frame(); it writes CSVs as data arrives.

    Usage:
        pc = PassiveCollector(account="main")
        cdp.on_frame(pc.handle_frame)   # direction, payload, ws_url
        cdp.run_forever()
    """

    def __init__(self, account: str = "main", data_dir: Optional[Path] = None):
        self._account = account
        self._data_dir = data_dir or DATA_DIR
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # HDV state, learned passively as the player interacts.
        self._quantities: list[int] = list(QUANTITY_TIERS)
        self._economics: dict = {}
        self._current_type: Optional[int] = None        # last ExchangeBidHouseTypeMessage
        self._pending_gids: deque[int] = deque()         # GIDs awaiting a price reply

        # Stats for the operator.
        self.items_captured = 0
        self.snapshots_captured = 0

        # One HDV CSV per day, appended to. Path + writer created lazily.
        self._hdv_csv_path: Optional[Path] = None
        self._lock = threading.Lock()

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

        if direction == "sent":
            self._on_sent(msg)
        else:
            self._on_recv(msg)

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

        self._append_hdv_row(record)
        self.items_captured += 1
        log.info("OK recorded item GID=%s (%d offers) - prix_x1=%s",
                 gid, len(offers), record.get("prix_x1"))

    # ------------------------------------------------------------------ #
    # CSV writers                                                        #
    # ------------------------------------------------------------------ #

    def _hdv_fieldnames(self) -> list[str]:
        price_cols = [f"prix_x{q}" for q in self._quantities]
        return (
            ["timestamp", "session", "item_gid", "hdv_type"]
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
            writer.writerow(["timestamp", "item_gid", "avg_price_x1", "compte_collecteur"])
            for gid, price in zip(ids, prices):
                writer.writerow([now, gid, price, self._account])
        self.snapshots_captured += 1
        log.info("OK average-price snapshot saved: %d items -> %s", len(ids), path.name)
