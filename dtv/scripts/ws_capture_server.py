"""
Local HTTP server that receives WebSocket logs from the patched game (fetch mode).

The patched script.js POSTs every WebSocket event to http://10.0.2.2:8765/log
(10.0.2.2 = host machine IP as seen from inside AVD).

Usage:
    python -m dtv.scripts.ws_capture_server

Output:
    Pretty-printed to stdout + JSONL file at data/raw/ws_capture_<timestamp>.jsonl

Tip: if using logcat mode instead (default in ws_intercept.js), just run:
    adb logcat | grep "[DTV]"

JSONL format (one JSON object per line):
    {"t": "url",  "ts": 1234567890, "d": "wss://..."}  <- WebSocket opened
    {"t": "out",  "ts": 1234567890, "d": "{...}"}       <- message sent
    {"t": "in",   "ts": 1234567890, "d": "{...}"}       <- message received
    {"t": "init", "ts": 1234567890, "mode": "fetch"}    <- interceptor loaded
"""
import json
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PORT = 8765
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "raw"

# ANSI colours for terminal readability
_RED   = "\033[91m"
_GREEN = "\033[92m"
_BLUE  = "\033[94m"
_GREY  = "\033[90m"
_RESET = "\033[0m"


def _fmt(entry: dict) -> str:
    t = entry.get("t", "?")
    d = entry.get("d", "")
    ts = datetime.fromtimestamp(entry.get("ts", 0) / 1000).strftime("%H:%M:%S.%f")[:-3]

    if t == "url":
        return f"{_BLUE}[{ts}] OPEN  {d}{_RESET}"
    elif t == "out":
        return f"{_GREEN}[{ts}] →OUT  {d[:300]}{_RESET}"
    elif t == "in":
        return f"{_RED}[{ts}] ←IN   {d[:300]}{_RESET}"
    elif t == "init":
        return f"{_GREY}[{ts}] INIT  mode={entry.get('mode')}{_RESET}"
    return f"{_GREY}[{ts}] {t}  {d[:300]}{_RESET}"


class _Handler(BaseHTTPRequestHandler):
    outfile = None

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            entry = json.loads(body)
            print(_fmt(entry))
            if _Handler.outfile:
                _Handler.outfile.write(body + "\n")
                _Handler.outfile.flush()
        except Exception as e:
            print(f"[ERROR] {e}: {body[:100] if 'body' in dir() else '?'}")

        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass  # silence access log noise


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = DATA_DIR / f"ws_capture_{timestamp}.jsonl"

    with open(out_path, "w", encoding="utf-8") as f:
        _Handler.outfile = f
        print(f"Listening on 0.0.0.0:{PORT}")
        print(f"Output: {out_path}")
        print(f"AVD can reach this server at http://10.0.2.2:{PORT}")
        print("Waiting for game events... (Ctrl+C to stop)\n")
        try:
            HTTPServer(("0.0.0.0", PORT), _Handler).serve_forever()
        except KeyboardInterrupt:
            print(f"\nCapture saved: {out_path}")


if __name__ == "__main__":
    main()
