"""
HAAPI authentication for Dofus Touch.

Flow (returning sessions): apikey + refresh_token → new apikey → game_token
The initial apikey/refresh_token must be bootstrapped once from a logged-in
app session (extract from Chrome DevTools connected to the emulator).

Confirmed from live DevTools capture (sdk_gphone64_x86_64 emulator, Android 12):
  - Host: haapi.ankama.com
  - GAME_ID = 18 (Dofus Touch)
  - Cloudflare active → curl_cffi with chrome_android impersonation required
  - RefreshApiKey body: game_id=18&refresh_token=UUID&long_life_token=1
    with Content-Type: text/plain;charset=UTF-8 (as sent by the real app)
"""
from curl_cffi import requests

HAAPI_BASE = "https://haapi.ankama.com/json"
GAME_ID = 18

# Matched to live emulator capture (sdk_gphone64_x86_64, Android 12, Chrome/91)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 12; sdk_gphone64_x86_64 Build/SE1A.220826.008; wv) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/91.0.4472.114 "
        "Mobile Safari/537.36 DofusTouch Client 3.11.0"
    ),
    "x-requested-with": "com.ankama.dofustouch",
    "Accept": "application/json",
    "sec-fetch-site": "cross-site",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "accept-language": "en-US,en;q=0.9",
}


def refresh_api_key(apikey: str, refresh_token: str) -> dict:
    """
    POST with current apikey + refresh_token → refreshed credentials dict.

    Body is sent as text/plain (not form-encoded) — as observed in live capture.
    Returns dict with at minimum: {"key": "...", "refresh_token": "...", "account_id": ...}
    The old apikey and refresh_token are invalidated after this call.
    """
    url = f"{HAAPI_BASE}/Ankama/v5/Api/RefreshApiKey"
    headers = {
        **_HEADERS,
        "apikey": apikey,
        "Content-Type": "text/plain;charset=UTF-8",
    }
    body = f"game_id={GAME_ID}&refresh_token={refresh_token}&long_life_token=1"
    resp = requests.post(url, data=body, headers=headers, impersonate="chrome_android", timeout=30)
    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
    return resp.json()


def create_token(api_key: str) -> str:
    """
    GET with api_key header → game token (UUID string).

    The token is sent to the login server in the Primus "login" call alongside
    account_id as username.
    """
    url = f"{HAAPI_BASE}/Ankama/v5/Account/CreateToken"
    headers = {**_HEADERS, "apikey": api_key}
    resp = requests.get(url, params={"game": GAME_ID}, headers=headers, impersonate="chrome_android", timeout=30)
    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
    return resp.json()["token"]


def authenticate(apikey: str, refresh_token: str) -> tuple[str, str, str, str]:
    """
    Full refresh flow → (account_id, game_token, new_apikey, new_refresh_token).

    The old apikey and refresh_token are invalidated — save the new values to
    .env after each call (use dotenv.set_key or update manually).

    Usage:
        account_id, token, new_key, new_rt = authenticate(apikey, refresh_token)
    """
    refreshed = refresh_api_key(apikey, refresh_token)
    new_apikey = refreshed["key"]
    new_refresh_token = refreshed.get("refresh_token", refresh_token)
    account_id = str(refreshed["account_id"])
    token = create_token(new_apikey)
    return account_id, token, new_apikey, new_refresh_token


def get_game_token(apikey: str, refresh_token: str) -> str:
    """Backwards-compatible helper — returns only the game token."""
    _, token, _, _ = authenticate(apikey, refresh_token)
    return token
