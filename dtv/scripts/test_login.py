"""
Step 3 — Test full login flow up to character selection.

Connects to login server, authenticates, prints server list and character list.
Does NOT enter the game or open HDV.

Usage:
    set DTV_APIKEY=78ab2339-...
    set DTV_REFRESH_TOKEN=0af20b4e-...
    set DTV_SERVER_ID=533
    python -m dtv.scripts.test_login

Server IDs (région canada, confirmés live ServersListMessage S6):
    530=Tiliwan  531=Kelerog  532=Blair  533=Talok  411=Tournament
    (server id is account-specific — check ServersListMessage for yours)
"""
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from dotenv import load_dotenv, set_key
    load_dotenv()
    _DOTENV_PATH = Path(__file__).parent.parent.parent / ".env"
    _HAS_DOTENV = True
except ImportError:
    _HAS_DOTENV = False

from dtv.collector.haapi import authenticate
from dtv.collector.connection import DofusTouchSession


def main():
    apikey = os.environ.get("DTV_APIKEY", "")
    refresh_token = os.environ.get("DTV_REFRESH_TOKEN", "")
    server_id = int(os.environ.get("DTV_SERVER_ID", "533"))

    if not apikey or not refresh_token:
        print("Usage: DTV_APIKEY=x DTV_REFRESH_TOKEN=y DTV_SERVER_ID=533 python -m dtv.scripts.test_login")
        sys.exit(1)

    print(f"\n=== Test login → server {server_id} ===\n")

    print("1. Authenticating with HAAPI...")
    try:
        account_id, token, new_apikey, new_rt = authenticate(apikey, refresh_token)
        print(f"   ✓ Token obtained ({len(token)} chars), account_id={account_id}")
        if _HAS_DOTENV and _DOTENV_PATH.exists():
            set_key(str(_DOTENV_PATH), "DTV_APIKEY", new_apikey)
            set_key(str(_DOTENV_PATH), "DTV_REFRESH_TOKEN", new_rt)
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
