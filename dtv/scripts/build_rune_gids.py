"""
Construit dtv/data/rune_gids.json : {code rune → GID de l'item rune en jeu}.

Ce mapping permet de lire le prix HDV de chaque rune depuis un snapshot
avgprices_*.csv (qui est indexé par GID). Une fois rempli, le classement de
brisage utilise les vrais prix de runes du marché plutôt que les prix exemple.

Les runes sont des ressources : leur fiche existe dans le catalogue
ressources_dofus_touch_full. Ce script les y cherche (Type == « Rune » ou nom
commençant par « Rune ») et tente de les apparier aux 42 codes via le nom.

Comme les noms d'items runes en jeu peuvent différer des libellés, le script :
  - écrit les correspondances trouvées
  - liste les runes NON appariées (à compléter à la main dans le JSON)
  - liste les items « Rune » du catalogue non reconnus (pour aide au mapping)

Lancer (depuis le dossier contenant ressources_dofus_touch_full.xlsx) :
  python -m dtv.scripts.build_rune_gids --catalog ressources_dofus_touch_full.xlsx
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dtv.collector import brisage as br

OUT_PATH = Path(__file__).parent.parent / "data" / "rune_gids.json"


def _norm(s: str) -> str:
    """minuscule, sans accents, espaces collapsés."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def main():
    ap = argparse.ArgumentParser(description="Construit le mapping code rune → GID")
    ap.add_argument("--catalog", required=True, type=Path,
                    help="ressources_dofus_touch_full.xlsx ou .json")
    args = ap.parse_args()

    # Chargement catalogue
    if args.catalog.suffix.lower() == ".json":
        with open(args.catalog, encoding="utf-8") as f:
            items = json.load(f)
    else:
        import pandas as pd
        items = pd.read_excel(args.catalog).to_dict("records")

    # Items « Rune » du catalogue
    rune_items = []
    for it in items:
        nom = str(it.get("Nom_FR", "") or "")
        typ = str(it.get("Type", "") or "")
        if _norm(nom).startswith("rune ") or "rune" in _norm(typ):
            rune_items.append((it.get("GID"), nom))

    print(f"🔎 {len(rune_items)} items « Rune » trouvés dans le catalogue")

    # Index par nom normalisé du SUFFIXE après « Rune »
    by_suffix = {}
    for gid, nom in rune_items:
        suf = _norm(re.sub(r"^\s*rune\s+", "", nom, flags=re.I))
        by_suffix.setdefault(suf, (gid, nom))

    # Appariement code → GID via le display / nom de la rune
    code2gid = {}
    matched_names = set()
    for code, info in br.RUNES.items():
        candidates = {_norm(info["display"]), _norm(code), _norm(info["nom"])}
        hit = next((by_suffix[c] for c in candidates if c in by_suffix), None)
        if hit:
            code2gid[code] = hit[0]
            matched_names.add(hit[1])
        else:
            code2gid[code] = None

    n_ok = sum(1 for v in code2gid.values() if v is not None)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(code2gid, f, ensure_ascii=False, indent=2)

    print(f"✅ {n_ok}/42 runes appariées → {OUT_PATH}")
    missing = [c for c, v in code2gid.items() if v is None]
    if missing:
        print(f"\n⚠️  {len(missing)} runes NON appariées (à compléter à la main) :")
        for c in missing:
            print(f"    {c:5s} ({br.RUNES[c]['nom']})")
    unmatched_items = [(g, n) for g, n in rune_items if n not in matched_names]
    if unmatched_items:
        print(f"\n📋 Items « Rune » du catalogue non reconnus ({len(unmatched_items)}) — "
              f"pour t'aider à compléter :")
        for g, n in unmatched_items[:60]:
            print(f"    GID {g} — {n}")


if __name__ == "__main__":
    main()
