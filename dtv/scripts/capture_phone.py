"""
Passive HDV capture from a real phone running the official Dofus Touch client.

This is the production collection path — no bot, no synthetic traffic. You play
normally on your (rooted) phone over 4G; the mini PC attaches to the game's
WebView via wireless ADB + CDP and records every item you open in the HDV plus
the average-price snapshot sent at each login.

────────────────────────────────────────────────────────────────────────────
ONE-TIME SETUP (phone)
  1. Root with Magisk (already done) so the WebView is debuggable. Dofus Touch's
     WebView must allow inspection — on a release app this needs root + a module
     that forces setWebContentsDebuggingEnabled(true) (e.g. an LSPosed module),
     OR the app already enables it. Verify with `adb shell cat /proc/net/unix |
     grep devtools` while the game is open: you should see a *webview_devtools*
     socket.
  2. Settings → Developer options → enable "Wireless debugging", pair once.

NETWORK (from anywhere on 4G)
  3. Phone joins the mini PC's WireGuard network so the PC can reach the phone's
     ADB port. Only the ADB/CDP channel uses WireGuard — the GAME traffic goes
     straight to Ankama over 4G, so there is no added in-game latency.

RUN (mini PC)
  adb connect <phone-wg-ip>:<adb-port>          # once per boot
  python -m dtv.scripts.capture_phone           # auto-forwards + captures

  # If you set up `adb forward` yourself, skip the auto step:
  python -m dtv.scripts.capture_phone --no-adb --port 9222

  # Disambiguate if several WebViews are debuggable:
  python -m dtv.scripts.capture_phone --target-filter dofus
────────────────────────────────────────────────────────────────────────────

Output (data/raw/):
  hdv_passive_<YYYYMMDD>.csv   — one row per item you open, appended live
  avgprices_<timestamp>.csv    — full market snapshot, one file per login
"""
import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent.parent.parent / "data" / "capture.log"),
    ],
)
log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from dtv.collector.cdp_client import CDPClient
from dtv.collector.passive_capture import PassiveCollector


def _adb(args: list[str], serial: str = None) -> str:
    """Run an adb command and return stdout (raises on non-zero exit)."""
    cmd = ["adb"] + (["-s", serial] if serial else []) + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        raise RuntimeError(f"adb {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _discover_webview_socket(serial: str = None) -> str:
    """
    Find the WebView devtools abstract socket name on the phone.

    /proc/net/unix lists '@webview_devtools_remote_<pid>' for each debuggable
    WebView. We strip the leading '@' (the abstract-namespace marker) because
    `adb forward localabstract:` wants the name without it.
    """
    out = _adb(["shell", "cat", "/proc/net/unix"], serial)
    sockets = []
    for line in out.splitlines():
        idx = line.find("@")
        if idx == -1:
            continue
        name = line[idx + 1:].strip()
        if "devtools_remote" in name:
            sockets.append(name)
    # Prefer a WebView socket over a chrome one; dedup preserving order.
    webviews = [s for s in dict.fromkeys(sockets) if "webview" in s]
    chosen = (webviews or list(dict.fromkeys(sockets)))
    if not chosen:
        raise RuntimeError(
            "No *_devtools_remote socket found. Is Dofus Touch open and its "
            "WebView debuggable (root + WebView debugging enabled)?"
        )
    if len(chosen) > 1:
        log.warning("Multiple devtools sockets %s — using %s", chosen, chosen[0])
    return chosen[0]


def _setup_forward(port: int, serial: str = None):
    socket_name = _discover_webview_socket(serial)
    log.info("Forwarding tcp:%d → localabstract:%s", port, socket_name)
    _adb(["forward", f"tcp:{port}", f"localabstract:{socket_name}"], serial)


def main():
    parser = argparse.ArgumentParser(description="Passive HDV capture from a real phone via CDP")
    parser.add_argument("--port", type=int, default=9222,
                        help="Local TCP port the WebView devtools socket is forwarded to")
    parser.add_argument("--account", default=os.environ.get("DTV_COLLECTOR_ACCOUNT", "main"),
                        help="Label written to the compte_collecteur CSV column")
    parser.add_argument("--target-filter",
                        help="Substring to pick the right WebView if several are debuggable")
    parser.add_argument("--adb-serial",
                        help="adb device serial (for `adb -s`), if multiple devices are connected")
    parser.add_argument("--adb-connect",
                        help="host:port to `adb connect` first (wireless ADB over WireGuard)")
    parser.add_argument("--no-adb", action="store_true",
                        help="Skip adb connect/forward — assume the port is already forwarded")
    args = parser.parse_args()

    if not args.no_adb:
        try:
            if args.adb_connect:
                log.info("adb connect %s", args.adb_connect)
                log.info(_adb(["connect", args.adb_connect]).strip())
            _setup_forward(args.port, args.adb_serial)
        except (RuntimeError, FileNotFoundError, subprocess.SubprocessError) as e:
            log.error("ADB setup failed: %s", e)
            log.error("Fix the ADB/forward step, or pass --no-adb if you forwarded it yourself.")
            sys.exit(1)

    collector = PassiveCollector(account=args.account)
    client = CDPClient(port=args.port, target_filter=args.target_filter)
    client.on_frame(collector.handle_frame)

    log.info("=== Passive capture started (account=%s, port=%d) ===", args.account, args.port)
    log.info("Play normally. Open items in the HDV — each is recorded. Ctrl+C to stop.")
    try:
        client.run_forever()
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    finally:
        client.stop()
        log.info("=== Capture ended: %d items, %d price snapshots captured ===",
                 collector.items_captured, collector.snapshots_captured)


if __name__ == "__main__":
    main()
