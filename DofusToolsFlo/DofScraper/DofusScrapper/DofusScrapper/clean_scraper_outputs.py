"""
clean_scraper_outputs.py — Nettoie les sorties des 3 scrapers SANS re-scraper.

Généralise clean_effets_equipements.py à tous les catalogues et toutes les
colonnes multi-valeurs. dofus-touch.com sert parfois 2 panels identiques
(« Effets », etc.), ce qui duplique les valeurs. Ce script déduplique les
tokens identiques de chaque colonne (en préservant l'ordre) et retire des
Effets les entrées qui sont en réalité des Conditions.

Idempotent : relançable sans risque. S'il n'y a pas de doublon → 0 changement.

Colonnes traitées (séparateur) :
  Effets (« | »)  Conditions (« | »)  Recette (« , »)
  Utilise_dans (« , »)  Drops_monstres (« | »)

Fichiers traités (ceux présents dans le dossier courant) :
  equipements_dofus_touch_full.{json,xlsx}
  consommables_dofus_touch_full.{json,xlsx}
  ressources_dofus_touch_full.{json,xlsx}

Usage :
  python clean_scraper_outputs.py                 # les 3 fichiers standard
  python clean_scraper_outputs.py mon_fichier.json
"""
import json
import sys
from pathlib import Path

import pandas as pd

# colonne → séparateur
COLS = {
    "Effets":         " | ",
    "Conditions":     " | ",
    "Recette":        ", ",
    "Utilise_dans":   ", ",
    "Drops_monstres": " | ",
}

DEFAULT_STEMS = [
    "equipements_dofus_touch_full",
    "consommables_dofus_touch_full",
    "ressources_dofus_touch_full",
]


def _dedup(value: str, sep: str, drop: set = frozenset()) -> str:
    if not isinstance(value, str) or not value:
        return value or ""
    parts = [p.strip() for p in value.split(sep) if p.strip()]
    # dict.fromkeys = dédup en préservant l'ordre
    kept = [p for p in dict.fromkeys(parts) if p not in drop]
    return sep.join(kept)


def clean_item(it: dict) -> int:
    """Nettoie un item en place. Retourne le nb de colonnes modifiées."""
    changed = 0
    cond = it.get("Conditions", "")
    cond_set = {c.strip() for c in cond.split(" | ")} if isinstance(cond, str) else set()
    for col, sep in COLS.items():
        if col not in it:
            continue
        before = it.get(col, "")
        # les conditions qui fuitent dans les effets sont retirées
        drop = cond_set if col == "Effets" else frozenset()
        after = _dedup(before, sep, drop)
        if after != (before if isinstance(before, str) else ""):
            it[col] = after
            changed += 1
    return changed


def clean_file(stem_or_path: str):
    p = Path(stem_or_path)
    if p.suffix:                      # chemin explicite
        json_path = p if p.suffix == ".json" else p.with_suffix(".json")
    else:                            # stem → .json + .xlsx
        json_path = Path(f"{stem_or_path}.json")
    xlsx_path = json_path.with_suffix(".xlsx")

    if not json_path.exists():
        print(f"⏭️  {json_path.name} absent, ignoré")
        return

    with open(json_path, encoding="utf-8") as f:
        items = json.load(f)

    total = sum(clean_item(it) for it in items)
    n_items = sum(1 for it in items if any(  # items touchés
        isinstance(it.get(c), str) for c in COLS))

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    pd.DataFrame(items).to_excel(xlsx_path, index=False)

    print(f"✅ {json_path.name} : {total} colonnes nettoyées sur {len(items)} items")
    print(f"   💾 {json_path.name} + {xlsx_path.name} réécrits")


if __name__ == "__main__":
    targets = sys.argv[1:] or DEFAULT_STEMS
    for t in targets:
        clean_file(t)
    print("\n🏁 Nettoyage terminé.")
