"""
Step 2 — Test WebSocket connection to login server.

This script:
  1. Fetches config.json from the login server (no auth needed)
  2. Connects to the Primus WebSocket endpoint
  3. Prints every message received for 30 seconds
  4. Exits — useful for discovering the exact wire format

Usage:
    python -m dtv.scripts.test_connect

No credentials needed for this test — just checks connectivity.
"""
import json
import logging
import sys
import time

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
log = logging.getLogger(__name__)

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent.parent))

import requests
from dtv.collector.primus_client import PrimusClient
from dtv.collector.connection import LOGIN_SERVER, PRIMUS_PATH


def main():
    print(f"\n=== Step 1: Fetching config.json from {LOGIN_SERVER} ===\n")
    try:
        r = requests.get(f"{LOGIN_SERVER}/config.json", params={"lang": "fr"}, timeout=15)
        config = r.json()
        print(json.dumps(config, indent=2)[:1000])
    except Exception as e:
        print(f"config.json failed: {e}")
        config = {}

    print(f"\n=== Step 2: Connecting to WebSocket ===\n")
    ws_url = LOGIN_SERVER.replace("https://", "wss://") + PRIMUS_PATH
    print(f"URL: {ws_url}")

    received = []
    client = PrimusClient(ws_url)

    @client.on_raw
    def capture(msg):
        received.append(msg)
        print(f"\n← MSG #{len(received)}: {json.dumps(msg, indent=2)[:500]}")

    @client.on("__open__")
    def on_open(msg):
        print("\n✓ WebSocket connected!")

    @client.on("__close__")
    def on_close(msg):
        print(f"\nConnection closed: {msg}")

    @client.on("__error__")
    def on_error(msg):
        print(f"\n✗ Error: {msg}")

    try:
        client.connect(wait=True, timeout=15)
        print("Listening for 30s (Ctrl+C to stop early)...")
        time.sleep(30)
    except TimeoutError:
        print(f"\n✗ Could not connect to {ws_url}")
        print("\nPossible issues:")
        print(f"  - Wrong path: try changing PRIMUS_PATH in connection.py")
        print(f"    Currently: {PRIMUS_PATH}")
        print(f"  - Check /build/primus.js for the actual path")
        sys.exit(1)
    except KeyboardInterrupt:
        pass
    finally:
        client.disconnect()

    print(f"\n=== Done. Received {len(received)} messages ===")


if __name__ == "__main__":
    main()
