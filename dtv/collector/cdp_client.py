"""
Chrome DevTools Protocol (CDP) WebSocket-frame listener.

This is the PASSIVE capture path: instead of running our own bot, we attach to
the real Dofus Touch client's WebView (running on a rooted phone, exposed over
wireless ADB) exactly like Chrome DevTools does, and read the WebSocket frames
the client has ALREADY decrypted for itself.

Why this is the safest possible capture:
  - The client talks to Ankama with its own native TLS — we never intercept or
    re-encrypt anything (no mitmproxy, no JA3 change).
  - Heartbeats, Logstash telemetry, sequence numbers — all sent by the genuine
    client. There is no synthetic traffic to fingerprint.
  - CDP is a purely LOCAL debug channel (phone ↔ mini PC over WireGuard). Ankama
    cannot observe that a debugger is attached.

How it works:
  1. `adb forward` exposes the WebView's devtools socket on a local TCP port.
  2. GET http://localhost:<port>/json lists the inspectable pages; we pick the
     Dofus Touch WebView and read its webSocketDebuggerUrl.
  3. We open that CDP WebSocket, send Network.enable, and stream the
     Network.webSocketFrameReceived / webSocketFrameSent events. Each event's
     `response.payloadData` is one raw Primus frame (the JSON we want).

Robustness:
  - If the WebView disappears (game closed) the CDP socket drops; we re-discover
    and re-attach automatically. Frames sent BEFORE we attach are not replayed,
    so the listener is meant to run continuously, attached before login.
"""
import json
import logging
import threading
import time
import urllib.request
from typing import Callable, Optional

import websocket

log = logging.getLogger(__name__)

# CDP frame events. Both carry the frame under params.response.payloadData;
# `mask` distinguishes nothing useful here — direction is the event name.
_EVT_RECV = "Network.webSocketFrameReceived"
_EVT_SENT = "Network.webSocketFrameSent"
_EVT_CREATED = "Network.webSocketCreated"

# opcode 1 = text frame (JSON). 2 = binary (unused by DT). Control opcodes >7.
_OPCODE_TEXT = 1


class CDPClient:
    """
    Attaches to a WebView via CDP and streams its WebSocket frames.

    Usage:
        client = CDPClient(port=9222, target_filter="dofus")
        client.on_frame(lambda direction, payload, ws_url: ...)
        client.run_forever()        # blocks; reconnects until stop() is called
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 9222,
        target_filter: Optional[str] = None,
        recv_timeout: float = 5.0,
        reconnect_delay: float = 3.0,
    ):
        """
        target_filter: case-insensitive substring matched against each target's
            url+title. None → pick the first inspectable page that has a
            webSocketDebuggerUrl (fine when only Dofus Touch is debuggable).
        recv_timeout: how often the recv loop wakes to check the stop flag.
        reconnect_delay: pause before re-discovering the target after a drop.
        """
        self._host = host
        self._port = port
        self._target_filter = (target_filter or "").lower()
        self._recv_timeout = recv_timeout
        self._reconnect_delay = reconnect_delay

        self._frame_cb: Optional[Callable[[str, str, str], None]] = None
        self._stop = threading.Event()
        self._cmd_id = 0
        # requestId → ws URL, learned from webSocketCreated, so the frame callback
        # can tell the login socket from the game socket.
        self._ws_urls: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #

    def on_frame(self, callback: Callable[[str, str, str], None]):
        """
        Register the frame callback: callback(direction, payload, ws_url).
          direction: "recv" (server→client) or "sent" (client→server)
          payload:   the raw WebSocket text frame (a Primus JSON string)
          ws_url:    the WebSocket URL the frame belongs to (login vs game)
        """
        self._frame_cb = callback

    def stop(self):
        """Signal the run loop to exit after the current recv wakes up."""
        self._stop.set()

    def list_targets(self) -> list[dict]:
        """Return the raw /json target list from the devtools endpoint."""
        url = f"http://{self._host}:{self._port}/json"
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def run_forever(self):
        """
        Discover the target, attach, and stream frames until stop() is called.
        Re-attaches automatically if the WebView (and thus the CDP socket) drops.
        """
        while not self._stop.is_set():
            ws_debugger_url = self._discover_target()
            if not ws_debugger_url:
                log.warning("No debuggable Dofus Touch WebView found on %s:%d — "
                            "is the game open and `adb forward` set up? Retrying in %.0fs",
                            self._host, self._port, self._reconnect_delay)
                self._stop.wait(self._reconnect_delay)
                continue
            try:
                self._attach_and_stream(ws_debugger_url)
            except (websocket.WebSocketException, OSError) as e:
                if not self._stop.is_set():
                    log.warning("CDP connection lost (%s) — will re-attach in %.0fs",
                                e, self._reconnect_delay)
                    self._stop.wait(self._reconnect_delay)

    # ------------------------------------------------------------------ #
    # Internal                                                            #
    # ------------------------------------------------------------------ #

    def _discover_target(self) -> Optional[str]:
        """Pick the Dofus Touch WebView and return its webSocketDebuggerUrl."""
        try:
            targets = self.list_targets()
        except (OSError, json.JSONDecodeError) as e:
            log.debug("Target discovery failed: %s", e)
            return None

        candidates = [
            t for t in targets
            if t.get("webSocketDebuggerUrl")
            and t.get("type", "page") in ("page", "webview", "app")
        ]
        if self._target_filter:
            candidates = [
                t for t in candidates
                if self._target_filter in (t.get("url", "") + t.get("title", "")).lower()
            ]

        if not candidates:
            return None
        if len(candidates) > 1:
            log.info("Multiple debuggable targets (%d) — using the first. "
                     "Pass --target-filter to disambiguate. Titles: %s",
                     len(candidates), [t.get("title") for t in candidates])

        chosen = candidates[0]
        log.info("Attaching to WebView: title=%r url=%r",
                 chosen.get("title"), chosen.get("url"))
        return chosen["webSocketDebuggerUrl"]

    def _next_id(self) -> int:
        self._cmd_id += 1
        return self._cmd_id

    def _attach_and_stream(self, ws_debugger_url: str):
        """Open the CDP socket, enable Network, and dispatch frames."""
        self._ws_urls.clear()
        conn = websocket.create_connection(
            ws_debugger_url,
            timeout=self._recv_timeout,
        )
        try:
            conn.send(json.dumps({"id": self._next_id(), "method": "Network.enable"}))
            log.info("CDP attached — Network domain enabled, streaming frames")

            while not self._stop.is_set():
                try:
                    raw = conn.recv()
                except websocket.WebSocketTimeoutException:
                    continue  # periodic wake to check the stop flag
                if not raw:
                    continue
                self._handle_cdp_message(raw)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _handle_cdp_message(self, raw: str):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        method = msg.get("method")
        if method == _EVT_CREATED:
            params = msg.get("params", {})
            req_id = params.get("requestId")
            if req_id:
                self._ws_urls[req_id] = params.get("url", "")
            return

        if method not in (_EVT_RECV, _EVT_SENT):
            return

        params = msg.get("params", {})
        response = params.get("response", {})
        # Only text frames carry game JSON; skip binary/control opcodes.
        if response.get("opcode") != _OPCODE_TEXT:
            return
        payload = response.get("payloadData")
        if not payload:
            return

        direction = "recv" if method == _EVT_RECV else "sent"
        ws_url = self._ws_urls.get(params.get("requestId"), "")
        if self._frame_cb:
            try:
                self._frame_cb(direction, payload, ws_url)
            except Exception:
                log.exception("Frame callback error (direction=%s)", direction)
