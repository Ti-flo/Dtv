"""
Step 1 — Test HAAPI authentication independently.

Requires DTV_APIKEY and DTV_REFRESH_TOKEN in .env (bootstrapped once from a
logged-in app session via Chrome DevTools — see README).

Usage:
    python -m dtv.scripts.test_auth

On success, prints the new apikey and refresh_token. Update .env with these
values (the old ones are invalidated after RefreshApiKey).
"""
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from dotenv import load_dotenv, set_key
    load_dotenv()
    _DOTENV_PATH = Path(__file__).parent.parent.parent / ".env"
    _HAS_DOTENV = True
except ImportError:
    _HAS_DOTENV = False

from dtv.collector.haapi import refresh_api_key, create_token, GAME_ID


def main():
    apikey = os.environ.get("DTV_APIKEY", "")
    refresh_token = os.environ.get("DTV_REFRESH_TOKEN", "")

    if not apikey or not refresh_token:
        print("Missing DTV_APIKEY or DTV_REFRESH_TOKEN in .env")
        print("Bootstrap these values once from a logged-in app session:")
        print("  1. Open Chrome DevTools connected to the emulator (adb forward)")
        print("  2. Go to Network tab, filter by 'haapi'")
        print("  3. Find the RefreshApiKey or CreateApiKey request")
        print("  4. Copy the 'apikey' header value → DTV_APIKEY")
        print("  5. Copy the 'refresh_token' from the response → DTV_REFRESH_TOKEN")
        sys.exit(1)

    print(f"\n=== Testing HAAPI auth (game_id={GAME_ID}) ===\n")

    # Step 1 — Refresh API key
    print("1. POST /Ankama/v5/Api/RefreshApiKey ...")
    try:
        refreshed = refresh_api_key(apikey, refresh_token)
        new_apikey = refreshed["key"]
        new_refresh_token = refreshed.get("refresh_token", refresh_token)
        account_id = refreshed.get("account_id", "N/A")
        print(f"   ✓ Fields: {list(refreshed.keys())}")
        print(f"   account_id: {account_id}")
        print(f"   new apikey: {new_apikey[:20]}...")
    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        print("\n   If 403: Cloudflare blocked — try from residential IP, no VPN")
        print("   If 401: apikey/refresh_token expired — re-bootstrap from the app")
        sys.exit(1)

    # Step 2 — Create game token
    print("\n2. GET /Ankama/v5/Account/CreateToken ...")
    try:
        token = create_token(new_apikey)
        print(f"   ✓ game token: {token[:30]}...")
        print(f"   (length: {len(token)} chars)")
    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        sys.exit(1)

    print("\n=== Auth OK ✓ ===")

    # Save rotated tokens to .env
    if _HAS_DOTENV and _DOTENV_PATH.exists():
        set_key(str(_DOTENV_PATH), "DTV_APIKEY", new_apikey)
        set_key(str(_DOTENV_PATH), "DTV_REFRESH_TOKEN", new_refresh_token)
        print(f"\n.env updated with new apikey and refresh_token")
    else:
        print(f"\nUpdate .env manually:")
        print(f"DTV_APIKEY={new_apikey}")
        print(f"DTV_REFRESH_TOKEN={new_refresh_token}")

    print(f"\nGame token (copy for next test):\n{token}")


if __name__ == "__main__":
    main()
