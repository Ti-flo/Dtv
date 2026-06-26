"""
Classement de rentabilité de brisage sur tout le catalogue.

Croise :
  - le catalogue scrapé (equipements/consommables_dofus_touch_full.xlsx ou .json)
    → effets + niveau de chaque item
  - les prix HDV (snapshot avgprices_*.csv)  → coût d'achat de l'item
  - les prix des runes                        → revenu du brisage

et produit un tableau classé des items les plus rentables à briser.

────────────────────────────────────────────────────────────────────────────
SOURCES DE PRIX (par ordre de priorité)

  Coût de l'item :
    --avg-prices avgprices_<date>.csv   → coût = prix moyen HDV de l'item (par GID)
    (sinon : coût inconnu → on classe par revenu brut)

  Prix des runes :
    --rune-prices runes.csv             → CSV « code,prix » (le plus simple)
    --avg-prices + --rune-gids map.json → prix runes depuis le HDV (par GID rune)
    (sinon : prix_exemple de runes.json — snapshot manuel RuneMaster)

EXEMPLES
  # tourne tout de suite avec les prix exemple, classe par revenu de brisage
  python -m dtv.scripts.brisage --catalog equipements_dofus_touch_full.xlsx

  # avec prix HDV live (coût item) + prix runes live (revenu)
  python -m dtv.scripts.brisage --catalog equipements_dofus_touch_full.xlsx \
      --avg-prices data/raw/avgprices_20260626.csv --rune-gids dtv/data/rune_gids.json

  # avec une table de prix runes éditée à la main
  python -m dtv.scripts.brisage --catalog equipements_dofus_touch_full.xlsx \
      --rune-prices mes_prix_runes.csv --top 100 --out top_brisage.xlsx
────────────────────────────────────────────────────────────────────────────
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dtv.collector import brisage as br


# ── Chargement du catalogue ─────────────────────────────────────────────────
def load_catalog(path: Path) -> list[dict]:
    if path.suffix.lower() == ".json":
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    import pandas as pd
    df = pd.read_excel(path)
    return df.to_dict("records")


def _to_level(v) -> float:
    try:
        return float(str(v).replace("Niv.", "").strip())
    except (ValueError, AttributeError):
        return 0.0


# ── Chargement des prix ─────────────────────────────────────────────────────
def load_avg_prices(path: Path) -> dict[int, float]:
    """avgprices_*.csv (timestamp,item_gid,avg_price_x1,compte) → {gid: prix}."""
    prices = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                prices[int(row["item_gid"])] = float(row["avg_price_x1"])
            except (ValueError, KeyError):
                continue
    return prices


def load_rune_prices_csv(path: Path) -> dict[str, float]:
    """CSV « code,prix » → {code: prix}."""
    prices = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) < 2:
                continue
            code = row[0].strip().lower()
            if code == "code" or code not in br.RUNES:
                continue
            try:
                prices[code] = float(row[1])
            except ValueError:
                continue
    return prices


def rune_prices_from_avg(avg: dict[int, float], rune_gids_path: Path) -> dict[str, float]:
    """{code rune → prix} en piochant le prix HDV du GID de chaque rune."""
    with open(rune_gids_path, encoding="utf-8") as f:
        code2gid = json.load(f)
    out = {}
    for code, gid in code2gid.items():
        if gid is not None and int(gid) in avg:
            out[code] = avg[int(gid)]
    return out


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Classement rentabilité de brisage")
    ap.add_argument("--catalog", required=True, type=Path,
                    help="equipements/consommables_dofus_touch_full.xlsx ou .json")
    ap.add_argument("--avg-prices", type=Path, help="avgprices_*.csv (coût des items)")
    ap.add_argument("--rune-prices", type=Path, help="CSV « code,prix » (prix runes)")
    ap.add_argument("--rune-gids", type=Path, help="JSON {code: gid} pour prix runes via --avg-prices")
    ap.add_argument("--top", type=int, default=50, help="nombre de lignes affichées (def 50)")
    ap.add_argument("--min-rentabilite", type=float, default=0.0,
                    help="filtre : rentabilité revenu/coût minimale")
    ap.add_argument("--out", type=Path, help="export CSV ou XLSX du classement complet")
    args = ap.parse_args()

    catalog = load_catalog(args.catalog)
    print(f"📦 {len(catalog)} items chargés depuis {args.catalog.name}")

    # Prix des items (coût)
    item_prices = {}
    if args.avg_prices:
        item_prices = load_avg_prices(args.avg_prices)
        print(f"💰 {len(item_prices)} prix HDV chargés (coût des items)")

    # Prix des runes (revenu)
    rune_prices = None
    if args.rune_prices:
        rune_prices = load_rune_prices_csv(args.rune_prices)
        print(f"🪙 {len(rune_prices)} prix de runes chargés (CSV)")
    elif args.avg_prices and args.rune_gids:
        rune_prices = rune_prices_from_avg(item_prices, args.rune_gids)
        print(f"🪙 {len(rune_prices)} prix de runes déduits du HDV (via GID)")
    else:
        print("🪙 prix de runes : valeurs exemple (runes.json) — fournir --rune-prices pour du live")

    # Calcul
    rows = []
    for it in catalog:
        effets = it.get("Effets") or ""
        if not isinstance(effets, str) or not effets.strip():
            continue
        niveau = _to_level(it.get("Niveau"))
        gid = it.get("GID")
        cout = item_prices.get(int(gid)) if (gid and item_prices) else None
        res = br.profitability(effets, niveau, cout, rune_prices)
        if res["revenu"] <= 0:
            continue
        rows.append({
            "GID": gid,
            "Nom": it.get("Nom_FR", ""),
            "Type": it.get("Type", ""),
            "Niveau": int(niveau),
            "Revenu_brisage": res["revenu"],
            "Cout_HDV": res["cout"],
            "Benefice": res["benefice"],
            "Rentabilite": res["rentabilite"],
            "Runes": ", ".join(f"{c}×{q:g}" for c, q in res["runes"].items()),
        })

    # Tri : par bénéfice si coût connu, sinon par revenu
    has_cost = any(r["Benefice"] is not None for r in rows)
    if has_cost:
        rows = [r for r in rows if r["Benefice"] is not None]
        if args.min_rentabilite:
            rows = [r for r in rows if (r["Rentabilite"] or 0) >= args.min_rentabilite]
        rows.sort(key=lambda r: r["Benefice"], reverse=True)
        sort_label = "bénéfice (revenu − coût HDV)"
    else:
        rows.sort(key=lambda r: r["Revenu_brisage"], reverse=True)
        sort_label = "revenu de brisage (coût HDV inconnu)"

    # Affichage
    print(f"\n🏆 Top {min(args.top, len(rows))} / {len(rows)} items — trié par {sort_label}\n")
    print(f"  {'Nom':28s} {'Niv':>3s} {'Revenu':>10s} {'Coût':>10s} {'Bénéf':>11s} {'Rent':>6s}")
    print("  " + "─" * 78)
    for r in rows[:args.top]:
        cout = f"{r['Cout_HDV']:,.0f}" if r["Cout_HDV"] is not None else "—"
        benef = f"{r['Benefice']:,.0f}" if r["Benefice"] is not None else "—"
        rent = f"{r['Rentabilite']:.2f}" if r["Rentabilite"] is not None else "—"
        print(f"  {r['Nom'][:28]:28s} {r['Niveau']:3d} {r['Revenu_brisage']:10,.0f} "
              f"{cout:>10s} {benef:>11s} {rent:>6s}")

    # Export
    if args.out:
        if args.out.suffix.lower() == ".json":
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=2)
        elif args.out.suffix.lower() == ".csv":
            with open(args.out, "w", newline="", encoding="utf-8") as f:
                wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                wr.writeheader()
                wr.writerows(rows)
        else:
            import pandas as pd
            pd.DataFrame(rows).to_excel(args.out, index=False)
        print(f"\n💾 Classement complet ({len(rows)} items) → {args.out}")


if __name__ == "__main__":
    main()
