"""
Full HDV price collection pipeline.

Connects to Dofus Touch, opens an HDV, collects prices for all categories,
saves to CSV. Designed to run 5x/day (cron or Task Scheduler).

Usage:
    set DTV_LOGIN=throwaway@gmail.com
    set DTV_PASSWORD=xxx
    set DTV_SERVER_ID=533
    set DTV_CHARACTER_ID=12345678   (optional, auto-selects first char if omitted)
    python -m dtv.scripts.collect

    # Or with explicit HDV categories to collect:
    python -m dtv.scripts.collect --categories 2,6,36

IMPORTANT:
    - Use throwaway accounts only
    - HDV is accessible from anywhere (no need to be near an NPC)
    - Residential IP mandatory (no VPN datacenter)
    - Max 4 accounts per IP/server
"""
import argparse
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent.parent.parent / "data" / "collect.log"),
    ],
)
log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from dtv.collector.haapi import authenticate
from dtv.collector.connection import DofusTouchSession
from dtv.collector.hdv import HdvCollector
from dtv.collector.avg_prices import AveragePricesCollector
from dtv.collector.timing import human_delay
from dtv.collector.item_types import CORE_RESOURCE_TYPE_IDS, RESOURCE_TYPE_IDS

def main():
    parser = argparse.ArgumentParser(description="Collect HDV prices from Dofus Touch")
    parser.add_argument("--categories",
                        help="Comma-separated type GIDs. Use 'all' for all HDV types, "
                             "'resources' for all resource types (default: core resources)",
                        default=None)
    parser.add_argument("--server-id", type=int, default=None)
    parser.add_argument("--character-id", type=int, default=None)
    parser.add_argument("--avg-prices-only", action="store_true",
                        help="Only grab the average-price snapshot (one message, "
                             "~4900 items), skip the HDV walk entirely")
    parser.add_argument("--no-avg-prices", action="store_true",
                        help="Skip the average-price snapshot")
    args = parser.parse_args()

    login = os.environ.get("DTV_LOGIN")
    password = os.environ.get("DTV_PASSWORD")
    server_id = args.server_id or int(os.environ.get("DTV_SERVER_ID", "533"))
    character_id = args.character_id or (int(os.environ.get("DTV_CHARACTER_ID")) if os.environ.get("DTV_CHARACTER_ID") else None)

    if args.categories == "all":
        categories = None  # use buyerDescriptor.types from server
    elif args.categories == "resources":
        categories = RESOURCE_TYPE_IDS
    elif args.categories:
        categories = [int(c.strip()) for c in args.categories.split(",")]
    else:
        categories = CORE_RESOURCE_TYPE_IDS  # default: 40 core crafting resources

    if not login or not password:
        log.error("DTV_LOGIN and DTV_PASSWORD must be set")
        sys.exit(1)

    log.info("=== DTV Collect | account=%s server=%d categories=%s ===", login, server_id, categories)

    # 1. Auth
    log.info("Authenticating...")
    try:
        account_id, token = authenticate(login, password)
        log.info("Token obtained (%d chars), account_id=%s", len(token), account_id)
    except Exception as e:
        log.error("Auth failed: %s", e)
        sys.exit(1)

    # 2. Connect + login flow
    session = DofusTouchSession(
        game_token=token,
        server_id=server_id,
        account_id=account_id,
        character_id=character_id,
    )

    collector = HdvCollector(session, account=login)
    avg_collector = AveragePricesCollector(session, account=login)

    try:
        session.connect()
        log.info("Waiting for game to be ready...")
        if not session.wait_for_game(timeout=90):
            log.error("Game not ready after 90s — aborting")
            sys.exit(1)
        log.info("Game ready!")

        # 3. Average-price snapshot (one message ≈ 4900 items, fully legit traffic)
        if not args.no_avg_prices:
            log.info("Grabbing average-price snapshot...")
            prices = avg_collector.collect(timeout=20)
            if prices:
                path = avg_collector.save_to_csv()
                log.info("Saved %d average prices to %s", len(prices), path)
            human_delay(2.0, 5.0)

        if args.avg_prices_only:
            log.info("--avg-prices-only set — skipping HDV walk")
            return

        # 4. Open HDV (accessible from anywhere, confirmed from script.js openBidHouse())
        log.info("Opening HDV...")
        if not collector.open_hdv(timeout=15):
            log.warning("HDV open timeout — check if npcMapId is correct")
        elif collector.economics:
            log.info("HDV economics: %s", collector.economics)

        # 5. Collect item types (all advertised, or the explicit subset)
        if categories is None:
            log.info("Collecting all %d advertised types from server...", len(collector.available_types))
            total_records = collector.collect_all(timeout=30)
        else:
            total_records = 0
            for type_gid in categories:
                log.info("Collecting item type GID=%d...", type_gid)
                records = collector.collect_type(type_gid, timeout=30)
                total_records += len(records)
                log.info("  → %d records", len(records))
                human_delay(2.0, 5.0)

        # 6. Close HDV
        collector.close_hdv()

        # 7. Save
        if total_records > 0:
            path = collector.save_to_csv()
            log.info("Saved %d total records to %s", total_records, path)
        else:
            log.warning("No records collected — check HDV open flow")

    except KeyboardInterrupt:
        log.info("Interrupted by user")
    except Exception as e:
        log.exception("Collection failed: %s", e)
    finally:
        session.disconnect()
        log.info("=== Collection session ended ===")


if __name__ == "__main__":
    main()
