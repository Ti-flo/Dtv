"""
Step 3 — Test full login flow up to character selection.

Connects to login server, authenticates, prints server list and character list.
Does NOT enter the game or open HDV.

Usage:
    set DTV_LOGIN=yourmail@gmail.com
    set DTV_PASSWORD=yourpassword
    set DTV_SERVER_ID=533
    python -m dtv.scripts.test_login

Server IDs (région canada, confirmés live ServersListMessage S6):
    530=Tiliwan  531=Kelerog  532=Blair  533=Talok  411=Tournament
    The throwaway test account's character is on 533 (Talok).
    (server id is account-specific — check ServersListMessage for yours)
"""
import logging
import os
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
log = logging.getLogger(__name__)

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from dtv.collector.haapi import authenticate
from dtv.collector.connection import DofusTouchSession


def main():
    login = os.environ.get("DTV_LOGIN")
    password = os.environ.get("DTV_PASSWORD")
    server_id = int(os.environ.get("DTV_SERVER_ID", "533"))

    if not login or not password:
        print("Usage: DTV_LOGIN=x DTV_PASSWORD=y DTV_SERVER_ID=533 python -m dtv.scripts.test_login")
        sys.exit(1)

    print(f"\n=== Test login: {login} → server {server_id} ===\n")

    print("1. Authenticating with HAAPI...")
    try:
        account_id, token = authenticate(login, password)
        print(f"   ✓ Token obtained ({len(token)} chars), account_id={account_id}")
    except Exception as e:
        print(f"   ✗ Auth failed: {e}")
        sys.exit(1)

    print("\n2. Connecting to login server...")
    session = DofusTouchSession(
        game_token=token,
        server_id=server_id,
        account_id=account_id,
        character_id=None,  # auto-select first character
    )

    # Intercept messages to print them
    from dtv.collector.primus_client import PrimusClient

    try:
        session.connect()
        print("   ✓ Connected")
    except Exception as e:
        print(f"   ✗ Connection failed: {e}")
        sys.exit(1)

    print("\n3. Waiting for game ready (max 60s)...")
    if session.wait_for_game(timeout=60):
        print("   ✓ Game ready! Full login flow works.")
    else:
        print("   ✗ Timed out. Check logs above for last message received.")

    session.disconnect()
    print("\n=== Test done ===")


if __name__ == "__main__":
    main()
