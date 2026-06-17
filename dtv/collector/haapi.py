"""
HAAPI authentication for Dofus Touch.

Flow: login + password → api_key → game_token
The game_token is then sent to the game server via AuthenticationTicketMessage.

Confirmed from mitmproxy capture:
  - Host: haapi.ankama.com
  - GAME_ID = 18 (Dofus Touch)
  - Cloudflare is active → Android headers required
"""
import requests

HAAPI_BASE = "https://haapi.ankama.com/json"
GAME_ID = 18

# Exact headers from mitmproxy capture (capture.har)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 9; SM-S908E Build/TP1A.220624.014; wv) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/129.0.6668.70 "
        "Safari/537.36 DofusTouch Client 3.11.0"
    ),
    "sec-ch-ua": '"Android WebView";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Android"',
    "x-requested-with": "com.ankama.dofustouch",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "sec-fetch-site": "cross-site",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "accept-language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
}


def create_api_key(login: str, password: str) -> dict:
    """
    POST credentials → api_key dict.

    Returns dict with at minimum: {"key": "...", "account_id": ...}
    The "key" field is what's passed to create_token().
    """
    url = f"{HAAPI_BASE}/Ankama/v5/Api/CreateApiKey"
    payload = {
        "login": login,
        "password": password,
        "long_life_token": False,
        "game": GAME_ID,
    }
    resp = requests.post(url, json=payload, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def create_token(api_key: str) -> str:
    """
    GET with api_key header → game token string.

    The token is a short-lived JWT passed to the game server as the
    "ticket" field in AuthenticationTicketMessage.
    """
    url = f"{HAAPI_BASE}/Ankama/v5/Game/CreateToken"
    headers = {**_HEADERS, "apikey": api_key}
    resp = requests.get(url, params={"game": GAME_ID}, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()["token"]


def get_game_token(login: str, password: str) -> str:
    """
    Full auth flow: credentials → game token ready for the WebSocket server.

    Usage:
        token = get_game_token("email@gmail.com", "password")
    """
    api_data = create_api_key(login, password)
    api_key = api_data["key"]
    return create_token(api_key)
