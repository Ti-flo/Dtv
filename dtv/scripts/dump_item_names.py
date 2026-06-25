"""
Dump GID → item name from the running Dofus Touch WebView via CDP.

Run ONCE while Dofus Touch is open and you are logged in (the Items DB
is fully populated after login):

    python -m dtv.scripts.dump_item_names

Prerequisites — same as capture_phone:
  • `adb forward tcp:9222 localabstract:webview_devtools_remote_<pid>` must
    already be set up (or use --port if you forwarded on a different port).

Saves  data/item_names.json  (~10,000+ entries, no personal data).
Re-run after game updates that add new items.

The script uses CDP Runtime.evaluate to call JavaScript directly in the
WebView; it reads window.gui.databases.Items._dataStore which is already
populated and has the localized item names for the game's current language.
"""
import argparse
import json
import logging
import sys
import time
import urllib.request
from pathlib import Path

import websocket

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent.parent
DEFAULT_OUT = ROOT / "data" / "item_names.json"

# ---------------------------------------------------------------------- #
# JavaScript that runs inside the WebView to extract item names.          #
#                                                                         #
# In Dofus Touch the game databases are loaded as JS objects at login.    #
# window.gui.databases.Items._dataStore is a plain object { id: item }.   #
# Each item has either:                                                    #
#   • item.name  — already-resolved string (most builds)                  #
#   • item.nameId — integer into the I18n table (some builds)             #
# We try both and fall back to a numeric placeholder so no GID is lost.   #
# ---------------------------------------------------------------------- #
_JS = r"""
(function() {
  try {
    // Diagnostic: report what's available if we can't find the Items DB.
    function diag() {
      var d = {
        hasGui: typeof window.gui !== "undefined",
        guiKeys: [],
        databaseKeys: [],
        hint: "run dump_item_names while logged in and in the game world"
      };
      if (window.gui) {
        try { d.guiKeys = Object.keys(window.gui).slice(0, 30); } catch(e) {}
        if (window.gui.databases) {
          try { d.databaseKeys = Object.keys(window.gui.databases); } catch(e) {}
        }
      }
      return JSON.stringify({error: "no Items database found", diag: d});
    }

    if (!window.gui || !window.gui.databases)
      return diag();

    // Try several key names used across Dofus Touch versions.
    var dbs = window.gui.databases;
    var db = dbs.Items || dbs.items || dbs.Item || dbs.item
          || dbs.ItemTemplate || dbs.ItemTemplates || null;

    // Also accept a key that contains "item" (case-insensitive) as fallback.
    if (!db) {
      for (var k in dbs) {
        if (k.toLowerCase().indexOf("item") === 0 && dbs[k] && dbs[k]._dataStore) {
          db = dbs[k];
          break;
        }
      }
    }

    if (!db) return diag();

    var store = db._dataStore || db.dataStore || db;
    if (!store || typeof store !== "object")
      return JSON.stringify({error: "Items store not an object"});

    // I18n table for nameId resolution (present in most builds).
    var i18nStore = null;
    try {
      var i18nDb = dbs.I18n || dbs.i18n || null;
      i18nStore = i18nDb && (i18nDb._dataStore || i18nDb.dataStore || i18nDb);
    } catch(e) {}

    var out = {};
    for (var id in store) {
      if (!Object.prototype.hasOwnProperty.call(store, id)) continue;
      var item = store[id];
      var name = null;

      if (typeof item.name === "string" && item.name.length > 0) {
        name = item.name;
      } else if (i18nStore && item.nameId) {
        var entry = i18nStore[item.nameId];
        if (entry && typeof entry.text === "string") name = entry.text;
        else if (typeof entry === "string") name = entry;
      }

      if (!name && item.nameId) name = "#" + item.nameId;
      if (name) out[id] = name;
    }

    return JSON.stringify({ok: true, count: Object.keys(out).length, items: out});
  } catch(e) {
    return JSON.stringify({error: String(e), stack: String(e.stack || "")});
  }
})()
"""

# Lightweight JS just to inspect the game's JS structure — used by --diagnose.
_JS_DIAG = r"""
(function() {
  var r = {
    hasGui: typeof window.gui !== "undefined",
    guiKeys: [],
    databaseKeys: [],
    sampleItem: null
  };
  try {
    if (window.gui) {
      r.guiKeys = Object.keys(window.gui).slice(0, 40);
      if (window.gui.databases) {
        r.databaseKeys = Object.keys(window.gui.databases);
        // Grab first item from any *item*-keyed DB so we can see its fields.
        for (var k in window.gui.databases) {
          if (k.toLowerCase().indexOf("item") === 0) {
            var store = window.gui.databases[k]._dataStore
                     || window.gui.databases[k].dataStore;
            if (store) {
              var firstKey = Object.keys(store)[0];
              if (firstKey) {
                r.sampleItem = {dbKey: k, id: firstKey,
                                fields: Object.keys(store[firstKey]).slice(0, 20)};
              }
            }
            break;
          }
        }
      }
    }
  } catch(e) { r.error = String(e); }
  return JSON.stringify(r);
})()
"""


