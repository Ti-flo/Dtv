"""
HDV (Hôtel de Vente) price collection.

Confirmed from static analysis of script.js (Dofus Touch 3.11.0).

HDV message flow:
  Send: NpcGenericActionRequestMessage({npcId:0, npcActionId:6, npcMapId:<mapId>})
  Recv: ExchangeStartedBidBuyerMessage  → HDV open, contains buyerDescriptor.quantities
  Send: ExchangeBidHouseTypeMessage({type: <item_gid>})   ← one per item type
  Recv: ExchangeTypesItemsExchangerDescriptionForUserMessage → all current offers
  Send: LeaveDialogRequestMessage
  Recv: ExchangeLeaveMessage

ExchangeTypesItemsExchangerDescriptionForUserMessage format (confirmed script.js):
  {
    "itemTypeDescriptions": [
      {
        "objectUID":     <int>,           unique offer ID
        "prices":        [p1, p10, p100], total price for 1 / 10 / 100 units (0 = no offer)
        "effects":       [...],
        "tutorialPrice": <bool>
      }, ...
    ]
  }

Note: objectGID is NOT in the server response — it equals the type we requested.

CSV output (one row per item type per session):
  timestamp, session, item_gid, hdv_type,
  prix_x1, prix_x10, prix_x100,
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

# Quantity tiers — matches buyerDescriptor.quantities from ExchangeStartedBidBuyerMessage
# Standard Dofus Touch: [1, 10, 100]
QUANTITY_TIERS = [1, 10, 100]


def _get_session_name() -> str:
    hour = datetime.now().hour
    closest = min(SESSION_NAMES.keys(), key=lambda h: abs(h - hour))
    return SESSION_NAMES[closest]


class HdvCollector:
    """
    Collects prices from HDV using an active game session.

    Usage:
        collector = HdvCollector(session, account="account@gmail.com")
        collector.open_hdv()           # sends NpcGenericActionRequestMessage
        collector.collect_type(12345)  # item type GID
        collector.close_hdv()
        collector.save_to_csv()
    """

    def __init__(self, session: DofusTouchSession, account: str = "unknown"):
        self._session = session
        self._account = account
        self._records: list[dict] = []
        self._hdv_ready = threading.Event()
        self._collection_done = threading.Event()
        self._pending_type_gid: Optional[int] = None
        self._quantities: list[int] = QUANTITY_TIERS
        self._setup_handlers()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def open_hdv(self, map_id: Optional[int] = None, timeout: float = 15.0) -> bool:
        """
        Open the HDV in buy mode.

        map_id: player's current map ID (from session.map_id).
                Falls back to session.map_id, then -1 if unknown.
        Returns True if HDV opened within timeout.
        """
        self._hdv_ready.clear()
        npc_map_id = map_id if map_id is not None else self._session.map_id
        log.info("Opening HDV (npcMapId=%d)...", npc_map_id)
        self._session.send_message("NpcGenericActionRequestMessage", {
            "npcId": 0,
            "npcActionId": 6,       # 6 = buy mode, confirmed openBidHouse() script.js
            "npcMapId": npc_map_id,
        })
        return self._hdv_ready.wait(timeout)

    def collect_type(self, type_gid: int, timeout: float = 30.0) -> list[dict]:
        """
        Request and collect all current offers for one item type GID.

        Args:
            type_gid: The generic item type ID in the HDV.
            timeout:  Max seconds to wait for the server response.

        Returns:
            Records collected for this type only.
        """
        self._collection_done.clear()
        self._pending_type_gid = type_gid
        batch_start = len(self._records)

        log.info("Requesting offers for item type GID=%d", type_gid)
        self._session.send_message("ExchangeBidHouseTypeMessage", {"type": type_gid})

        if not self._collection_done.wait(timeout):
            log.warning("Timeout waiting for type GID=%d", type_gid)

        return list(self._records[batch_start:])

    def close_hdv(self):
        """Send LeaveDialogRequestMessage to close the HDV."""
        self._session.send_message("LeaveDialogRequestMessage", {})

    def save_to_csv(self, output_dir: Path = None) -> Path:
        """Write collected records to CSV. Returns the output file path."""
        out_dir = output_dir or DATA_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        session_name = _get_session_name()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = out_dir / f"hdv_{session_name}_{timestamp}.csv"

        fieldnames = [
            "timestamp", "session", "item_gid", "hdv_type",
            "prix_x1", "prix_x10", "prix_x100",
            "nb_offres", "all_prices_x1", "compte_collecteur",
        ]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
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
                log.info("HDV opened. Quantity tiers: %s", quantities)
            else:
                log.info("HDV opened (no quantities in descriptor, using default %s)",
                         self._quantities)
            self._hdv_ready.set()

        @session.on("ExchangeTypesItemsExchangerDescriptionForUserMessage")
        def on_offers(msg):
            offers = msg.get("itemTypeDescriptions", [])
            type_gid = self._pending_type_gid
            log.info("Received %d offers for GID=%s", len(offers), type_gid)

            if type_gid is not None:
                record = _aggregate_offers(
                    offers, type_gid, self._quantities,
                    datetime.now().isoformat(), _get_session_name(), self._account,
                )
                self._records.append(record)

            self._collection_done.set()

        @session.on("ExchangeLeaveMessage")
        def on_hdv_closed(msg):
            log.info("HDV closed")


def _aggregate_offers(
    offers: list[dict],
    type_gid: int,
    quantities: list[int],
    timestamp: str,
    session: str,
    account: str,
) -> dict:
    """
    Aggregate all offers for one item type into a single CSV row.

    Each offer: { objectUID, prices: [p_qty0, p_qty1, p_qty2], effects, tutorialPrice }
    prices[i] = total price for quantities[i] units. 0 means no offer at that tier.
    """
    min_prices = [0] * len(quantities)
    all_x1: list[int] = []

    for offer in offers:
        prices = offer.get("prices", [])
        for i, qty in enumerate(quantities):
            p = prices[i] if i < len(prices) else 0
            if p > 0:
                if min_prices[i] == 0 or p < min_prices[i]:
                    min_prices[i] = p
                if qty == 1:
                    all_x1.append(p)

    while len(min_prices) < 3:
        min_prices.append(0)

    return {
        "timestamp": timestamp,
        "session": session,
        "item_gid": type_gid,
        "hdv_type": type_gid,
        "prix_x1": min_prices[0],
        "prix_x10": min_prices[1],
        "prix_x100": min_prices[2],
        "nb_offres": len(offers),
        "all_prices_x1": "|".join(str(p) for p in sorted(all_x1)),
        "compte_collecteur": account,
    }
