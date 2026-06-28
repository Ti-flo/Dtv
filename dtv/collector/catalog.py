"""
Lecture des catalogues scrapés (equipements/ressources/consommables) — partagé
par le CLI brisage (`scripts/brisage.py`) et le rapport HTML (`report.py`).

Les catalogues sont les exports du scraper de Flo (Nom_FR, GID, Niveau, Type,
Effets, Recette…). On en tire deux dictionnaires d'appoint pour chiffrer les
recettes de craft :
  - {nom normalisé → GID}    (build_name_to_gid)
  - {nom normalisé → prix}   (build_name_prices, en croisant avec un {GID: prix})

stdlib pure (json) ; pandas chargé paresseusement seulement pour les .xlsx.
"""
import json
from pathlib import Path

from . import brisage as br

# Catalogues d'où viennent les noms d'ingrédients (à côté du catalogue principal).
INGREDIENT_CATALOGS = (
    "ressources_dofus_touch_full.json",
    "consommables_dofus_touch_full.json",
    "equipements_dofus_touch_full.json",
)


def load_catalog(path) -> list[dict]:
    """Charge un catalogue .json (rapide) ou .xlsx (via pandas) → liste de dicts."""
    path = Path(path)
    if path.suffix.lower() == ".json":
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    import pandas as pd
    return pd.read_excel(path).to_dict("records")


def _iter_ingredient_items(catalog_dir):
    """Itère les items des 3 catalogues d'ingrédients présents à côté du principal."""
    for fname in INGREDIENT_CATALOGS:
        path = Path(catalog_dir) / fname
        if not path.exists():
            continue
        try:
            items = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        yield from items


def build_name_to_gid(catalog_dir) -> dict:
    """{nom normalisé → GID} depuis les 3 catalogues d'ingrédients."""
    out: dict[str, int] = {}
    for it in _iter_ingredient_items(catalog_dir):
        nom = it.get("Nom_FR")
        gid = br.to_gid(it.get("GID"))
        if nom and gid:
            out.setdefault(br.normalize_name(nom), gid)
    return out


def build_name_prices(item_prices: dict, catalog_dir) -> dict:
    """
    {nom d'ingrédient normalisé → prix} en croisant les catalogues (Nom_FR → GID)
    avec un {GID → prix} (typiquement l'avgprices). Indépendant de la colonne
    `nom` de l'avgprices → marche aussi sur les anciens snapshots.
    """
    out: dict[str, float] = {}
    for it in _iter_ingredient_items(catalog_dir):
        gid = br.to_gid(it.get("GID"))
        nom = it.get("Nom_FR")
        if gid is None or not nom or gid not in item_prices:
            continue
        out.setdefault(br.normalize_name(nom), item_prices[gid])
    return out
