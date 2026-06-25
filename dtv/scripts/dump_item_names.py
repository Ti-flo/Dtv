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

# Deep probe of the game's JS structure — used by --diagnose.
# Dofus Touch loads item templates lazily (not into gui.databases), so we hunt
# for the real store: the module registry, any window-level cache, and the
# player's own inventory (whose items carry resolved names).
_JS_DIAG = r"""
(function() {
  var r = {hasGui: typeof window.gui !== "undefined"};
  function keysOf(o, n) { try { return Object.keys(o).slice(0, n || 60); } catch(e) { return []; } }

  try {
    // 1) Top-level window keys that might hold data managers.
    r.windowKeys = keysOf(window).filter(function(k){
      return /item|data|i18n|cache|content|dofus|iso|manager/i.test(k);
    });

    // 2) gui.databases keys (static reference data only, but list anyway).
    if (window.gui && window.gui.databases) r.databaseKeys = keysOf(window.gui.databases);

    // 3) Module registry — Dofus Touch may use requirejs or browserify.
    r.modules = {kind: null, itemModules: []};
    var ctx = window.require && window.require.s && window.require.s.contexts
              && window.require.s.contexts._;
    if (ctx && ctx.defined) {
      r.modules.kind = "requirejs";
      r.modules.itemModules = keysOf(ctx.defined).filter(function(n){
        return /item|i18n/i.test(n);
      }).slice(0, 40);
    } else if (typeof window.require === "function") {
      r.modules.kind = "require-fn";
    }

    // 4) Player inventory — items here have a resolved name/nameId.
    if (window.gui && window.gui.playerData) {
      r.playerDataKeys = keysOf(window.gui.playerData);
      var inv = window.gui.playerData.inventory;
      if (inv) {
        r.inventoryKeys = keysOf(inv);
        // objects is usually {uid: itemInstance}; itemInstance.item is the template.
        var objs = inv.objects || inv._items || inv.items;
        if (objs) {
          var firstUid = Object.keys(objs)[0];
          if (firstUid) {
            var inst = objs[firstUid];
            r.invSample = {uid: firstUid, instanceFields: keysOf(inst, 25)};
            var tmpl = inst.item || inst.template || inst;
            if (tmpl) {
              r.invSample.templateFields = keysOf(tmpl, 30);
              r.invSample.exampleName = tmpl.name || tmpl.nameId || null;
              r.invSample.exampleId = tmpl.id || tmpl._id || null;
            }
          }
        }
      }
    }

    // 5) Brute scan: any window.gui.databases value whose store looks like items
    //    (large, entries have a nameId). Report the biggest candidate.
    if (window.gui && window.gui.databases) {
      var best = null;
      for (var k in window.gui.databases) {
        var db = window.gui.databases[k];
        var store = db && (db._dataStore || db.dataStore);
        if (!store || typeof store !== "object") continue;
        var ks = Object.keys(store);
        if (ks.length < 50) continue;
        var sample = store[ks[0]];
        var hasName = sample && (typeof sample.name === "string" || "nameId" in sample);
        if (hasName && (!best || ks.length > best.count)) {
          best = {key: k, count: ks.length, sampleFields: keysOf(sample, 20),
                  exampleName: sample.name || ("#" + sample.nameId)};
        }
      }
      r.bestStore = best;
    }

    // 6) HOW does item.name resolve? + how does the client LOAD items by id?
    //    This reveals the i18n function and the lazy item loader.
    function methodsOf(o) {
      var out = [], p = o, depth = 0;
      while (p && depth < 5) {
        Object.getOwnPropertyNames(p).forEach(function(k){
          try { if (typeof o[k] === "function") out.push(k); } catch(e){}
        });
        p = Object.getPrototypeOf(p); depth++;
      }
      return out.filter(function(v,i,a){return a.indexOf(v)===i;}).slice(0, 70);
    }
    r.probe = {};
    try {
      var inv2 = window.gui.playerData.inventory.objects;
      var uid2 = Object.keys(inv2)[0];
      var tmpl2 = inv2[uid2].item;
      r.probe.templateCtor = tmpl2.constructor && tmpl2.constructor.name;
      r.probe.templateCtorStatics = tmpl2.constructor ? keysOf(tmpl2.constructor, 40) : [];
      r.probe.templateMethods = methodsOf(tmpl2);
      // Source of the `name` getter — shows the i18n call.
      var pr = Object.getPrototypeOf(tmpl2), desc = null;
      while (pr && !desc) { desc = Object.getOwnPropertyDescriptor(pr, "name"); pr = Object.getPrototypeOf(pr); }
      r.probe.nameGetterSrc = (desc && desc.get) ? String(desc.get).slice(0, 400) : "(no name getter)";
    } catch(e) { r.probe.errTemplate = String(e); }
    try {
      var dbo = window.gui.databases.ItemTypes;
      r.probe.dbCtor = dbo.constructor && dbo.constructor.name;
      r.probe.dbMethods = methodsOf(dbo);
    } catch(e) { r.probe.errDb = String(e); }
    try {
      r.probe.invManagerMethods = methodsOf(window.gui.playerData.inventoryManager);
    } catch(e) { r.probe.errInvMgr = String(e); }
    // Common global i18n function names.
    r.probe.globals = {
      getText: typeof window.getText,
      i18n: typeof window.i18n,
      processStaticData: typeof window.processStaticData,
    };
  } catch(e) { r.error = String(e) + " | " + String(e.stack || ""); }

  return JSON.stringify(r);
})()
"""

