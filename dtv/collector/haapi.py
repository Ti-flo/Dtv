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
    Returns a 13-field dict including: key, account_id, refresh_token,
    expiration_date, ip.

    Token lifecycle (CONFIRMED live, session 7): with long_life_token=1 the
    apikey does NOT rotate — three consecutive refreshes returned the SAME key
    and refresh_token. They are reusable, not single-use. (The per-call
    game_token from create_token() IS single-use; only that one changes.)
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


def _field(d: dict, *names: str):
    """Return the first present key among names, or None — HAAPI field naming
    (key/apikey, account_id/accountId) varies; the live response body wasn't
    captured, so accept the known aliases instead of crashing on KeyError."""
    for n in names:
        if n in d:
            return d[n]
    return None


def authenticate(apikey: str, refresh_token: str) -> tuple[str, str, str, str]:
    """
    Full refresh flow → (account_id, game_token, new_apikey, new_refresh_token).

    NOTE on token rotation: CONFIRMED live (session 7) that with long_life_token=1
    the apikey and refresh_token do NOT rotate — they come back identical across
    refreshes, so they're reusable. The new values are still returned (and should
    be persisted) in case Ankama ever changes this. Do NOT use the Ankama app on
    this account while the bot runs — both sharing one token chain risks one
    invalidating the other.

    NOTE on IP binding: the RefreshApiKey response includes an "ip" field —
    Ankama binds the apikey to the IP it was bootstrapped from. The bot must run
    from that same residential IP.

    Usage:
        account_id, token, new_key, new_rt = authenticate(apikey, refresh_token)
    """
    refreshed = refresh_api_key(apikey, refresh_token)
    new_apikey = _field(refreshed, "key", "apikey", "api_key")
    account_id = _field(refreshed, "account_id", "accountId", "id")
    if not new_apikey or account_id is None:
        raise RuntimeError(
            f"RefreshApiKey response missing key/account_id. Got fields: "
            f"{list(refreshed.keys())}"
        )
    new_refresh_token = _field(refreshed, "refresh_token", "refreshToken") or refresh_token
    token = create_token(new_apikey)
    return str(account_id), token, new_apikey, new_refresh_token


def get_game_token(apikey: str, refresh_token: str) -> str:
    """Backwards-compatible helper — returns only the game token."""
    _, token, _, _ = authenticate(apikey, refresh_token)
    return token
