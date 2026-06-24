"""
Remote-control HTTP server — lets you start/stop passive capture from your phone.

Run once on the mini PC (keep it in a tmux pane):
    python -m dtv.scripts.remote_server

Then from your phone on the WireGuard network:
    # Check status
    curl http://<minipc-wg-ip>:8765/status

    # Start capture (uses env defaults)
    curl -X POST http://<minipc-wg-ip>:8765/start

    # Start with params
    curl -X POST http://<minipc-wg-ip>:8765/start \\
         -H "Content-Type: application/json" \\
         -d '{"adb_connect":"192.168.100.2:5555","account":"main"}'

    # Stop capture
    curl -X POST http://<minipc-wg-ip>:8765/stop

    # Tail the last 20 log lines
    curl http://<minipc-wg-ip>:8765/logs

On Android you can bookmark these as browser shortcuts or use HTTP Shortcuts app.
On iOS, save them as Shortcuts (URL + "Get Contents of URL" action).

Security: by default listens on all interfaces on port 8765. Use --host to restrict
to the WireGuard interface IP only. No authentication — keep this port firewalled
to the WireGuard network.
"""
import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent.parent
LOG_PATH = ROOT / "data" / "capture.log"

_process: "subprocess.Popen | None" = None
_lock = threading.Lock()
_capture_params: dict = {}


# ------------------------------------------------------------------ #
# Capture lifecycle                                                   #
# ------------------------------------------------------------------ #

def _build_cmd(params: dict) -> list[str]:
    cmd = [sys.executable, "-m", "dtv.scripts.capture_phone"]
    if params.get("port"):
        cmd += ["--port", str(params["port"])]
    if params.get("account"):
        cmd += ["--account", str(params["account"])]
    if params.get("target_filter"):
        cmd += ["--target-filter", str(params["target_filter"])]
    if params.get("adb_serial"):
        cmd += ["--adb-serial", str(params["adb_serial"])]
    if params.get("adb_connect"):
        cmd += ["--adb-connect", str(params["adb_connect"])]
    if params.get("no_adb"):
        cmd += ["--no-adb"]
    return cmd


def _read_status() -> dict:
    with _lock:
        running = _process is not None and _process.poll() is None
        pid = _process.pid if _process else None
        rc = _process.returncode if (_process and _process.poll() is not None) else None
    return {
        "running": running,
        "pid": pid,
        "returncode": rc,
        "params": _capture_params,
    }


def _start(params: dict) -> dict:
    global _process, _capture_params
    with _lock:
        if _process is not None and _process.poll() is None:
            return {"ok": False, "error": "already_running", "pid": _process.pid}
        cmd = _build_cmd(params)
        log.info("Starting capture: %s", " ".join(cmd))
        _process = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # don't propagate SIGINT from the server
        )
        _capture_params = params
    log.info("Capture started (pid=%d)", _process.pid)
    return {"ok": True, "pid": _process.pid, "cmd": cmd}


def _stop() -> dict:
    global _process
    with _lock:
        if _process is None or _process.poll() is not None:
            return {"ok": False, "error": "not_running"}
        pid = _process.pid
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return {"ok": False, "error": "process_already_gone", "pid": pid}
    log.info("SIGTERM sent to capture process (pid=%d)", pid)
    return {"ok": True, "pid": pid, "message": "SIGTERM sent"}


def _tail_log(n: int = 40) -> list[str]:
    """Return the last n lines of the capture log."""
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-n:]


# ------------------------------------------------------------------ #
# HTTP handler                                                        #
# ------------------------------------------------------------------ #

class _Handler(BaseHTTPRequestHandler):
    def _send_json(self, data, status: int = 200):
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        if self.path in ("/", "/status"):
            self._send_json(_read_status())
        elif self.path.startswith("/logs"):
            # Optional ?n=20 query param
            n = 40
            if "?" in self.path:
                qs = self.path.split("?", 1)[1]
                for part in qs.split("&"):
                    if part.startswith("n="):
                        try:
                            n = int(part[2:])
                        except ValueError:
                            pass
            self._send_json({"lines": _tail_log(n)})
        else:
            self._send_json({"error": "not_found"}, 404)

    def do_POST(self):
        if self.path == "/start":
            params = self._read_body()
            self._send_json(_start(params))
        elif self.path == "/stop":
            self._send_json(_stop())
        elif self.path == "/restart":
            params = self._read_body()
            _stop()
            self._send_json(_start(params))
        else:
            self._send_json({"error": "not_found"}, 404)

    def log_message(self, fmt, *args):
        log.debug("HTTP %s — %s", self.address_string(), fmt % args)


# ------------------------------------------------------------------ #
# Entry point                                                         #
# ------------------------------------------------------------------ #

def main():
    parser = argparse.ArgumentParser(description="Remote control server for passive capture")
    parser.add_argument("--host", default="0.0.0.0",
                        help="Interface to bind (default: all). Use WireGuard IP to restrict access.")
    parser.add_argument("--port", type=int, default=8765,
                        help="HTTP port (default: 8765)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        handlers=[logging.StreamHandler()],
    )

    server = HTTPServer((args.host, args.port), _Handler)
    log.info("=== Remote server ready on http://%s:%d ===", args.host, args.port)
    log.info("Phone shortcut  → curl -X POST http://<wg-ip>:%d/start", args.port)
    log.info("Status          → curl http://<wg-ip>:%d/status", args.port)
    log.info("Logs            → curl http://<wg-ip>:%d/logs", args.port)
    log.info("Stop            → curl -X POST http://<wg-ip>:%d/stop", args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Stopping...")
    finally:
        _stop()


if __name__ == "__main__":
    main()
