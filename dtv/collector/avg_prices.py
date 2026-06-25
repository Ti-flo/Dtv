"""
Average-price snapshot collector.

✅ Confirmed from live capture (HAR, sessions 5–6). The game client sends a
parameter-less ObjectAveragePricesGetMessage shortly after entering the world;
the server replies with a single ObjectAveragePricesMessage carrying the average
unit price (x1) of every tradeable item known to the server.

  Send: ObjectAveragePricesGetMessage   (no data)
  Recv: ObjectAveragePricesMessage {
          "ids":       [1977, 7624, 7733, ...],   # ~4900 item GIDs
          "avgPrices": [1,    1,    1,    ...]     # parallel array, kamas per x1
        }

Why this matters:
  - One message ≈ 4906 items (whole market) vs. hundreds of HDV round-trips.
  - It is exactly what the official client requests — fully legitimate traffic.
  - Per server, updated as sales happen (NOT a static daily value: 115 GIDs
    moved between two captures 51 min apart). Good signal for trend tracking.

Caveats:
  - It is an AVERAGE of recent sales (volume + recency weighted), not the live
    cheapest offer. For the current floor price, use the HDV two-step flow.
  - Quantity is x1 only (confirmed: GID 468 avg=28 vs HDV best x1 offer=14).
  - An item with no recent sales keeps a stale value until it next sells.

CSV output (one row per item GID per snapshot):
  timestamp, session, item_gid, avg_price_x1, compte_collecteur
"""
import csv
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from .connection import DofusTouchSession

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "raw"


class AveragePricesCollector:
    """
    Requests and stores the server's average-price snapshot.

    Usage:
        collector = AveragePricesCollector(session, account="mail@gmail.com")
        prices = collector.collect(timeout=20)   # {gid: avg_price_x1}
        collector.save_to_csv()

    Note: the snapshot is keyed by ITEM GID, while RESOURCE_TYPE_IDS in
    item_types.py are TYPE GIDs — you cannot filter this snapshot to resources
    directly. To know which item GIDs are resources, use the HDV typeDescription
    lists (HdvCollector), which map type → item GIDs.
    """

    def __init__(self, session: DofusTouchSession, account: str = "unknown"):
        self._session = session
        self._account = account
        self._prices: dict[int, int] = {}
        self._ready = threading.Event()
        self._setup_handlers()

    @property
    def prices(self) -> dict[int, int]:
        """Last collected snapshot as {item_gid: avg_price_x1}."""
        return dict(self._prices)

    def collect(self, timeout: float = 20.0) -> dict[int, int]:
        """
        Send ObjectAveragePricesGetMessage and wait for the snapshot.
        Returns {item_gid: avg_price_x1}. Empty dict on timeout.
        """
        self._ready.clear()
        log.info("Requesting average-price snapshot...")
        self._session.send_message("ObjectAveragePricesGetMessage", None)
        if not self._ready.wait(timeout):
            log.warning("Timeout waiting for ObjectAveragePricesMessage")
            return {}
        log.info("Average-price snapshot: %d items", len(self._prices))
        return dict(self._prices)

    def save_to_csv(self, output_dir: Optional[Path] = None) -> Path:
        """Write the snapshot to CSV. Returns the output path."""
        out_dir = output_dir or DATA_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = out_dir / f"avgprices_{timestamp}.csv"

        now = datetime.now().isoformat()
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "item_gid", "avg_price_x1", "compte_collecteur"])
            for gid, price in sorted(self._prices.items()):
                writer.writerow([now, gid, price, self._account])

        log.info("Saved %d average prices to %s", len(self._prices), path)
        return path

    def _setup_handlers(self):
        @self._session.on("ObjectAveragePricesMessage")
        def on_avg_prices(msg):
            ids = msg.get("ids", []) or []
            prices = msg.get("avgPrices", []) or []
            if len(ids) != len(prices):
                log.warning("ids/avgPrices length mismatch: %d vs %d", len(ids), len(prices))
            self._prices = dict(zip(ids, prices))
            self._ready.set()