def _discover_ws_url(host: str, port: int, target_filter: str) -> str:
    url = f"http://{host}:{port}/json"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            targets = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log.error("Cannot reach DevTools endpoint %s: %s", url, e)
        sys.exit(1)

    filt = target_filter.lower()
    candidates = [
        t for t in targets
        if t.get("webSocketDebuggerUrl")
        and t.get("type", "page") in ("page", "webview", "app")
        and (not filt or filt in (t.get("url", "") + t.get("title", "")).lower())
    ]
    if not candidates:
        available = [t.get("title") or t.get("url") for t in targets]
        log.error(
            "No debuggable target found (filter=%r). Available targets: %s",
            target_filter, available,
        )
        sys.exit(1)

    chosen = candidates[0]
    log.info("Using WebView: title=%r", chosen.get("title") or chosen.get("url"))
    return chosen["webSocketDebuggerUrl"]


def dump_item_names(
    host: str = "localhost",
    port: int = 9222,
    target_filter: str = "dofus",
    out_path: Path = DEFAULT_OUT,
    timeout: float = 30.0,
) -> int:
    """Run the JS dump and save the result.  Returns the number of names saved."""
    log.info("Runtime.evaluate sent — waiting for response (timeout=%.0fs)…", timeout)
    raw_value = _run_js(host, port, target_filter, _JS, timeout)
    parsed = json.loads(raw_value)
    if "error" in parsed:
        diag = parsed.get("diag", {})
        log.error("JavaScript error: %s", parsed["error"])
        if diag:
            log.error("window.gui present: %s", diag.get("hasGui"))
            log.error("window.gui keys: %s", diag.get("guiKeys"))
            log.error("window.gui.databases keys: %s", diag.get("databaseKeys"))
            hint = diag.get("hint", "")
            if hint:
                log.error("Hint: %s", hint)
        sys.exit(1)

    items: dict[str, str] = parsed.get("items", {})
    count = parsed.get("count", len(items))
    log.info("Extracted %d item names", count)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Compact JSON: one line, no indentation (file is ~1 MB with 10k items)
    out_path.write_text(
        json.dumps(items, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    log.info("Saved → %s  (%.1f KB)", out_path, out_path.stat().st_size / 1024)
    return count


def _run_js(host: str, port: int, target_filter: str, js: str, timeout: float) -> str:
    """Connect to CDP, evaluate js, return the raw string value."""
    ws_url = _discover_ws_url(host, port, target_filter)
    log.info("Connecting to %s", ws_url)
    conn = websocket.create_connection(ws_url, timeout=timeout)
    try:
        conn.send(json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {"expression": js, "returnByValue": True, "awaitPromise": False},
        }))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                raw = conn.recv()
            except websocket.WebSocketTimeoutException:
                continue
            msg = json.loads(raw)
            if msg.get("id") != 1:
                continue
            result = msg.get("result", {})
            exc = result.get("exceptionDetails")
            if exc:
                log.error("JS exception: %s", exc)
                sys.exit(1)
            val = result.get("result", {}).get("value")
            if val is None:
                log.error("Runtime.evaluate returned no value")
                sys.exit(1)
            return val
        log.error("Timed out after %.0fs", timeout)
        sys.exit(1)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(
        description="Dump GID→name from Dofus Touch WebView via CDP Runtime.evaluate"
    )
    parser.add_argument("--host", default="localhost",
                        help="DevTools host (default: localhost)")
    parser.add_argument("--port", type=int, default=9222,
                        help="DevTools port, must match adb forward (default: 9222)")
    parser.add_argument("--target-filter", default="dofus",
                        help="Substring to match WebView title/URL (default: dofus)")
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help=f"Output JSON path (default: {DEFAULT_OUT})")
    parser.add_argument("--timeout", type=float, default=30.0,
                        help="Seconds to wait for JS response (default: 30)")
    parser.add_argument("--diagnose", action="store_true",
                        help="Inspect the game's JS structure (use when dump fails)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s — %(message)s",
    )

    if args.diagnose:
        raw = _run_js(args.host, args.port, args.target_filter, _JS_DIAG, args.timeout)
        d = json.loads(raw)
        print("\n=== Diagnostic window.gui ===")
        print(f"  window.gui present : {d.get('hasGui')}")
        print(f"  gui keys           : {d.get('guiKeys')}")
        print(f"  databases keys     : {d.get('databaseKeys')}")
        si = d.get("sampleItem")
        if si:
            print(f"  DB key used        : {si['dbKey']}")
            print(f"  sample item id     : {si['id']}")
            print(f"  sample item fields : {si['fields']}")
        if d.get("error"):
            print(f"  JS error           : {d['error']}")
        return

    n = dump_item_names(
        host=args.host,
        port=args.port,
        target_filter=args.target_filter,
        out_path=Path(args.out),
        timeout=args.timeout,
    )
    print(f"✓ {n:,} noms d'items sauvegardés → {args.out}")
    print("  Relancez analyze.py — les noms apparaîtront dans tous les tableaux.")


if __name__ == "__main__":
    main()
