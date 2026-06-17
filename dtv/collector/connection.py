"""
Dofus Touch connection manager.

Orchestrates the full login flow:
  1. Connect to login server (Primus WebSocket)
  2. Authenticate with game token
  3. Select server
  4. Connect to game server (Primus WebSocket)
  5. Select character
  6. Emit game-ready event → HDV collection can start

Architecture confirmed from script.js + PCAPdroid captures:
  Login server:  dt-proxy-production-login.ankama-games.com  (TCP → TLS)
  Game server:   dt-proxy-production-france.ankama-games.com (TCP → TLS)
  Protocol:      Primus WebSocket, JSON messages
"""
import logging
import threading
from typing import Optional

from curl_cffi import requests

from .primus_client import PrimusClient

log = logging.getLogger(__name__)

# Default login server (from script.js: window.appInfo.server fallback)
LOGIN_SERVER = "https://dt-proxy-production-login.ankama-games.com"

# Primus endpoint path — TODO: verify by fetching /build/primus.js
# Standard Primus default is /primus; some servers use root or custom path
PRIMUS_PATH = "/primus"


def _get_config(server_url: str, lang: str = "fr") -> dict:
    """
    Fetch game config from the login server.
    Returns URLs for game servers, assets CDN, etc.
    Called before auth — no credentials needed.
    """
    url = f"{server_url}/config.json"
    resp = requests.get(url, params={"lang": lang}, impersonate="chrome_android", timeout=15)
    resp.raise_for_status()
    return resp.json()