# Reads the SOURCE of getItem/getName so we can confirm getItem is a local
# synchronous lookup (no network) before iterating it over thousands of ids.
# Also does a tiny, safe, bounded test on a few ids.
_JS_SOURCES = r"""
(function() {
  var r = {};
  try {
    var inv = window.gui.playerData.inventory.objects;
    var uids = Object.keys(inv);
    r.invCount = uids.length;
    if (!uids.length) return JSON.stringify({error: "inventory empty — need >=1 item"});

    var t = inv[uids[0]].item;
    r.getItemSrc    = typeof t.getItem    === "function" ? String(t.getItem).slice(0, 600)    : null;
    r.getRawNameSrc = typeof t.getRawName === "function" ? String(t.getRawName).slice(0, 400) : null;
    r.getNameSrc    = typeof t.getName    === "function" ? String(t.getName).slice(0, 400)    : null;
    var ctor = t.constructor;
    r.initListSrc = (ctor && typeof ctor.initializeList === "function")
                    ? String(ctor.initializeList).slice(0, 500) : null;

    // Safe bounded test: own gid + a few well-known low resource gids + a high
    // improbable id (to confirm unknown ids return null synchronously, no hang).
    var ownGid = inv[uids[0]].objectGID || t.id;
    var probeIds = [ownGid, 311, 312, 289, 1, 99999];
    r.tests = {};
    probeIds.forEach(function(id){
      try {
        var it = t.getItem(id);
        if (!it) { r.tests[id] = null; return; }
        var nm = (typeof it.getRawName === "function") ? it.getRawName()
               : (typeof it.getName === "function") ? it.getName()
               : (it.name || "?");
        r.tests[id] = nm;
      } catch(e) { r.tests[id] = "ERR:" + e; }
    });
  } catch(e) { r.error = String(e) + " | " + String(e.stack || ""); }
  return JSON.stringify(r);
})()
"""


