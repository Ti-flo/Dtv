"""
Full HDV price collection pipeline.

Connects to Dofus Touch, opens an HDV, collects prices for all categories,
saves to CSV. Designed to run 5x/day (cron or Task Scheduler).

Usage:
    set DTV_APIKEY=78ab2339-...
    set DTV_REFRESH_TOKEN=0af20b4e-...
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

_DOTENV_PATH = Path(__file__).parent.parent.parent / ".env"

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
    from dotenv import load_dotenv, set_key as _set_key
    load_dotenv()
    _HAS_DOTENV = True
except ImportError:
    _HAS_DOTENV = False

from dtv.collector.haapi import authenticate
from dtv.collector.connection import (
    DofusTouchSession, classify_error, RETRY_LATER, STOP_HUMAN,
)
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

    apikey = os.environ.get("DTV_APIKEY", "")
    refresh_token = os.environ.get("DTV_REFRESH_TOKEN", "")
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

    if not apikey or not refresh_token:
        log.error("DTV_APIKEY and DTV_REFRESH_TOKEN must be set in .env")
        sys.exit(1)

    log.info("=== DTV Collect | server=%d categories=%s ===", server_id, categories)

    # 1. Auth
    log.info("Authenticating...")
    try:
        account_id, token, new_apikey, new_rt = authenticate(apikey, refresh_token)
        log.info("Token obtained (%d chars), account_id=%s", len(token), account_id)
        if _HAS_DOTENV and _DOTENV_PATH.exists():
            _set_key(str(_DOTENV_PATH), "DTV_APIKEY", new_apikey)
            _set_key(str(_DOTENV_PATH), "DTV_REFRESH_TOKEN", new_rt)
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

    collector = HdvCollector(session, account=account_id)
    avg_collector = AveragePricesCollector(session, account=account_id)

    failed = False
    try:
        session.connect()
        log.info("Waiting for game to be ready...")
        if not session.wait_for_game(timeout=90):
            log.error("Game not ready after 90s — aborting")
            raise RuntimeError("game_not_ready_timeout")
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
        return
    except Exception as e:
        log.exception("Collection failed: %s", e)
        failed = True
    finally:
        session.disconnect()
        log.info("=== Collection session ended ===")

    # Map the outcome to an exit code a scheduler can act on:
    #   0 = OK | 2 = retry later (maintenance/network) | 3 = stop, human needed
    #   (ban / outdated client) | 1 = unknown failure
    if not failed and session.error is None:
        return  # clean success → exit 0
    category = classify_error(session.error)
    if category == STOP_HUMAN:
        log.error("STOP — human intervention required (%s). Not retrying.", session.error)
        sys.exit(3)
    if category == RETRY_LATER:
        log.warning("Transient failure (%s) — scheduler should retry next slot.", session.error)
        sys.exit(2)
    log.error("Run failed (%s) — exit 1.", session.error or "unknown")
    sys.exit(1)


if __name__ == "__main__":
    main()
