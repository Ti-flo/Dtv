"""
Session dump — log every WebSocket frame to a JSONL file.

Connects to Dofus Touch, runs the full login flow, then records every
inbound game message to data/raw/session_dump_<timestamp>.jsonl.

Use this to explore new message types, verify protocol changes, or build
new collectors without guessing the format.

Usage:
    python -m dtv.scripts.dump_session
    python -m dtv.scripts.dump_session --duration 120   # stay 2 min
    python -m dtv.scripts.dump_session --filter HDV     # only types containing "HDV"

Output: data/raw/session_dump_YYYYMMDD_HHMMSS.jsonl
Each line: {"ts": 1234567890.123, "type": "MessageName", "msg": {...}}
"""
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

_DOTENV_PATH = Path(__file__).parent.parent.parent / ".env"
_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "raw"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
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
from dtv.collector.connection import DofusTouchSession


def main():
    parser = argparse.ArgumentParser(description="Dump all WebSocket frames to JSONL")
    parser.add_argument("--duration", type=float, default=60.0,
                        help="Seconds to stay connected after game ready (default: 60)")
    parser.add_argument("--filter", default="",
                        help="Only log types whose name contains this string (case-insensitive)")
    parser.add_argument("--server-id", type=int, default=None)
    parser.add_argument("--character-id", type=int, default=None)
    args = parser.parse_args()

    apikey = os.environ.get("DTV_APIKEY", "")
    refresh_token = os.environ.get("DTV_REFRESH_TOKEN", "")
    server_id = args.server_id or int(os.environ.get("DTV_SERVER_ID", "533"))
    character_id = args.character_id or (int(os.environ.get("DTV_CHARACTER_ID")) if os.environ.get("DTV_CHARACTER_ID") else None)

    if not apikey or not refresh_token:
        log.error("DTV_APIKEY and DTV_REFRESH_TOKEN must be set in .env")
        sys.exit(1)

    log.info("Authenticating...")
    account_id, token, new_apikey, new_rt = authenticate(apikey, refresh_token)
    log.info("Token obtained, account_id=%s", account_id)
    if _HAS_DOTENV and _DOTENV_PATH.exists():
        _set_key(str(_DOTENV_PATH), "DTV_APIKEY", new_apikey)
        _set_key(str(_DOTENV_PATH), "DTV_REFRESH_TOKEN", new_rt)

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = _DATA_DIR / f"session_dump_{stamp}.jsonl"

    session = DofusTouchSession(
        game_token=token,
        server_id=server_id,
        account_id=account_id,
        character_id=character_id,
    )

    msg_filter = args.filter.lower()
    frame_count = 0

    with open(out_path, "w") as f:
        def _write_frame(msg: dict):
            nonlocal frame_count
            msg_type = msg.get("_messageType") or msg.get("type") or "unknown"
            if msg_filter and msg_filter not in msg_type.lower():
                return
            line = json.dumps({"ts": time.time(), "type": msg_type, "msg": msg})
            f.write(line + "\n")
            f.flush()
            frame_count += 1
            log.info("[dump] %s", msg_type)

        session.connect()

        # Hook into the game primus client's wildcard handler once it exists.
        # _game_client is set in _setup_game_handlers() which runs before the
        # game socket opens — poll briefly for it.
        _deadline = time.time() + 30
        while time.time() < _deadline:
            game_client = getattr(session, "_game_client", None)
            if game_client is not None:
                game_client.on_raw(_write_frame)
                log.info("Hooked into game socket wildcard handler")
                break
            time.sleep(0.1)
        else:
            log.warning("Game socket not created within 30s — hooking login socket instead")
            login_client = getattr(session, "_login_client", None)
            if login_client:
                login_client.on_raw(_write_frame)

        log.info("Waiting for game ready (max 90s)...")
        if not session.wait_for_game(timeout=90):
            log.error("Game not ready after 90s — aborting")
            session.disconnect()
            sys.exit(1)

        log.info("Game ready! Recording for %.0fs (Ctrl+C to stop early)...", args.duration)
        try:
            time.sleep(args.duration)
        except KeyboardInterrupt:
            log.info("Interrupted by user")

    session.disconnect()
    log.info("Saved %d frames to %s", frame_count, out_path)
    print(f"\nDump saved: {out_path}  ({frame_count} frames)")


if __name__ == "__main__":
    main()