# Hunt for the real item registry: ALL statics on the Item constructor (incl.
# non-enumerable), their sources, and any large {id: {nameId}} map reachable
# from window / window.gui. nameId already holds the resolved name string.
_JS_FIND = r"""
(function() {
  var r = {};
  function names(o, n) { try { return Object.getOwnPropertyNames(o).slice(0, n || 100); } catch(e) { return []; } }
  try {
    var inv = window.gui.playerData.inventory.objects;
    var t = inv[Object.keys(inv)[0]].item;
    var ctor = t.constructor;

    // ALL statics on the constructor (own names, incl. non-enumerable).
    r.ctorStatics = names(ctor, 100);
    r.staticSrcs = {};
    r.staticBigMaps = {};
    names(ctor, 100).forEach(function(k){
      try {
        var v = ctor[k];
        if (typeof v === "function") {
          r.staticSrcs[k] = String(v).slice(0, 180);
        } else if (v && typeof v === "object") {
          var ck = Object.keys(v);
          // A big map keyed by numeric ids whose values have nameId = the list.
          if (ck.length > 100) {
            var s = v[ck[0]];
            r.staticBigMaps[k] = {count: ck.length,
              sampleKey: ck[0],
              sampleNameId: s && s.nameId,
              sampleFields: s && typeof s === "object" ? Object.keys(s).slice(0,12) : typeof s};
          }
        }
      } catch(e){}
    });

    r.getItemInstanceSrc = (typeof t.getItemInstance === "function") ? String(t.getItemInstance).slice(0, 300) : null;
    r.getPropertySrc     = (typeof t.getProperty     === "function") ? String(t.getProperty).slice(0, 300)     : null;

    // Broad listing to spot a data manager we filtered out before.
    r.windowKeys = Object.keys(window).slice(0, 160);
    r.guiAllKeys = Object.keys(window.gui).slice(0, 90);
    var w = window.gui.windowsList || window.gui.windows;
    r.guiWindowKeys = w ? Object.keys(w).slice(0, 100) : null;
  } catch(e) { r.error = String(e) + " | " + String(e.stack || ""); }
  return JSON.stringify(r);
})()
"""


# Read window.Config (CDN/data URLs) so we can fetch the item data file the
# client downloads at login — the full id→name source, fetched without
# touching the game server.
_JS_CONFIG = r"""
(function() {
  var r = {};
  function flat(o, prefix, out, depth) {
    if (depth > 2) return;
    for (var k in o) {
      try {
        var v = o[k];
        var key = prefix ? prefix + "." + k : k;
        if (v == null) continue;
        if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
          out[key] = v;
        } else if (typeof v === "object" && depth < 2) {
          flat(v, key, out, depth + 1);
        }
      } catch(e){}
    }
  }
  try {
    r.hasConfig = typeof window.Config;
    if (window.Config) {
      r.config = {};
      flat(window.Config, "", r.config, 0);
      // Keep only entries that look like URLs / paths / versions (avoid noise).
      var filtered = {};
      for (var k in r.config) {
        var v = String(r.config[k]);
        if (/url|uri|host|cdn|path|version|assets|data|lang|server/i.test(k)
            || /^https?:|^\/\/|\.json|\.swf|\/data\//i.test(v)) {
          filtered[k] = r.config[k];
        }
      }
      r.urlish = filtered;
    }
    // Other possibly-useful globals.
    r.globals = {
      Config: typeof window.Config,
      dataManager: typeof window.dataManager,
      require: typeof window.require,
    };
  } catch(e) { r.error = String(e); }
  return JSON.stringify(r);
})()
"""

# Test candidate data-file URLs by fetching them FROM the WebView (same origin
# as the asset CDN, so no CORS). Hits only the static asset CDN, never the game
# server. Returns which URLs respond + a sample so we find the items data file.
# Runs as a Promise → call _run_js(..., await_promise=True).
_JS_FETCH_TEST = r"""
(function() {
  var base = window.Config.assetsUrl;
  var lang = window.Config.language || "en";
  var paths = [
    "/data/Items.json",
    "/data/" + lang + "/Items.json",
    "/data/items.json",
    "/data/Items_0.json",
    "/data/Items/0.json",
    "/data/i18n/i18n_" + lang + ".json",
    "/data/i18n_" + lang + ".json",
    "/data/" + lang + "/i18n.json",
    "/data/ItemTypes.json",
    "/data/" + lang + "/ItemTypes.json",
    "/data/index.json",
    "/data/filemap.json",
    "/data/manifest.json"
  ];
  var urls = paths.map(function(p){ return base + p; });
  return Promise.all(urls.map(function(u){
    return fetch(u).then(function(res){
      if (!res.ok) return {url: u, status: res.status};
      return res.text().then(function(t){
        return {url: u, status: res.status, len: t.length, head: t.slice(0, 160)};
      });
    }).catch(function(e){ return {url: u, err: String(e) }; });
  })).then(function(results){
    return JSON.stringify({base: base, lang: lang, results: results});
  });
})()
"""