class DofusTouchSession:
    """
    Manages a full Dofus Touch session from auth to in-game.

    Usage:
        session = DofusTouchSession(game_token="...", server_id=401, character_id=123)
        session.connect()
        # game_ready event fires → use session.game to send messages
        session.wait_for_game(timeout=60)
        # Now in game, can use session.send_message(...)
        session.disconnect()
    """

    def __init__(
        self,
        game_token: str,
        server_id: int,
        character_id: Optional[int] = None,  # None = pick first character
        lang: str = "fr",
        login_server: str = LOGIN_SERVER,
    ):
        self.game_token = game_token
        self.server_id = server_id
        self.character_id = character_id
        self.lang = lang
        self.login_server = login_server

        self._login_client: Optional[PrimusClient] = None
        self._game_client: Optional[PrimusClient] = None
        self._game_ready = threading.Event()
        self._error: Optional[str] = None
        self._message_handlers: dict = {}

        # State built up during the login flow
        self._servers: list = []
        self._characters: list = []
        self._game_server_url: Optional[str] = None
        self._ticket: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def on(self, message_type: str):
        """Decorator to register a handler for in-game messages."""
        def decorator(fn):
            self._message_handlers.setdefault(message_type, []).append(fn)
            if self._game_client:
                self._game_client.on(message_type)(fn)
            return fn
        return decorator

    def send_message(self, msg_type: str, data: dict = None):
        """Send a game message (must be called after wait_for_game)."""
        if not self._game_client:
            raise RuntimeError("Not connected to game server yet")
        self._game_client.send_message(msg_type, data)

    def connect(self):
        """Start the login flow (non-blocking, runs in background threads)."""
        config = _get_config(self.login_server, self.lang)
        log.info("Config loaded. dataUrl=%s", config.get("dataUrl"))

        login_ws_url = self.login_server.replace("https://", "wss://").replace("http://", "ws://")
        login_ws_url += PRIMUS_PATH

        log.info("Connecting to login server: %s", login_ws_url)
        self._login_client = PrimusClient(login_ws_url)
        self._setup_login_handlers()
        self._login_client.connect(wait=True, timeout=15)

    def wait_for_game(self, timeout: float = 90.0) -> bool:
        """
        Block until the game is fully loaded and character is in-game.
        Returns True if ready within timeout, False otherwise.
        Raises RuntimeError immediately if authentication was refused.
        """
        ready = self._game_ready.wait(timeout)
        if not ready and self._error:
            raise RuntimeError(f"Connection failed: {self._error}")
        return ready

    def disconnect(self):
        """Close all connections."""
        if self._game_client:
            self._game_client.disconnect()
        if self._login_client:
            self._login_client.disconnect()

    # ------------------------------------------------------------------ #
    # Login server handlers                                               #
    # ------------------------------------------------------------------ #

    def _setup_login_handlers(self):
        c = self._login_client

        @c.on("__open__")
        def on_open(msg):
            # Primus "connecting" call sent on socket open (from script.js)
            log.info("Login socket open → sending 'connecting'")
            c.send_call("connecting", self._build_identification_data())

        @c.on("HelloConnectMessage")
        def on_hello(msg):
            # Server sends salt+key for the login call
            log.info("HelloConnectMessage received")
            ident = self._build_identification_data()
            ident["salt"] = msg.get("salt", "")
            ident["key"] = msg.get("key", "")
            c.send_call("login", ident)

        @c.on("IdentificationSuccessMessage")
        @c.on("IdentificationSuccessWithLoginTokenMessage")
        def on_ident_success(msg):
            log.info("Identification success. nick=%s", msg.get("uniqueNickname"))
            # The login token for the game server is in this message
            self._ticket = msg.get("login_token") or msg.get("loginToken")

        @c.on("ServersListMessage")
        def on_servers(msg):
            self._servers = msg.get("servers", [])
            log.info("Servers list received (%d servers)", len(self._servers))
            log.info("Selecting server id=%d", self.server_id)
            c.send_message("ServerSelectionMessage", {"serverId": self.server_id})

        @c.on("SelectedServerDataMessage")
        def on_server_selected(msg):
            log.info("Server selected: %s", msg)
            # msg contains the game server address
            host = msg.get("address") or msg.get("ip") or msg.get("host")
            port = msg.get("port", 443)
            ticket = msg.get("ticket") or self._ticket or self.game_token

            self._ticket = ticket
            # Build game server WebSocket URL
            if host:
                self._game_server_url = f"wss://{host}:{port}{PRIMUS_PATH}"
            else:
                # Fallback: try default France game server
                log.warning("No host in SelectedServerDataMessage, using default game server")
                self._game_server_url = (
                    f"wss://dt-proxy-production-france.ankama-games.com{PRIMUS_PATH}"
                )

            log.info("Connecting to game server: %s", self._game_server_url)
            self._login_client.disconnect()
            self._connect_to_game_server()

        @c.on("IdentificationFailedMessage")
        @c.on("IdentificationFailedBannedMessage")
        @c.on("IdentificationFailedForBadVersionMessage")
        def on_ident_failed(msg):
            reason = msg.get("reason") or msg.get("_messageType", "unknown")
            log.error("Identification failed: %s", reason)
            self._error = reason
            self._game_ready.set()  # unblock wait_for_game() immediately

    def _build_identification_data(self) -> dict:
        return {
            "token": self.game_token,
            "lang": self.lang,
            "autoSelectServer": False,
        }

    # ------------------------------------------------------------------ #
    # Game server handlers                                                #
    # ------------------------------------------------------------------ #

    def _connect_to_game_server(self):
        self._game_client = PrimusClient(self._game_server_url)
        self._setup_game_handlers()

        # Register any user-provided handlers
        for msg_type, handlers in self._message_handlers.items():
            for handler in handlers:
                self._game_client.on(msg_type)(handler)

        self._game_client.connect(wait=True, timeout=15)

    def _setup_game_handlers(self):
        c = self._game_client
        ticket = self._ticket or self.game_token

        @c.on("HelloGameMessage")
        def on_hello_game(msg):
            log.info("HelloGameMessage → sending AuthenticationTicketMessage")
            c.send_message("AuthenticationTicketMessage", {
                "ticket": ticket,
                "lang": self.lang,
            })

        @c.on("AuthenticationTicketAcceptedMessage")
        def on_ticket_accepted(msg):
            log.info("Auth ticket accepted → requesting character list")
            c.send_message("CharactersListRequestMessage", {})

        @c.on("AuthenticationTicketRefusedMessage")
        def on_ticket_refused(msg):
            log.error("Auth ticket refused")

        @c.on("CharactersListMessage")
        def on_char_list(msg):
            chars = msg.get("characters", [])
            log.info("Character list: %d characters", len(chars))
            self._characters = chars

            if not chars:
                log.error("No characters on this server")
                self._error = "No characters on server"
                self._game_ready.set()
                return

            if self.character_id:
                selected = next((ch for ch in chars if ch.get("id") == self.character_id), None)
                if not selected:
                    log.warning("Character id=%d not found, using first", self.character_id)
                    selected = chars[0]
            else:
                selected = chars[0]

            log.info("Selecting character: %s (id=%s)", selected.get("name"), selected.get("id"))
            c.send_message("CharacterSelectionMessage", {"id": selected["id"]})

        @c.on("CharacterSelectedSuccessMessage")
        def on_char_selected(msg):
            log.info("Character selected → sending context ready")
            c.send_message("GameContextCreateRequestMessage", {})

        @c.on("GameContextCreateMessage")
        def on_context_created(msg):
            log.info("Game context created — session is ready!")
            self._game_ready.set()

        @c.on("ConnectionFailedMessage")
        def on_conn_failed(msg):
            log.error("Connection failed: %s", msg)
