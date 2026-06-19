"""
HDV (Hôtel de Vente) price collection.

✅ Flow confirmed from live capture (HAR, session 4). It is a TWO-STEP flow:

  Send: NpcGenericActionRequestMessage({npcId:0, npcActionId:6, npcMapId:<real mapId>})
  Recv: ExchangeStartedBidBuyerMessage → buyerDescriptor.{quantities, types}

  For each type T in buyerDescriptor.types:
    Send: ExchangeBidHouseTypeMessage({type: T})
    Recv: ExchangeTypesExchangerDescriptionForUserMessage({typeDescription: [GID, ...]})
          ← list of object GIDs that currently have offers in this type

    For each object GID in typeDescription:
      Send: ExchangeBidHouseListMessage({id: GID})
      Recv: ExchangeTypesItemsExchangerDescriptionForUserMessage({itemTypeDescriptions: [...]})
            ← the actual offers (prices) for that object

  Send: LeaveDialogRequestMessage
  Recv: ExchangeLeaveMessage

CAUTION — message name collision (both start with "ExchangeTypes..."):
  - ExchangeTypesExchangerDescriptionForUserMessage      (NO "Items") = list of GIDs
  - ExchangeTypesItemsExchangerDescriptionForUserMessage (WITH "Items") = prices

ExchangeTypesItemsExchangerDescriptionForUserMessage format (live):
  {
    "itemTypeDescriptions": [
      {
        "_type":     "BidExchangerObjectInfo",
        "objectUID": 1221817,
        "effects":   [...],
        "prices":    [14, 280, 2978, 0]   # indexed on buyerDescriptor.quantities (0 = no offer)
      }, ...
    ]
  }

CSV output (one row per object GID per session):
  timestamp, session, item_gid, hdv_type,
  prix_x1, prix_x10, prix_x100, prix_x1000,
  nb_offres, all_prices_x1, compte_collecteur
"""
import csv
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from .connection import DofusTouchSession

log = logging.getLogger(__name__)

SESSION_NAMES = {
    7: "morning",
    12: "noon",
    18: "evening",
    22: "night",
    2: "late_night",
}

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "raw"

# Default quantity tiers — overwritten by buyerDescriptor.quantities at HDV open.
# Live capture confirmed [1, 10, 100, 1000] (4 tiers).
QUANTITY_TIERS = [1, 10, 100, 1000]


def _get_session_name() -> str:
    hour = datetime.now().hour
    closest = min(SESSION_NAMES.keys(), key=lambda h: abs(h - hour))
    return SESSION_NAMES[closest]


