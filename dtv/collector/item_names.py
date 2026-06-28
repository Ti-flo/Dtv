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
DATA_DIR = ROOT / "data"
DEFAULT_PATH = DATA_DIR / "item_names.json"
GID_TYPES_PATH = DATA_DIR / "item_types_by_gid.json"
TYPE_NAMES_PATH = DATA_DIR / "item_type_names.json"
LEVELS_PATH = DATA_DIR / "item_levels.json"

_CACHE: "dict[int, str] | None" = None
_GID_TYPES_CACHE: "dict[int, int] | None" = None
_TYPE_NAMES_CACHE: "dict[int, str] | None" = None
_LEVELS_CACHE: "dict[int, int] | None" = None


def _load_int_keyed(path: Path, value_cast) -> dict:
    """Load a {int_key: value} JSON map, casting keys to int and values."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("Could not load %s: %s", path.name, e)
        return {}
    out = {}
    for k, v in raw.items():
        try:
            cv = value_cast(v)
        except (ValueError, TypeError):
            continue
        if cv != "" and cv is not None:
            out[int(k)] = cv
    return out


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
    _CACHE = _load_int_keyed(path, str)
    log.info("Loaded %d item names from %s", len(_CACHE), path.name)
    return _CACHE


def load_gid_types(path: Path = GID_TYPES_PATH) -> dict[int, int]:
    """Return {gid: typeId} — the TRUE item type from the game data cache."""
    global _GID_TYPES_CACHE
    if _GID_TYPES_CACHE is None:
        _GID_TYPES_CACHE = _load_int_keyed(path, int)
    return _GID_TYPES_CACHE


def load_type_names(path: Path = TYPE_NAMES_PATH) -> dict[int, str]:
    """Return {typeId: name} — live type labels from the ItemTypes store."""
    global _TYPE_NAMES_CACHE
    if _TYPE_NAMES_CACHE is None:
        _TYPE_NAMES_CACHE = _load_int_keyed(path, str)
    return _TYPE_NAMES_CACHE


def load_item_levels(path: Path = LEVELS_PATH) -> dict[int, int]:
    """Return {gid: level} — the item level (the HDV is sorted by level in-game)."""
    global _LEVELS_CACHE
    if _LEVELS_CACHE is None:
        _LEVELS_CACHE = _load_int_keyed(path, int)
    return _LEVELS_CACHE


def get_item_name(gid: int, fallback: str = "") -> str:
    """Return the item name for a GID, or fallback when unknown."""
    return load_item_names().get(gid, fallback)
