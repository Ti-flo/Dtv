"""
Plan de craft : combien d'items fabriquer et à quel tier acheter les ingrédients.

Pour un item donné, croise :
  - sa recette (catalogue scrapé)            → ingrédients + quantités
  - les noms d'ingrédients → GID (catalogues) → identité
  - les prix de lot réels (base SQLite)       → hdv_offers 7 j + repli avgprices
  - la logique de tiers (collector/craft.py)  → tier optimal selon le besoin total

et affiche le coût de craft optimisé, le nombre de crafts conseillé, et le tier
d'achat (x1/x10/x100/x1000) recommandé pour chaque ingrédient.

EXEMPLES
  python -m dtv.scripts.craft_plan "Bâton de Boisaille"
  python -m dtv.scripts.craft_plan "Épée de Boued" --n-crafts 50
  python -m dtv.scripts.craft_plan "Marteau" --days 14
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dtv import config
from dtv.collector import brisage as br
from dtv.collector import craft
from dtv.collector import store
from dtv.collector.catalog import build_recipes
from dtv.scripts.brisage import load_catalog


def build_name_to_gid(catalog_dir: Path) -> dict:
    """{nom d'ingrédient normalisé → GID} depuis les 3 catalogues scrapers."""
    out: dict[str, int] = {}
    for fname in config.CATALOG_FILES.values():
        path = catalog_dir / fname
        if not path.exists():
            continue
        try:
            with open(path, encoding="utf-8") as f:
                items = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        for it in items:
            nom = it.get("Nom_FR")
            try:
                gid = int(float(it.get("GID")))
            except (TypeError, ValueError):
                continue
            if nom:
                out.setdefault(br.normalize_name(nom), gid)
    return out


def find_item(catalog: list, query: str) -> dict | None:
    """Item du catalogue dont le nom matche `query` (exact prioritaire)."""
    q = br.normalize_name(query)
    matches = [it for it in catalog if q in br.normalize_name(it.get("Nom_FR", ""))]
    if not matches:
        return None
    exact = [it for it in matches if br.normalize_name(it.get("Nom_FR", "")) == q]
    return (exact or matches)[:1][0]


def _fmt(n) -> str:
    if n is None:
        return "—"
    return f"{n:,.0f}".replace(",", " ")


def main():
    ap = argparse.ArgumentParser(description="Plan de craft optimisé (tiers d'achat)")
    ap.add_argument("item", help="nom (partiel) de l'item à fabriquer")
    ap.add_argument("--n-crafts", type=int, default=None,
                    help="forcer le nombre de crafts (sinon estimé depuis le coût)")
    ap.add_argument("--days", type=int, default=7,
                    help="fenêtre de prix HDV réels en jours (def 7)")
    ap.add_argument("--catalog", type=Path, default=None,
                    help="catalogue équipements (déf : résolu par la config)")
    args = ap.parse_args()

    catalog_path = args.catalog or config.catalog("equipements")
    if not catalog_path or not Path(catalog_path).exists():
        print("Catalogue équipements introuvable. Définis DTV_SCRAPER_DIR ou --catalog.")
        sys.exit(1)
    catalog = load_catalog(Path(catalog_path))

    it = find_item(catalog, args.item)
    if it is None:
        print(f"Aucun item ne correspond à « {args.item} »")
        sys.exit(1)

    nom = it.get("Nom_FR", "?")
    recette = it.get("Recette") or ""
    recipe_raw = br.parse_recipe(recette)
    if not recipe_raw:
        print(f"{nom} : pas de recette (item non craftable).")
        sys.exit(0)

    # Résolution noms d'ingrédients → GID → prix de lot réels (base SQLite).
    name2gid = build_name_to_gid(Path(catalog_path).parent)
    recipe_items = [(qty, br.normalize_name(ing)) for qty, ing in recipe_raw]
    display_names = {br.normalize_name(ing): ing for _, ing in recipe_raw}

    gids = [name2gid.get(n) for _, n in recipe_items]
    conn = store.connect()
    tp_by_gid = store.tier_prices_for_gids(conn, [g for g in gids if g], days=args.days)

    # {nom normalisé → {tier: prix_lot}} pour craft_plan.
    ing_prices = {}
    for (_, n), g in zip(recipe_items, gids):
        if g and g in tp_by_gid:
            ing_prices[n] = tp_by_gid[g]

    # Récursivité des sous-crafts : coût de craft unitaire par ingrédient
    # (min achat/craft), pour chiffrer un ingrédient craftable à son coût de craft.
    all_gids = [g for g in name2gid.values() if g]
    tp_all = store.tier_prices_for_gids(conn, all_gids, days=args.days)
    buy_unit = {nom: craft.best_unit_price(tp_all[g])
                for nom, g in name2gid.items() if g in tp_all}
    buy_unit = {k: v for k, v in buy_unit.items() if v is not None}
    resolved = craft.resolve_craft_unit_costs(
        build_recipes(Path(catalog_path).parent), buy_unit)
    craft_alt = {nom: r["craft_unit"] for nom, r in resolved.items()
                 if r["craft_unit"] is not None}

    plan = craft.craft_plan(recipe_items, ing_prices, n_crafts=args.n_crafts,
                            craft_alt=craft_alt)
    if plan is None:
        print(f"{nom} : recette vide.")
        sys.exit(0)

    # Plan minimal à 10 % du volume (au moins 1 craft).
    n_mini = max(1, plan["n_crafts"] // 10)
    plan_mini = craft.craft_plan(recipe_items, ing_prices, n_crafts=n_mini,
                                 craft_alt=craft_alt)

    def _print_plan(p, label: str, src: str):
        print(f"\n--- {label} : {p['n_crafts']} crafts  ({src}) ---")
        print(f"  {'Ingrédient':28s} {'Qté':>4s} {'Besoin':>8s} {'Tier':>6s} "
              f"{'PU':>10s} {'Coût ligne':>12s} {'Achats':>7s}")
        print("  " + "-" * 85)
        warns = []
        for d in p["detail"]:
            ing = display_names.get(d["nom"], d["nom"])[:28]
            tier = "craft" if d.get("method") == "craft" else (f"x{d['tier']}" if d["tier"] else "—")
            pu = _fmt(d["unit_price"])
            line = _fmt(d["line_cost"]) if d["line_cost"] is not None else "PRIX INCONNU"
            np_ = d.get("n_purchases")
            np_str = str(np_) if np_ is not None else "—"
            flag = " !" if (np_ is not None and np_ > craft.MAX_PURCHASES) else "  "
            print(f"  {ing:28s} {d['qty']:>4d} {_fmt(d['total_needed']):>8s} {tier:>6s} "
                  f"{pu:>10s} {line:>12s} {np_str:>6s}{flag}")
            if np_ is not None and np_ > craft.MAX_PURCHASES:
                warns.append((display_names.get(d["nom"], d["nom"]), d["tier"], np_,
                              d["total_needed"], d.get("available_tiers", {})))
        print("  " + "-" * 85)
        missing_flag = "" if p["complete"] else f"   /!\\ {len(p['missing'])} ingrédient(s) sans prix"
        print(f"  {'COÛT DE CRAFT / unité':>50s}  = {_fmt(p['cost_per_craft'])} kamas{missing_flag}")
        print(f"  {'COÛT TOTAL pour ' + str(p['n_crafts']) + ' crafts':>50s}  "
              f"= {_fmt(p['cost_total'])} kamas")
        if warns:
            print(f"\n  /!\\ Aucun lot assez grand pour rester sous {craft.MAX_PURCHASES} achats :")
            for wnom, wtier, wnp, wneeded, wavail in warns:
                next_tier = next((t for t in (10, 100, 1000) if t > wtier), None)
                hint = (f" -> capture x{next_tier} dans l'HDV pour réduire"
                        if next_tier else "")
                print(f"       {wnom}: x{wtier} max disponible → {wnp} achats{hint}")
        if not p["complete"]:
            print(f"\n  Ingrédients sans prix HDV ni moyen : "
                  f"{', '.join(display_names.get(m, m) for m in p['missing'])}")
            print("  (ouvre-les dans l'HDV pendant une capture pour relever leur prix)")

    # Affichage
    print(f"\n=== Plan de craft : {nom}  (GID {it.get('GID')}, niv {it.get('Niveau')}) ===")
    print(f"Fenêtre prix HDV réels : {args.days} derniers jours (repli : prix moyen serveur)")

    src_full = "forcé" if args.n_crafts else "estimé d'après le coût"
    _print_plan(plan, "Plan réaliste (100 %)", src_full)

    if plan_mini is not None and n_mini != plan["n_crafts"]:
        _print_plan(plan_mini, "Plan minimal  (10 %)", "10 % du plan réaliste")

        # Comparaison
        diff = plan["cost_per_craft"] - plan_mini["cost_per_craft"]
        if diff > 0:
            print(f"\n  => Le plan minimal est moins cher de {_fmt(diff)} kamas/craft "
                  f"({diff / plan['cost_per_craft'] * 100:.1f} % d'économie par craft).")
        elif diff < 0:
            print(f"\n  => Le plan réaliste est moins cher de {_fmt(-diff)} kamas/craft "
                  f"({-diff / plan_mini['cost_per_craft'] * 100:.1f} % d'économie par craft).")
        else:
            print("\n  => Coût par craft identique dans les deux plans.")


if __name__ == "__main__":
    main()
