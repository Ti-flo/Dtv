"""
Enrichit un fichier avgprices_*.csv avec les noms d'items (depuis les catalogues
scrapers) et produit un XLSX lisible.

Croise les GIDs du snapshot de prix avec equipements + ressources + consommables
pour ajouter Nom_FR et Type. Utile pour vérifier les prix à la main.

Usage :
  python -m dtv.scripts.enrich_avgprices --avgprices data/raw/avgprices_XXX.csv
  python -m dtv.scripts.enrich_avgprices --avgprices data/raw/avgprices_XXX.csv --out data/raw/prix_nommes.xlsx
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dtv import config

CATALOG_NAMES = list(config.CATALOG_FILES.values())


def _build_name_map(scraper_dir: Path) -> dict[int, tuple[str, str]]:
    """GID -> (Nom_FR, Type) depuis les 3 catalogues."""
    name_map: dict[int, tuple[str, str]] = {}
    for fname in CATALOG_NAMES:
        path = scraper_dir / fname
        if not path.exists():
            print(f"  [!] catalogue absent : {path.name}")
            continue
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
        for it in items:
            try:
                gid = int(float(it.get("GID") or 0))
            except (ValueError, TypeError):
                continue
            if gid and gid not in name_map:
                name_map[gid] = (
                    str(it.get("Nom_FR") or ""),
                    str(it.get("Type") or ""),
                )
    return name_map


def main():
    ap = argparse.ArgumentParser(description="Enrichit avgprices avec les noms d'items")
    ap.add_argument("--avgprices", required=True, type=Path,
                    help="avgprices_*.csv (timestamp,item_gid,avg_price_x1,...)")
    ap.add_argument("--out", type=Path,
                    help="Fichier de sortie .xlsx ou .csv (défaut : même dossier, _named.xlsx)")
    ap.add_argument("--scraper-dir", type=Path, default=config.scraper_dir(),
                    help="Dossier contenant les catalogues JSON des scrapers")
    args = ap.parse_args()

    if not args.avgprices.exists():
        print(f"Fichier introuvable : {args.avgprices}")
        sys.exit(1)

    out_path = args.out or args.avgprices.with_name(
        args.avgprices.stem + "_named.xlsx"
    )

    print(f"Chargement des catalogues depuis {args.scraper_dir}...")
    name_map = _build_name_map(args.scraper_dir)
    print(f"  {len(name_map)} items connus")

    rows = []
    with open(args.avgprices, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                gid = int(row["item_gid"])
                price = int(float(row["avg_price_x1"]))
            except (ValueError, KeyError):
                continue
            nom, typ = name_map.get(gid, ("", ""))
            rows.append({
                "GID": gid,
                "Nom": nom,
                "Type": typ,
                "Prix_moyen_x1": price,
            })

    rows.sort(key=lambda r: r["Prix_moyen_x1"], reverse=True)

    n_named = sum(1 for r in rows if r["Nom"])
    n_unknown = len(rows) - n_named
    print(f"  {len(rows)} prix | {n_named} nommés | {n_unknown} GIDs inconnus")
    if n_unknown:
        print(f"  (GIDs inconnus = items hors catalogue scrapers : consommables non scrapes, etc.)")

    if out_path.suffix.lower() == ".csv":
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=["GID", "Nom", "Type", "Prix_moyen_x1"])
            wr.writeheader()
            wr.writerows(rows)
    else:
        import pandas as pd
        pd.DataFrame(rows).to_excel(out_path, index=False)

    print(f"Sauvegarde -> {out_path}")


if __name__ == "__main__":
    main()
