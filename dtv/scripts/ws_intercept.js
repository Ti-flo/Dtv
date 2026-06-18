/* DTV WebSocket interceptor
 *
 * Prepended to script.js on the device — executes BEFORE Ankama Shield.
 *
 * Design choices:
 *   - Proxy instead of function replacement: keeps WebSocket.prototype, .name,
 *     .toString() intact so Shield's prototype/toString checks pass.
 *   - Object.defineProperty with writable:true so Shield can still overwrite
 *     window.WebSocket later — doesn't matter, we hook at the instance level.
 *   - Reflect.construct preserves the prototype chain exactly like `new WebSocket()`.
 *   - Native fetch saved immediately so Shield can't intercept our log POSTs.
 *   - Instance-level hooks (ws.send, addEventListener) survive Shield overwriting
 *     window.WebSocket after our Proxy runs.
 *
 * CONFIG: set MODE below before patching.
 *   'logcat' — console.log only, no network, read with:
 *              adb logcat | grep "\[DTV\]"
 *   'fetch'  — POST JSON to Python server on host (10.0.2.2:8765)
 *              run: python -m dtv.scripts.ws_capture_server
 */
(function () {
    var MODE = 'logcat';           // 'logcat' | 'fetch'
    var FETCH_HOST = 'http://10.0.2.2:8765';
    var TAG = '[DTV]';
    var CHUNK = 800;               // logcat line length safety margin

    // Save native fetch NOW before Shield can replace it
    var _fetch = (typeof fetch !== 'undefined') ? fetch.bind(window) : null;

    function emit(dir, data) {
        var entry = JSON.stringify({ t: dir, ts: Date.now(), d: data });
        if (MODE === 'fetch' && _fetch) {
            _fetch(FETCH_HOST + '/log', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: entry
            }).catch(function () {});
        } else {
            // Split to avoid logcat line truncation
            for (var i = 0; i < entry.length; i += CHUNK) {
                console.log(TAG + entry.slice(i, i + CHUNK));
            }
        }
    }

    Object.defineProperty(window, 'WebSocket', {
        value: new Proxy(WebSocket, {
            construct: function (Target, args) {
                emit('url', args[0]);
                // Reflect.construct: identical behaviour to `new Target(args[0], args[1])`
                // but correctly sets up prototype chain without triggering any native check
                var ws = Reflect.construct(Target, args);

                // Patch at instance level — persists even if Shield replaces window.WebSocket
                var _send = ws.send.bind(ws);
                ws.send = function (d) {
                    if (typeof d === 'string') emit('out', d);
                    return _send(d);
                };
                ws.addEventListener('message', function (e) {
                    if (typeof e.data === 'string') emit('in', e.data);
                });
                return ws;
            }
        }),
        writable: true,
        configurable: true,
        enumerable: true
    });

    console.log(TAG + JSON.stringify({ t: 'init', mode: MODE }));
})();
