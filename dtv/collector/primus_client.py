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

Server-initiated close:
  Receive: "primus::server::close"  (kick, maintenance, session invalidated)
  → do NOT reconnect on this signal
"""
import enum
import json
import logging
import threading
import time
from typing import Callable, Optional

import websocket

log = logging.getLogger(__name__)

# Server sends a ping every ~30s. Two missed pings → connection is dead.
PING_TIMEOUT_S = 65.0


class DisconnectReason(enum.Enum):
    CLIENT_CLOSE = "client_close"   # we called disconnect()
    SERVER_CLOSE = "server_close"   # primus::server::close received (kick/maintenance)
    PING_TIMEOUT = "ping_timeout"   # no ping from server for PING_TIMEOUT_S
    TCP_DROP = "tcp_drop"           # raw TCP/TLS close, no Primus signal


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
        # Disconnect reason tracking — reset on each connect()
        self._intentional_close = False
        self._server_closed = False
        self._ping_timeout_triggered = False
        self._last_ping_at: float = 0.0
        self.disconnect_reason: Optional[DisconnectReason] = None

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
        self._intentional_close = False
        self._server_closed = False
        self._ping_timeout_triggered = False
        self._last_ping_at = 0.0
        self.disconnect_reason = None

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

        threading.Thread(target=self._heartbeat_watchdog, daemon=True).start()

        if wait:
            if not self._connected.wait(timeout):
                raise TimeoutError(f"WebSocket did not connect within {timeout}s")

    def disconnect(self):
        """Close the WebSocket connection."""
        self._intentional_close = True
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

    def _heartbeat_watchdog(self):
        """Background thread: detect if the server stops sending pings."""
        while not self._closed.wait(10.0):  # wakes immediately if closed
            if self._last_ping_at > 0:
                elapsed = time.time() - self._last_ping_at
                if elapsed > PING_TIMEOUT_S:
                    log.warning("Heartbeat timeout (%.0fs since last ping) — closing", elapsed)
                    self._ping_timeout_triggered = True
                    if self._ws:
                        self._ws.close()
                    break

    def _on_open(self, ws):
        log.info("WebSocket connected: %s", self._url)
        self._connected.set()
        self._dispatch("__open__", {})

    def _on_close(self, ws, code, reason):
        if self._intentional_close:
            r = DisconnectReason.CLIENT_CLOSE
        elif self._server_closed:
            r = DisconnectReason.SERVER_CLOSE
        elif self._ping_timeout_triggered:
            r = DisconnectReason.PING_TIMEOUT
        else:
            r = DisconnectReason.TCP_DROP

        self.disconnect_reason = r
        log.info("WebSocket closed [%s]: code=%s reason=%s", r.value, code, reason)
        self._closed.set()
        self._dispatch("__close__", {"code": code, "reason": reason, "disconnect_reason": r})

    def _on_error(self, ws, error):
        log.error("WebSocket error: %s", error)
        self._dispatch("__error__", {"error": error})

    def _on_message(self, ws, raw):
        # Primus heartbeat — respond immediately and track time for watchdog
        if isinstance(raw, str) and raw.startswith("primus::ping::"):
            ts = raw.split("::", 2)[2]
            ws.send(f"primus::pong::{ts}")
            self._last_ping_at = time.time()
            log.debug("↔ heartbeat pong %s", ts)
            return

        # Server-initiated close (kick, maintenance, session expired)
        if raw == "primus::server::close":
            log.info("primus::server::close received")
            self._server_closed = True
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
