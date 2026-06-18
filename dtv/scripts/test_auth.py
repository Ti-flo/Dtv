"""
Step 1 — Test HAAPI authentication independently.

Usage:
    # Option A: env vars (recommended, don't type password in terminal)
    set DTV_LOGIN=yourmail@gmail.com
    set DTV_PASSWORD=yourpassword
    python -m dtv.scripts.test_auth

    # Option B: args
    python -m dtv.scripts.test_auth yourmail@gmail.com yourpassword

IMPORTANT: Use a throwaway Gmail account. Never use your main account.
"""
import logging
import os
import sys

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
log = logging.getLogger(__name__)

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from dtv.collector.haapi import create_api_key, create_token, GAME_ID


def main():
    if len(sys.argv) >= 3:
        login, password = sys.argv[1], sys.argv[2]
    else:
        login = os.environ.get("DTV_LOGIN")
        password = os.environ.get("DTV_PASSWORD")

    if not login or not password:
        print("Usage: python -m dtv.scripts.test_auth <login> <password>")
        print("   or: DTV_LOGIN=x DTV_PASSWORD=y python -m dtv.scripts.test_auth")
        sys.exit(1)

    print(f"\n=== Testing HAAPI auth for: {login} (game_id={GAME_ID}) ===\n")

    # Step 1 — Create API key
    print("1. POST /Ankama/v5/Api/CreateApiKey ...")
    try:
        api_data = create_api_key(login, password)
        print(f"   ✓ api_key fields: {list(api_data.keys())}")
        print(f"   account_id: {api_data.get('account_id', 'N/A')}")
        api_key = api_data.get("key", "")
        print(f"   api_key: {api_key[:20]}...")
    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        print("\n   If you got a 403: Cloudflare is blocking — try from residential IP (no VPN)")
        print("   If you got a 401: Wrong credentials")
        sys.exit(1)

    # Step 2 — Create game token
    print("\n2. GET /Ankama/v5/Game/CreateToken ...")
    try:
        token = create_token(api_key)
        print(f"   ✓ game token: {token[:30]}...")
        print(f"   (length: {len(token)} chars)")
    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        sys.exit(1)

    print("\n=== Auth OK ✓ ===")
    print(f"\nGame token (copy for next test):\n{token}")


if __name__ == "__main__":
    main()