class HdvCollector:
    """
    Collects prices from HDV using an active game session.

    Two-step collection per item type:
      collect_type(T) → asks for the GIDs in type T, then asks each GID for prices.

    Usage:
        collector = HdvCollector(session, account="account@gmail.com")
        collector.open_hdv()
        collector.collect_type(33)     # an item type GID from buyerDescriptor.types
        collector.close_hdv()
        collector.save_to_csv()
    """

    def __init__(self, session: DofusTouchSession, account: str = "unknown"):
        self._session = session
        self._account = account
        self._records: list[dict] = []
        self._quantities: list[int] = QUANTITY_TIERS
        self._available_types: list[int] = []

        self._hdv_ready = threading.Event()
        # Step 1 result: list of GIDs for the type currently being requested
        self._type_gids_ready = threading.Event()
        self._current_type_gids: list[int] = []
        # Step 2 result: prices for a single GID
        self._offers_ready = threading.Event()
        self._pending_gid: Optional[int] = None

        self._setup_handlers()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    @property
    def available_types(self) -> list[int]:
        """Item type GIDs advertised by the server (from buyerDescriptor.types)."""
        return list(self._available_types)

    def open_hdv(self, map_id: Optional[int] = None, timeout: float = 15.0) -> bool:
        """
        Open the HDV in buy mode.

        map_id: player's current map ID. Falls back to session.map_id.
                Must be the REAL mapId (from CurrentMapMessage), not -1.
        """
        self._hdv_ready.clear()
        npc_map_id = map_id if map_id is not None else self._session.map_id
        log.info("Opening HDV (npcMapId=%d)...", npc_map_id)
        self._session.send_message("NpcGenericActionRequestMessage", {
            "npcId": 0,
            "npcActionId": 6,       # 6 = buy mode (confirmed openBidHouse() script.js + live)
            "npcMapId": npc_map_id,
        })
        return self._hdv_ready.wait(timeout)

    def collect_type(self, type_gid: int, timeout: float = 30.0) -> list[dict]:
        """
        Collect all offers for one item type GID (two-step).

        Step 1: ExchangeBidHouseTypeMessage{type} → list of object GIDs
        Step 2: for each GID, ExchangeBidHouseListMessage{id} → prices

        Returns the records collected for this type.
        """
        batch_start = len(self._records)

        # --- Step 1: get the GIDs in this type ---
        self._type_gids_ready.clear()
        self._current_type_gids = []
        log.info("Requesting GID list for type=%d", type_gid)
        self._session.send_message("ExchangeBidHouseTypeMessage", {"type": type_gid})

        if not self._type_gids_ready.wait(timeout):
            log.warning("Timeout waiting for GID list of type=%d", type_gid)
            return []

        gids = list(self._current_type_gids)
        log.info("Type %d → %d object GIDs", type_gid, len(gids))

        # --- Step 2: get prices for each GID ---
        from .timing import human_delay
        for gid in gids:
            self._offers_ready.clear()
            self._pending_gid = gid
            self._session.send_message("ExchangeBidHouseListMessage", {"id": gid})
            if not self._offers_ready.wait(timeout):
                log.warning("Timeout waiting for offers of GID=%d", gid)
            human_delay(0.3, 0.9)  # small jitter between item requests

        return list(self._records[batch_start:])

    def collect_all(self, timeout: float = 30.0) -> int:
        """Collect every type advertised in buyerDescriptor.types. Returns total records."""
        from .timing import human_delay
        total = 0
        for t in self._available_types:
            total += len(self.collect_type(t, timeout))
            human_delay(2.0, 5.0)  # human-like pause between categories
        return total

    def close_hdv(self):
        """Send LeaveDialogRequestMessage to close the HDV."""
        self._session.send_message("LeaveDialogRequestMessage", None)

    def save_to_csv(self, output_dir: Path = None) -> Path:
        """Write collected records to CSV. Returns the output file path."""
        out_dir = output_dir or DATA_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        session_name = _get_session_name()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = out_dir / f"hdv_{session_name}_{timestamp}.csv"

        # Price columns are dynamic: one per quantity tier (x1/x10/x100/x1000)
        price_cols = [f"prix_x{q}" for q in self._quantities]
        fieldnames = (
            ["timestamp", "session", "item_gid", "hdv_type"]
            + price_cols
            + ["nb_offres", "all_prices_x1", "compte_collecteur"]
        )
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(self._records)

        log.info("Saved %d records to %s", len(self._records), path)
        return path

    # ------------------------------------------------------------------ #
    # Internal handlers                                                   #
    # ------------------------------------------------------------------ #

    def _setup_handlers(self):
        session = self._session

        @session.on("ExchangeStartedBidBuyerMessage")
        def on_hdv_opened(msg):
            descriptor = msg.get("buyerDescriptor") or {}
            quantities = descriptor.get("quantities")
            if quantities:
                self._quantities = quantities
            self._available_types = descriptor.get("types", []) or []
            log.info("HDV opened. quantities=%s, %d types available",
                     self._quantities, len(self._available_types))
            self._hdv_ready.set()

        # Step 1 response: list of object GIDs for the requested type (NO "Items")
        @session.on("ExchangeTypesExchangerDescriptionForUserMessage")
        def on_type_gids(msg):
            self._current_type_gids = msg.get("typeDescription", []) or []
            self._type_gids_ready.set()

        # Step 2 response: actual offers/prices for one object (WITH "Items")
        @session.on("ExchangeTypesItemsExchangerDescriptionForUserMessage")
        def on_offers(msg):
            offers = msg.get("itemTypeDescriptions", []) or []
            gid = self._pending_gid
            log.debug("Received %d offers for GID=%s", len(offers), gid)
            if gid is not None:
                record = _aggregate_offers(
                    offers, gid, self._quantities,
                    datetime.now().isoformat(), _get_session_name(), self._account,
                )
                self._records.append(record)
            self._offers_ready.set()

        @session.on("ExchangeLeaveMessage")
        def on_hdv_closed(msg):
            log.info("HDV closed")


def _aggregate_offers(
    offers: list[dict],
    gid: int,
    quantities: list[int],
    timestamp: str,
    session: str,
    account: str,
) -> dict:
    """
    Aggregate all offers for one object GID into a single CSV row.

    Each offer: { objectUID, effects, prices: [p_qty0, p_qty1, ...] }
    prices[i] = total price for quantities[i] units. 0 means no offer at that tier.
    """
    min_prices: dict[int, int] = {qty: 0 for qty in quantities}
    all_x1: list[int] = []

    for offer in offers:
        prices = offer.get("prices", [])
        for i, qty in enumerate(quantities):
            p = prices[i] if i < len(prices) else 0
            if p > 0:
                if min_prices[qty] == 0 or p < min_prices[qty]:
                    min_prices[qty] = p
                if qty == 1:
                    all_x1.append(p)

    row: dict = {
        "timestamp": timestamp,
        "session": session,
        "item_gid": gid,
        "hdv_type": gid,
        "nb_offres": len(offers),
        "all_prices_x1": "|".join(str(p) for p in sorted(all_x1)),
        "compte_collecteur": account,
    }
    for qty, price in min_prices.items():
        row[f"prix_x{qty}"] = price
    return row
