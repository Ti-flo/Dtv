"""
HDV (Hôtel de Vente) price collection.

Sends ExchangePlayerRequestMessage to open an HDV, then collects
ExchangeTypesItemsExchangerDescriptionForUserMessage responses.

HDV message flow (confirmed from script.js):
  Send: ExchangePlayerRequestMessage  → open an HDV NPC
  Recv: ExchangeStartedWithStorageMessage → HDV opened
  Recv: ExchangeTypesItemsExchangerDescriptionForUserMessage → item descriptions + prices
  Send: ExchangeTypeItemsExchangerDescriptionForUserMessage (for each category)
  Recv: ExchangeTypesItemsExchangerDescriptionForUserMessage (with prices)
  Send: LeaveDialogRequestMessage → close HDV

CSV output format:
  timestamp, session, item_id, item_name, hdv_category,
  prix_x1, prix_x10, prix_x100, prix_x1000, nb_offres, liste_prix, compte_collecteur
"""
import csv
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from .connection import DofusTouchSession

log = logging.getLogger(__name__)

# Sessions are named by time of day (from the project spec)
SESSION_NAMES = {
    7: "morning",
    12: "noon",
    18: "evening",
    22: "night",
    2: "late_night",
}

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "raw"


def _get_session_name() -> str:
    hour = datetime.now().hour
    closest = min(SESSION_NAMES.keys(), key=lambda h: abs(h - hour))
    return SESSION_NAMES[closest]


class HdvCollector:
    """
    Collects prices from one HDV category using an active game session.

    Usage:
        collector = HdvCollector(session, account="account1@gmail.com")
        collector.collect_category(category_id=2)  # 2 = resources
        collector.save_to_csv()
    """

    def __init__(self, session: DofusTouchSession, account: str = "unknown"):
        self._session = session
        self._account = account
        self._records: list[dict] = []
        self._hdv_ready = threading.Event()
        self._collection_done = threading.Event()
        self._last_batch_start = 0  # index into _records where last collect_category started
        self._setup_handlers()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def collect_category(self, category_id: int, timeout: float = 30.0) -> list[dict]:
        """
        Request and collect prices for one HDV category.

        Args:
            category_id: The item type/category ID in the HDV
            timeout:     Max seconds to wait for response

        Returns:
            Only the records collected in THIS call (not previous calls).
        """
        self._collection_done.clear()
        self._last_batch_start = len(self._records)
        log.info("Requesting HDV category %d", category_id)
        self._session.send_message(
            "ExchangeTypeItemsExchangerDescriptionForUserMessage",
            {"objectType": category_id},
        )
        if not self._collection_done.wait(timeout):
            log.warning("Timeout waiting for category %d", category_id)
        return list(self._records[self._last_batch_start:])

    def open_hdv(self, npc_id: int = None, timeout: float = 15.0) -> bool:
        """
        Send ExchangePlayerRequestMessage to open an HDV.
        Returns True if HDV opened within timeout.

        Note: The character must be physically near the HDV NPC on the map.
        The npc_id must be the actionId of the HDV NPC in the current map.
        """
        self._hdv_ready.clear()
        # The exact message format needs verification from game traffic
        payload = {"npcId": npc_id} if npc_id else {}
        self._session.send_message("ExchangePlayerRequestMessage", payload)
        return self._hdv_ready.wait(timeout)

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
            "timestamp", "session", "item_id", "item_name", "hdv_category",
            "prix_x1", "prix_x10", "prix_x100", "prix_x1000",
            "nb_offres", "liste_prix", "compte_collecteur",
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

        @session.on("ExchangeStartedWithStorageMessage")
        @session.on("ExchangeStartedBidBuyerMessage")
        @session.on("ExchangeStartedBidSellerMessage")
        def on_hdv_opened(msg):
            log.info("HDV opened: %s", msg.get("_messageType"))
            self._hdv_ready.set()

        @session.on("ExchangeTypesItemsExchangerDescriptionForUserMessage")
        def on_item_descriptions(msg):
            descriptions = msg.get("itemTypeDescriptions", [])
            log.info("Received %d item descriptions", len(descriptions))

            now = datetime.now().isoformat()
            session_name = _get_session_name()

            for desc in descriptions:
                record = _parse_item_description(desc, now, session_name, self._account)
                if record:
                    self._records.append(record)

            self._collection_done.set()

        @session.on("ExchangeLeaveMessage")
        def on_hdv_closed(msg):
            log.info("HDV closed")


def _parse_item_description(desc: dict, timestamp: str, session: str, account: str) -> Optional[dict]:
    """
    Parse one item description from ExchangeTypesItemsExchangerDescriptionForUserMessage
    into a CSV row.

    The exact field names need verification from live traffic capture.
    Field names are based on script.js analysis + Dofus 2 protocol docs.
    """
    item_id = desc.get("objectGID") or desc.get("itemId") or desc.get("id")
    if not item_id:
        log.warning("Item description without ID: %s", list(desc.keys()))
        return None

    # Prices by quantity — field names TBC from live capture
    # Dofus protocol typically has prices as a list [price_x1, price_x10, price_x100]
    # Copy before padding to avoid mutating the original dict data
    prices = list(desc.get("prices", []) or desc.get("price", []))
    while len(prices) < 4:
        prices.append(0)

    # Individual prices list (to detect purchases between sessions)
    all_prices = desc.get("typeDescription", {}).get("prices", []) or prices
    liste_prix = "|".join(str(p) for p in all_prices if p > 0)

    nb_offres = desc.get("nbItems") or desc.get("quantity") or len(all_prices)

    return {
        "timestamp": timestamp,
        "session": session,
        "item_id": item_id,
        "item_name": desc.get("objectName") or desc.get("name") or "",
        "hdv_category": desc.get("objectType") or desc.get("categoryId") or "",
        "prix_x1": prices[0],
        "prix_x10": prices[1],
        "prix_x100": prices[2],
        "prix_x1000": prices[3],
        "nb_offres": nb_offres,
        "liste_prix": liste_prix,
        "compte_collecteur": account,
    }