# List the URLs the client ACTUALLY loaded (definitive — no guessing). Reveals
# the real data-file paths (or file://android_asset/ if data ships in the APK).
_JS_RESOURCES = r"""
(function() {
  var r = {};
  try {
    var entries = (performance.getEntriesByType("resource") || []).map(function(e){ return e.name; });
    r.total = entries.length;
    r.dataUrls = entries.filter(function(u){
      return /\/data\/|item|i18n|\.json|\.jar|\.d2o|assetmap|filemap|manifest/i.test(u);
    }).slice(0, 120);
    // Distinct path prefixes to understand the layout.
    var prefixes = {};
    entries.forEach(function(u){
      var m = u.replace(/^https?:\/\/[^/]+/, "").split("?")[0];
      var parts = m.split("/"); parts.pop();
      var pre = parts.slice(0, 5).join("/");
      prefixes[pre] = (prefixes[pre] || 0) + 1;
    });
    r.prefixes = prefixes;
    r.sample = entries.slice(0, 30);
  } catch(e) { r.error = String(e); }
  return JSON.stringify(r);
})()
"""

# Fetch the data-proxy text/dictionary endpoints (versioned static data the
# client loads at boot) and report their structure so we can see which holds
# item names. Runs as a Promise → _run_js(..., await_promise=True).
_JS_FETCH_DATA = r"""
(function() {
  var data  = window.Config.dataUrl;  // e.g. dt-proxy-production-canada
  var login = "https://dt-proxy-production-login.ankama-games.com";
  var lang  = window.Config.language || "en";
  var v     = "1.72.12";
  var urls = {
    text:       data  + "/data/text?lang=" + lang + "&v=" + v,
    dictionary: login + "/data/dictionary?lang=" + lang + "&v=" + v
  };
  function probe(u){
    return fetch(u).then(function(res){
      if (!res.ok) return {status: res.status};
      return res.text().then(function(t){
        var info = {status: 200, len: t.length, head: t.slice(0, 160)};
        try {
          var j = JSON.parse(t);
          info.type = Array.isArray(j) ? "array" : typeof j;
          if (j && typeof j === "object") {
            var ks = Object.keys(j);
            info.count = ks.length;
            info.topKeys = ks.slice(0, 15);
            info.sample = {};
            ks.slice(0, 6).forEach(function(k){
              var val = j[k];
              info.sample[k] = (val && typeof val === "object")
                ? "[obj:" + Object.keys(val).slice(0, 8).join(",") + "]"
                : String(val).slice(0, 50);
            });
          }
        } catch(e) { info.parseErr = String(e).slice(0, 80); }
        return info;
      });
    }).catch(function(e){ return {err: String(e)}; });
  }
  return Promise.all([probe(urls.text), probe(urls.dictionary)]).then(function(res){
    return JSON.stringify({urls: urls, text: res[0], dictionary: res[1]});
  });
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


def _run_js(host: str, port: int, target_filter: str, js: str, timeout: float,
            await_promise: bool = False) -> str:
    """Connect to CDP, evaluate js, return the raw string value."""
    ws_url = _discover_ws_url(host, port, target_filter)
    log.info("Connecting to %s", ws_url)
    conn = websocket.create_connection(ws_url, timeout=timeout)
    try:
        conn.send(json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {"expression": js, "returnByValue": True,
                       "awaitPromise": await_promise},
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
    parser.add_argument("--sources", action="store_true",
                        help="Print getItem/getName source + a safe id test (no network)")
    parser.add_argument("--find", action="store_true",
                        help="Hunt for the real item registry (statics + big maps)")
    parser.add_argument("--config", action="store_true",
                        help="Read window.Config — CDN/data URLs for the item data file")
    parser.add_argument("--probe-data", action="store_true",
                        help="Fetch-test candidate data-file URLs from the WebView (asset CDN only)")
    parser.add_argument("--resources", action="store_true",
                        help="List URLs the client actually loaded (find real data paths)")
    parser.add_argument("--probe-text", action="store_true",
                        help="Fetch + inspect the data-proxy text/dictionary endpoints")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s — %(message)s",
    )

    if args.probe_text:
        raw = _run_js(args.host, args.port, args.target_filter, _JS_FETCH_DATA,
                      args.timeout, await_promise=True)
        d = json.loads(raw)
        print("\n=== Inspection text / dictionary ===")
        for label in ("text", "dictionary"):
            info = d.get(label) or {}
            print(f"\n  [{label}]  {d.get('urls', {}).get(label, '')}")
            if info.get("err"):
                print(f"    ERREUR : {info['err']}")
            elif info.get("status") != 200:
                print(f"    HTTP {info.get('status')}")
            else:
                print(f"    taille  : {info.get('len'):,} octets   type: {info.get('type')}   "
                      f"entrées: {info.get('count')}")
                print(f"    head    : {info.get('head')}")
                print(f"    topKeys : {info.get('topKeys')}")
                print(f"    sample  : {info.get('sample')}")
                if info.get("parseErr"):
                    print(f"    parseErr: {info['parseErr']}")
        print()
        return

    if args.resources:
        raw = _run_js(args.host, args.port, args.target_filter, _JS_RESOURCES, args.timeout)
        d = json.loads(raw)
        print("\n=== URLs réellement chargées par le client ===")
        if d.get("error"):
            print(f"  ERREUR : {d['error']}")
            return
        print(f"  total resources     : {d.get('total')}")
        print("  --- préfixes de chemins (compte) ---")
        for pre, n in sorted((d.get("prefixes") or {}).items(), key=lambda x: -x[1]):
            print(f"    {n:>4}  {pre}")
        print("  --- URLs data / item / i18n / json ---")
        for u in d.get("dataUrls", []):
            print(f"    {u}")
        if not d.get("dataUrls"):
            print("    (aucune — les données sont peut-être dans l'APK. Échantillon :)")
            for u in d.get("sample", []):
                print(f"    {u}")
        print()
        return

    if args.probe_data:
        raw = _run_js(args.host, args.port, args.target_filter, _JS_FETCH_TEST,
                      args.timeout, await_promise=True)
        d = json.loads(raw)
        print("\n=== Test des URLs de données (CDN assets) ===")
        print(f"  base : {d.get('base')}   lang : {d.get('lang')}")
        for res in d.get("results", []):
            u = res.get("url", "")
            tail = u.split("/assets/", 1)[-1] if "/assets/" in u else u
            if res.get("status") == 200:
                print(f"  ✓ 200  len={res.get('len'):>9}  …/{tail}")
                print(f"         head: {res.get('head')}")
            elif res.get("err"):
                print(f"  ✗ ERR  …/{tail}  ({res['err']})")
            else:
                print(f"  ✗ {res.get('status')}  …/{tail}")
        print()
        return

    if args.config:
        raw = _run_js(args.host, args.port, args.target_filter, _JS_CONFIG, args.timeout)
        d = json.loads(raw)
        print("\n=== window.Config — URLs de données ===")
        if d.get("error"):
            print(f"  ERREUR : {d['error']}")
            return
        print(f"  globals             : {d.get('globals')}")
        urlish = d.get("urlish") or {}
        if urlish:
            print("  --- entrées URL / data / version ---")
            for k, v in urlish.items():
                print(f"    {k} = {v}")
        else:
            print("  (window.Config absent ou sans URL — colle le bloc ci-dessus)")
        print()
        return

    if args.find:
        raw = _run_js(args.host, args.port, args.target_filter, _JS_FIND, args.timeout)
        d = json.loads(raw)
        print("\n=== Recherche du registre d'items ===")
        if d.get("error"):
            print(f"  ERREUR : {d['error']}")
            return
        print(f"  ctor statics        : {d.get('ctorStatics')}")
        print("  --- sources des statics ---")
        for k, v in (d.get("staticSrcs") or {}).items():
            print(f"    {k} = {v}")
        bigmaps = d.get("staticBigMaps") or {}
        if bigmaps:
            print("  >>> GROS MAPS STATIQUES (candidats registre) :")
            for k, v in bigmaps.items():
                print(f"    ctor.{k}: {v}")
        print(f"\n  getItemInstance src : {d.get('getItemInstanceSrc')}")
        print(f"  getProperty src     : {d.get('getPropertySrc')}")
        print(f"\n  window keys         : {d.get('windowKeys')}")
        print(f"\n  gui keys            : {d.get('guiAllKeys')}")
        print(f"\n  gui.windows keys    : {d.get('guiWindowKeys')}")
        print()
        return

    if args.sources:
        raw = _run_js(args.host, args.port, args.target_filter, _JS_SOURCES, args.timeout)
        d = json.loads(raw)
        print("\n=== Sources getItem / getName ===")
        if d.get("error"):
            print(f"  ERREUR : {d['error']}")
            return
        print(f"  items en inventaire : {d.get('invCount')}")
        print(f"\n  getItem source :\n    {d.get('getItemSrc')}")
        print(f"\n  getRawName source :\n    {d.get('getRawNameSrc')}")
        print(f"\n  getName source :\n    {d.get('getNameSrc')}")
        print(f"\n  initializeList source :\n    {d.get('initListSrc')}")
        print(f"\n  tests getItem(id) → nom :")
        for k, v in (d.get("tests") or {}).items():
            print(f"    {k:>6} → {v!r}")
        print()
        return

    if args.diagnose:
        raw = _run_js(args.host, args.port, args.target_filter, _JS_DIAG, args.timeout)
        d = json.loads(raw)
        print("\n=== Sonde structure JS Dofus Touch ===")
        print(f"  window.gui present  : {d.get('hasGui')}")
        print(f"  window keys (data)  : {d.get('windowKeys')}")
        print(f"  databases keys      : {d.get('databaseKeys')}")
        mods = d.get("modules") or {}
        print(f"  module system       : {mods.get('kind')}")
        print(f"  item/i18n modules   : {mods.get('itemModules')}")
        print(f"  playerData keys     : {d.get('playerDataKeys')}")
        print(f"  inventory keys      : {d.get('inventoryKeys')}")
        inv = d.get("invSample")
        if inv:
            print(f"  inv instance fields : {inv.get('instanceFields')}")
            print(f"  inv template fields : {inv.get('templateFields')}")
            print(f"  inv example name    : {inv.get('exampleName')!r} (id={inv.get('exampleId')})")
        best = d.get("bestStore")
        if best:
            print(f"  >>> STORE TROUVÉ    : databases.{best['key']} "
                  f"({best['count']} entrées)")
            print(f"      champs          : {best['sampleFields']}")
            print(f"      exemple nom     : {best['exampleName']!r}")
        p = d.get("probe") or {}
        if p:
            print("  --- résolution nom / chargement items ---")
            print(f"  template class      : {p.get('templateCtor')}")
            print(f"  template statics    : {p.get('templateCtorStatics')}")
            print(f"  template methods    : {p.get('templateMethods')}")
            print(f"  name getter source  : {p.get('nameGetterSrc')}")
            print(f"  ItemTypes db class  : {p.get('dbCtor')}")
            print(f"  ItemTypes db methods: {p.get('dbMethods')}")
            print(f"  invManager methods  : {p.get('invManagerMethods')}")
            print(f"  globals i18n        : {p.get('globals')}")
            for ek in ("errTemplate", "errDb", "errInvMgr"):
                if p.get(ek):
                    print(f"  {ek:18}: {p[ek]}")
        if d.get("error"):
            print(f"  JS error            : {d['error']}")
        print()
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
