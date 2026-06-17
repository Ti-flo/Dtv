"""
Primus WebSocket client for Dofus Touch.

Primus is the WebSocket framework used by the game (loaded dynamically
from the game server as /build/primus.js).

Wire format (confirmed from script.js analysis):
  Send:    ws.send(json.dumps({"call": "sendMessage", "data": {"type": NAME, "data": {...}}}))
  Receive: json message with "_messageType" field → {"_messageType": NAME, ...fields...}

Primus heartbeat (must respond or server disconnects after ~30s):
  Receive: "primus::ping::<timestamp>"   (plain string, not JSON)
  Send:    "primus::pong::<timestamp>"
"""
import json
import logging
import threading
from typing import Callable, Optional

import websocket

log = logging.getLogger(__name__)


class PrimusClient:
    """
    Thread-safe Primus WebSocket client.

    Register message handlers with on(), then call connect().
    The client runs its receive loop in a background daemon thread.

    Example:
        client = PrimusClient("wss://dt-proxy-production-login.ankama-games.com/primus")

        @client.on("HelloConnectMessage")
        def handle_hello(msg):
            client.send_message("IdentificationMessage", {...})

        client.connect()
        client.wait_until_closed()
    """

    def __init__(self, url: str):
        self._url = url
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._handlers: dict[str, list[Callable]] = {}
        self._handlers_lock = threading.Lock()
        self._closed = threading.Event()
        self._connected = threading.Event()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def on(self, message_type: str):
        """Decorator to register a handler for a specific message type."""
        def decorator(fn: Callable):
            with self._handlers_lock:
                self._handlers.setdefault(message_type, []).append(fn)
            return fn
        return decorator

    def on_raw(self, fn: Callable):
        """Register a catch-all handler called for every decoded message."""
        with self._handlers_lock:
            self._handlers.setdefault("*", []).append(fn)
        return fn

    def connect(self, wait: bool = False, timeout: float = 15.0):
        """
        Start the WebSocket connection in a background thread.

        Args:
            wait:    If True, block until the connection is open.
            timeout: Max seconds to wait for the open event.
        """
        self._closed.clear()
        self._connected.clear()

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 9; SM-S908E Build/TP1A.220624.014; wv) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/129.0.6668.70 "
                "Safari/537.36 DofusTouch Client 3.11.0"
            ),
            "Origin": "file://",
        }
        self._ws = websocket.WebSocketApp(
            self._url,
            header=headers,
            on_open=self._on_open,
            on_message=self._on_message,
            on_close=self._on_close,
            on_error=self._on_error,
        )
        self._thread = threading.Thread(
            target=self._ws.run_forever,
            kwargs={"ping_interval": 0},  # Primus handles its own pings
            daemon=True,
        )
        self._thread.start()

        if wait:
            if not self._connected.wait(timeout):
                raise TimeoutError(f"WebSocket did not connect within {timeout}s")

    def disconnect(self):
        """Close the WebSocket connection."""
        if self._ws:
            self._ws.close()

    def send_message(self, msg_type: str, data: dict = None):
        """
        Send a game message.
        Wraps in {"call": "sendMessage", "data": {"type": ..., "data": ...}}.
        """
        self._write("sendMessage", {"type": msg_type, "data": data or {}})

    def send_call(self, call: str, data=None):
        """
        Send a raw Primus call (e.g. "login", "connecting", "sendMessage").
        Used for the login flow which uses "login" and "connecting" calls,
        not the standard "sendMessage" call.
        """
        self._write(call, data)

    def wait_until_closed(self, timeout: float = None):
        """Block until the connection is closed."""
        self._closed.wait(timeout)

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _write(self, call: str, data=None):
        if not self._ws:
            raise RuntimeError("Not connected — call connect() first")
        payload = json.dumps({"call": call, "data": data})
        try:
            self._ws.send(payload)
        except websocket.WebSocketConnectionClosedException:
            raise RuntimeError(f"Cannot send '{call}': WebSocket is already closed")
        log.debug("→ %s", call)

    def _on_open(self, ws):
        log.info("WebSocket connected: %s", self._url)
        self._connected.set()
        self._dispatch("__open__", {})

    def _on_close(self, ws, code, reason):
        log.info("WebSocket closed: code=%s reason=%s", code, reason)
        self._closed.set()
        self._dispatch("__close__", {"code": code, "reason": reason})

    def _on_error(self, ws, error):
        log.error("WebSocket error: %s", error)
        self._dispatch("__error__", {"error": error})

    def _on_message(self, ws, raw):
        # Primus heartbeat — respond immediately
        if isinstance(raw, str) and raw.startswith("primus::ping::"):
            ts = raw.split("::", 2)[2]
            ws.send(f"primus::pong::{ts}")
            log.debug("↔ heartbeat pong %s", ts)
            return

        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Non-JSON message received: %r", raw[:100])
            return

        msg_type = msg.get("_messageType") or msg.get("type") or "unknown"
        log.debug("← %s", msg_type)

        self._dispatch("*", msg)
        self._dispatch(msg_type, msg)

    def _dispatch(self, msg_type: str, msg: dict):
        with self._handlers_lock:
            handlers = list(self._handlers.get(msg_type, []))
        for handler in handlers:
            try:
                handler(msg)
            except Exception:
                log.exception("Handler error for %s", msg_type)
