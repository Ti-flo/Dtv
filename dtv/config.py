"""
Configuration centrale de DTV — résout tous les chemins machine à la place de
l'utilisateur, pour que la collecte tourne en UNE commande, sans rien saisir.

Le but : supprimer les chemins en dur (adb.exe, dossier des catalogues scrapers,
data dir) qui forçaient des manips manuelles (trouver le PID du socket, faire
`--no-adb` parce qu'adb n'était pas dans le PATH, etc.).

Tout est résolu par ordre de priorité :
  1. variable d'environnement explicite (DTV_ADB, DTV_SCRAPER_DIR, DTV_DATA_DIR)
  2. emplacement standard connu (SDK Android, dossier scrapers de Flo)
  3. recherche automatique (PATH, arborescence du repo)

stdlib pure — aucune dépendance.
"""
import os
import shutil
from pathlib import Path

# Racine du repo : dtv/config.py → dtv/ → racine
ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.environ.get("DTV_DATA_DIR") or (ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
DB_PATH = Path(os.environ.get("DTV_DB") or (DATA_DIR / "dtv.db"))

# Catalogues produits par les scrapers (chez Flo, à côté des scripts scraper)
_KNOWN_SCRAPER_DIR = ROOT / "DofusToolsFlo" / "DofScraper" / "DofusScrapper" / "DofusScrapper"

CATALOG_FILES = {
    "equipements": "equipements_dofus_touch_full.json",
    "ressources": "ressources_dofus_touch_full.json",
    "consommables": "consommables_dofus_touch_full.json",
}


def _first_existing(paths) -> Path | None:
    for p in paths:
        if p and Path(p).exists():
            return Path(p)
    return None


def adb_path() -> str:
    """
    Chemin vers l'exécutable adb, résolu automatiquement.

    Ordre : DTV_ADB → adb dans le PATH → emplacements SDK Android standard
    (Windows/Linux/macOS) → repli sur « adb » (échouera clairement si absent).
    Ça évite le `--no-adb` manuel : capture_phone peut piloter adb tout seul.
    """
    env = os.environ.get("DTV_ADB")
    if env and Path(env).exists():
        return env

    which = shutil.which("adb") or shutil.which("adb.exe")
    if which:
        return which

    candidates = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "Android" / "Sdk" / "platform-tools" / "adb.exe")
    home = Path.home()
    candidates += [
        home / "AppData" / "Local" / "Android" / "Sdk" / "platform-tools" / "adb.exe",
        home / "Android" / "Sdk" / "platform-tools" / "adb",
        home / "Library" / "Android" / "sdk" / "platform-tools" / "adb",
        Path("/usr/local/bin/adb"),
        Path("/usr/bin/adb"),
    ]
    hit = _first_existing(candidates)
    return str(hit) if hit else "adb"


def adb_available() -> bool:
    """True si un adb exécutable a été localisé (sur PATH ou chemin connu)."""
    p = adb_path()
    return p != "adb" or shutil.which("adb") is not None


def scraper_dir() -> Path:
    """
    Dossier contenant les catalogues scrapés (equipements/ressources/consommables).

    Ordre : DTV_SCRAPER_DIR → dossier connu de Flo → recherche du catalogue
    équipements dans l'arborescence du repo.
    """
    env = os.environ.get("DTV_SCRAPER_DIR")
    if env and Path(env).exists():
        return Path(env)
    if _KNOWN_SCRAPER_DIR.exists():
        return _KNOWN_SCRAPER_DIR
    for p in ROOT.rglob(CATALOG_FILES["equipements"]):
        return p.parent
    return _KNOWN_SCRAPER_DIR


def catalog(kind: str) -> Path | None:
    """
    Chemin d'un catalogue par type ('equipements' | 'ressources' | 'consommables').

    Retourne le .json s'il existe (sinon le .xlsx de même nom, sinon None).
    """
    fname = CATALOG_FILES.get(kind)
    if not fname:
        return None
    d = scraper_dir()
    j = d / fname
    if j.exists():
        return j
    x = d / fname.replace(".json", ".xlsx")
    return x if x.exists() else None


def rune_gids_path() -> Path:
    """Chemin du mapping code rune → GID (dtv/data/rune_gids.json)."""
    return ROOT / "dtv" / "data" / "rune_gids.json"


def summary() -> dict:
    """Vue d'ensemble de la config résolue (pour diagnostic / `dtv doctor`)."""
    return {
        "root": str(ROOT),
        "data_dir": str(DATA_DIR),
        "raw_dir": str(RAW_DIR),
        "db_path": str(DB_PATH),
        "adb": adb_path(),
        "adb_available": adb_available(),
        "scraper_dir": str(scraper_dir()),
        "catalogs": {k: (str(catalog(k)) if catalog(k) else None) for k in CATALOG_FILES},
        "rune_gids": str(rune_gids_path()) if rune_gids_path().exists() else None,
    }
