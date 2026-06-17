"""
Full HDV price collection pipeline.

Connects to Dofus Touch, opens an HDV, collects prices for all categories,
saves to CSV. Designed to run 5x/day (cron or Task Scheduler).

Usage:
    set DTV_LOGIN=throwaway@gmail.com
    set DTV_PASSWORD=xxx
    set DTV_SERVER_ID=401
    set DTV_CHARACTER_ID=12345678   (optional, auto-selects first char if omitted)
    python -m dtv.scripts.collect

    # Or with explicit HDV categories to collect:
    python -m dtv.scripts.collect --categories 2,6,36

IMPORTANT:
    - Use throwaway accounts only
    - The character must be near an HDV NPC in the game
    - Residential IP recommended (no VPN datacenter)
    - Max 4 accounts per IP/server
"""
import argparse
import logging
import os
import sys
import time
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

from dtv.collector.haapi import get_game_token
from dtv.collector.connection import DofusTouchSession
from dtv.collector.hdv import HdvCollector

# HDV categories to collect by default
# These are item type IDs — the full list will be discovered from live data
# TODO: populate from ExchangeTypesItemsExchangerDescriptionForUserMessage
DEFAULT_CATEGORIES = [
    2,    # Resources
    6,    # Equipment
    36,   # Consumables
]

# Delay between category requests (avoid looking like a bot)
INTER_CATEGORY_DELAY_S = 2.0


def main():
    parser = argparse.ArgumentParser(description="Collect HDV prices from Dofus Touch")
    parser.add_argument("--categories", help="Comma-separated category IDs", default=None)
    parser.add_argument("--server-id", type=int, default=None)
    parser.add_argument("--character-id", type=int, default=None)
    args = parser.parse_args()

    login = os.environ.get("DTV_LOGIN")
    password = os.environ.get("DTV_PASSWORD")
    server_id = args.server_id or int(os.environ.get("DTV_SERVER_ID", "401"))
    character_id = args.character_id or (int(os.environ.get("DTV_CHARACTER_ID")) if os.environ.get("DTV_CHARACTER_ID") else None)

    categories = DEFAULT_CATEGORIES
    if args.categories:
        categories = [int(c.strip()) for c in args.categories.split(",")]

    if not login or not password:
        log.error("DTV_LOGIN and DTV_PASSWORD must be set")
        sys.exit(1)

    log.info("=== DTV Collect | account=%s server=%d categories=%s ===", login, server_id, categories)

    # 1. Auth
    log.info("Authenticating...")
    try:
        token = get_game_token(login, password)
        log.info("Token obtained (%d chars)", len(token))
    except Exception as e:
        log.error("Auth failed: %s", e)
        sys.exit(1)

    # 2. Connect + login flow
    session = DofusTouchSession(
        game_token=token,
        server_id=server_id,
        character_id=character_id,
    )

    collector = HdvCollector(session, account=login)

    try:
        session.connect()
        log.info("Waiting for game to be ready...")
        if not session.wait_for_game(timeout=90):
            log.error("Game not ready after 90s — aborting")
            sys.exit(1)
        log.info("Game ready!")

        # 3. Open HDV
        # TODO: The character needs to be positioned near an HDV NPC.
        # For now we try to open without specifying NPC ID.
        # In a real scenario we'd navigate to the HDV map first.
        log.info("Opening HDV...")
        if not collector.open_hdv(timeout=15):
            log.warning("HDV open timeout — maybe not near an HDV NPC?")

        # 4. Collect each category
        total_records = 0
        for cat_id in categories:
            log.info("Collecting category %d...", cat_id)
            records = collector.collect_category(cat_id, timeout=30)
            total_records += len(records)
            log.info("  → %d records", len(records))
            time.sleep(INTER_CATEGORY_DELAY_S)

        # 5. Close HDV
        collector.close_hdv()

        # 6. Save
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
