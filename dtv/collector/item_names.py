"""
GID → item name lookup.

The name database is built by running:
    python -m dtv.scripts.dump_item_names

That script connects to the running Dofus Touch WebView via CDP and reads
the game's IndexedDB item cache (enDataCache → Items store) into
data/item_names.json. The game caches items lazily, so each run merges new
names into the file; coverage grows as you play. Re-run anytime.

If the JSON doesn't exist, load_item_names() returns an empty dict and
everything falls back to showing bare GIDs (same behaviour as before).
"""
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent.parent
DEFAULT_PATH = ROOT / "data" / "item_names.json"

_CACHE: "dict[int, str] | None" = None


def load_item_names(path: Path = DEFAULT_PATH) -> dict[int, str]:
    """Return {gid: name}. Result is cached; safe to call repeatedly."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    if not path.exists():
        log.debug(
            "item_names.json not found — run: python -m dtv.scripts.dump_item_names"
        )
        _CACHE = {}
        return _CACHE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        _CACHE = {int(k): v for k, v in raw.items() if v}
        log.info("Loaded %d item names from %s", len(_CACHE), path.name)
    except Exception as e:
        log.warning("Could not load item_names.json: %s", e)
        _CACHE = {}
    return _CACHE


def get_item_name(gid: int, fallback: str = "") -> str:
    """Return the item name for a GID, or fallback when unknown."""
    return load_item_names().get(gid, fallback)
