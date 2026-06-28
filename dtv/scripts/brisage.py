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

from dtv import config
from dtv.collector import brisage as br
from dtv.collector import craft, store


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
        lvl = float(str(v).replace("Niv.", "").strip())
        return 0.0 if lvl != lvl else lvl   # NaN (cellule xlsx vide) → 0
    except (ValueError, AttributeError):
        return 0.0


def _to_gid(v):
    """GID en int, ou None si absent/NaN (pandas met NaN pour les cellules vides)."""
    if v is None:
        return None
    try:
        g = int(float(v))
        return g if g == g else None   # garde anti-NaN
    except (ValueError, TypeError):
        return None


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


# Catalogues d'où viennent les noms d'ingrédients (à côté du catalogue principal).
_INGREDIENT_CATALOGS = (
    "ressources_dofus_touch_full.json",
    "consommables_dofus_touch_full.json",
    "equipements_dofus_touch_full.json",
)


def build_name_to_gid(catalog_dir: Path) -> dict:
    """{nom normalisé → GID} depuis les 3 catalogues d'ingrédients."""
    out: dict[str, int] = {}
    for fname in _INGREDIENT_CATALOGS:
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
            gid = _to_gid(it.get("GID"))
            if nom and gid:
                out.setdefault(br.normalize_name(nom), gid)
    return out


def build_name_prices(item_prices: dict[int, float], catalog_dir: Path) -> dict[str, float]:
    """
    {nom d'ingrédient normalisé → prix moyen} pour chiffrer les recettes de craft.

    Croise les catalogues scrapers (Nom_FR → GID) avec l'avgprices (GID → prix).
    Indépendant de la colonne `nom` de l'avgprices → marche aussi sur les anciens
    snapshots. Les catalogues sont cherchés à côté du catalogue principal.
    """
    name_prices: dict[str, float] = {}
    for fname in _INGREDIENT_CATALOGS:
        path = catalog_dir / fname
        if not path.exists():
            continue
        try:
            with open(path, encoding="utf-8") as f:
                items = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        for it in items:
            gid = _to_gid(it.get("GID"))
            nom = it.get("Nom_FR")
            if gid is None or not nom or gid not in item_prices:
                continue
            name_prices.setdefault(br.normalize_name(nom), item_prices[gid])
    return name_prices


def explain_craft(catalog: list[dict], name_prices: dict[str, float], query: str):
    """Affiche le détail du coût de craft d'un item (recherche par nom)."""
    q = br.normalize_name(query)
    matches = [it for it in catalog
               if q in br.normalize_name(it.get("Nom_FR", ""))]
    if not matches:
        print(f"Aucun item ne correspond à « {query} »")
        return
    exact = [it for it in matches if br.normalize_name(it.get("Nom_FR", "")) == q]
    shown = exact or matches[:5]
    for it in shown:
        nom = it.get("Nom_FR", "?")
        recette = it.get("Recette") or ""
        cc = br.craft_cost(recette, name_prices)
        print(f"\n{nom}  (GID {it.get('GID')}, niv {it.get('Niveau')})")
        if cc is None:
            print("  pas de recette (item non craftable)")
            continue
        for qty, ing, prix in cc["detail"]:
            if prix is None:
                print(f"  {qty:>3} x {ing:30s}  prix INCONNU")
            else:
                print(f"  {qty:>3} x {ing:30s}  {prix:>10,.0f}  = {qty * prix:>12,.0f}")
        flag = "" if cc["complete"] else f"  /!\\ {len(cc['missing'])} ingredient(s) sans prix"
        print(f"  {'COUT CRAFT TOTAL':>36s}  = {cc['cost']:>12,.0f}{flag}")


def load_observations(path: Path) -> dict[int, dict]:
    """
    brisage_observations.csv (GID,coefficient_reel,dernier_brisage) → {gid: {...}}.

    Données OBSERVÉES en jeu (le coeff réel n'est connu qu'après brisage). Stockées
    à part du catalogue (qui se régénère par scraping). Rempli à la main pour
    l'instant ; à terme relevé auto depuis le serveur (cf. TODO KNOWLEDGE.md).
    """
    obs = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                gid = int(row["GID"])
            except (ValueError, KeyError):
                continue
            coeff = row.get("coefficient_reel", "").strip()
            obs[gid] = {
                "coeff": float(coeff) if coeff else None,
                "date": row.get("dernier_brisage", "").strip() or None,
            }
    return obs


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Classement rentabilité de brisage")
    ap.add_argument("--catalog", required=True, type=Path,
                    help="equipements/consommables_dofus_touch_full.xlsx ou .json")
    ap.add_argument("--avg-prices", type=Path, help="avgprices_*.csv (coût des items)")
    ap.add_argument("--rune-prices", type=Path, help="CSV « code,prix » (prix runes)")
    ap.add_argument("--rune-gids", type=Path, help="JSON {code: gid} pour prix runes via --avg-prices")
    ap.add_argument("--observations", type=Path,
                    help="brisage_observations.csv (GID,coefficient_reel,dernier_brisage) — "
                         "coeff réel observé en jeu, utilisé par item s'il est présent")
    ap.add_argument("--coeff", type=float, default=100.0,
                    help="coefficient de brisage serveur en %% (def 100 = base). "
                         "Le revenu réel = revenu_base × coeff/100. Inconnu avant brisage.")
    ap.add_argument("--sort", choices=("coeff-min", "benefice", "revenu"), default="coeff-min",
                    help="tri quand le coût est connu (def coeff-min = pari le plus sûr)")
    ap.add_argument("--top", type=int, default=50, help="nombre de lignes affichées (def 50)")
    ap.add_argument("--min-rentabilite", type=float, default=0.0,
                    help="filtre : rentabilité revenu/coût minimale")
    ap.add_argument("--days", type=int, default=7,
                    help="fenêtre prix HDV tiers en jours pour le coût de craft (def 7)")
    ap.add_argument("--craft", action="store_true",
                    help="coût = COÛT DE CRAFT optimisé (tiers HDV depuis la base SQLite). "
                         "Repli sur avg_prices si la base est vide.")
    ap.add_argument("--explain", metavar="NOM",
                    help="diagnostic : affiche le détail du coût de craft d'un item (par nom) "
                         "puis quitte. Ex : --explain \"Bâton de Boisaille\"")
    ap.add_argument("--out", type=Path, help="export CSV ou XLSX du classement complet")
    args = ap.parse_args()

    catalog = load_catalog(args.catalog)
    print(f"📦 {len(catalog)} items chargés depuis {args.catalog.name}")

    # Prix des items (coût)
    item_prices = {}
    if args.avg_prices:
        item_prices = load_avg_prices(args.avg_prices)
        print(f"💰 {len(item_prices)} prix HDV chargés (coût des items)")

    # Prix des ingrédients pour le coût de craft.
    # Priorité : prix HDV tiers depuis la base SQLite (optimisation de lot).
    # Repli : avg_prices x1 (si DB vide ou pour --explain).
    name_prices: dict[str, float] = {}       # avg_prices fallback
    ing_tier_prices: dict[str, dict] = {}    # {nom → {1:p, 10:p, 100:p, 1000:p}}
    use_db_craft = False

    if args.craft or args.explain:
        name2gid = build_name_to_gid(args.catalog.parent)
        if name2gid:
            try:
                conn_db = store.connect()
                all_gids = [g for g in name2gid.values() if g]
                tp = store.tier_prices_for_gids(conn_db, all_gids, days=args.days)
                ing_tier_prices = {nom: tp[gid] for nom, gid in name2gid.items() if gid in tp}
                use_db_craft = bool(ing_tier_prices)
            except Exception:
                pass

        if use_db_craft and args.craft:
            print(f"🔨 {len(ing_tier_prices)} ingrédients — prix HDV tiers depuis la base ({args.days} j)")
        else:
            if not item_prices:
                print("⚠️  --craft/--explain : base SQLite vide et pas de --avg-prices. Abandon.")
                sys.exit(1)
            name_prices = build_name_prices(item_prices, args.catalog.parent)
            suffix = " (avg_prices — sans optimisation tiers)" if args.craft else ""
            print(f"🔨 {len(name_prices)} prix d'ingrédients chargés{suffix}")

    # Diagnostic coût de craft d'un item → affiche et quitte
    if args.explain:
        explain_craft(catalog, name_prices, args.explain)
        return

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

    # Observations (coeff réel + date dernier brisage, par item)
    observations = {}
    if args.observations and args.observations.exists():
        observations = load_observations(args.observations)
        print(f"📝 {len(observations)} observations de brisage chargées (coeff réel par item)")

    # Calcul
    rows = []
    for it in catalog:
        effets = it.get("Effets") or ""
        if not isinstance(effets, str) or not effets.strip():
            continue
        niveau = _to_level(it.get("Niveau"))
        gid = _to_gid(it.get("GID"))
        # Coût : craft (tiers optimisés ou avg_prices) si --craft, sinon prix HDV de l'item
        craft_missing = None
        if args.craft:
            if use_db_craft:
                recipe_raw = br.parse_recipe(it.get("Recette") or "")
                if not recipe_raw:
                    cout = None
                else:
                    recipe_items = [(qty, br.normalize_name(ing)) for qty, ing in recipe_raw]
                    ing_p = {n: ing_tier_prices[n] for _, n in recipe_items if n in ing_tier_prices}
                    plan = craft.craft_plan(recipe_items, ing_p)
                    cout = plan["cost_per_craft"] if plan else None
                    craft_missing = len(plan["missing"]) if plan else None
            else:
                cc = br.craft_cost(it.get("Recette") or "", name_prices)
                cout = cc["cost"] if cc else None
                craft_missing = len(cc["missing"]) if cc else None
        else:
            cout = item_prices.get(gid) if (gid is not None and item_prices) else None
        obs = observations.get(gid) if (gid is not None and observations) else None
        # coeff réel observé par item s'il existe, sinon le coeff global (--coeff)
        coeff_item = obs["coeff"] if (obs and obs["coeff"]) else args.coeff
        res = br.profitability(effets, niveau, cout, rune_prices, coeff=coeff_item)
        if res["revenu_coeff100"] <= 0:
            continue
        rows.append({
            "GID": gid,
            "Nom": it.get("Nom_FR", ""),
            "Type": it.get("Type", ""),
            "Niveau": int(niveau),
            "Revenu_coeff100": res["revenu_coeff100"],
            "Revenu_brisage": res["revenu"],     # au coeff appliqué (réel ou --coeff)
            "Cout_HDV": res["cout"],             # = coût de craft si --craft
            "Craft_Manquants": craft_missing,    # nb d'ingrédients sans prix (None hors --craft)
            "Coeff_Min": res["coeff_min"],       # coeff % minimal pour être rentable
            "Coeff_Reel": obs["coeff"] if obs else None,        # observé en jeu
            "Dernier_Brisage": obs["date"] if obs else None,    # date observation
            "Benefice": res["benefice"],
            "Rentabilite": res["rentabilite"],
            "Runes": ", ".join(f"{c}×{q:g}" for c, q in res["runes"].items()),
        })

    # Tri : si coût connu → par Coeff_Min croissant (pari le plus sûr d'abord),
    # car le coeff réel est inconnu. Sinon → par revenu de brisage.
    has_cost = any(r["Coeff_Min"] is not None for r in rows)
    if has_cost:
        rows = [r for r in rows if r["Coeff_Min"] is not None]
        if args.min_rentabilite:
            rows = [r for r in rows if (r["Rentabilite"] or 0) >= args.min_rentabilite]
        if args.sort == "benefice":
            rows.sort(key=lambda r: r["Benefice"], reverse=True)
            sort_label = f"bénéfice (au coeff {args.coeff:g}%)"
        elif args.sort == "revenu":
            rows.sort(key=lambda r: r["Revenu_coeff100"], reverse=True)
            sort_label = "revenu de brisage (coeff 100%)"
        else:  # coeff-min (défaut)
            rows.sort(key=lambda r: r["Coeff_Min"])
            sort_label = "Coeff Min croissant (pari le plus sûr — coeff réel inconnu)"
    else:
        rows.sort(key=lambda r: r["Revenu_coeff100"], reverse=True)
        sort_label = "revenu de brisage coeff 100% (coût HDV inconnu)"

    # Affichage
    show_obs = bool(observations)
    print(f"\n🏆 Top {min(args.top, len(rows))} / {len(rows)} items — trié par {sort_label}")
    print(f"   (Coeff Min = coefficient serveur minimal pour rentrer dans ses frais ; "
          f"plus bas = plus sûr)\n")
    cost_label = "Craft" if args.craft else "Coût"
    header = (f"  {'Nom':26s} {'Niv':>3s} {'Rev@100%':>10s} {cost_label:>10s} "
              f"{'CoeffMin':>9s} {'Bénéf':>11s} {'Rent':>6s}")
    if show_obs:
        header += f" {'CoeffRéel':>9s} {'DernBris':>10s}"
    print(header)
    print("  " + "─" * (84 + (21 if show_obs else 0)))
    for r in rows[:args.top]:
        cout = f"{r['Cout_HDV']:,.0f}" if r["Cout_HDV"] is not None else "—"
        cmin = f"{r['Coeff_Min']:,.0f}%" if r["Coeff_Min"] is not None else "—"
        benef = f"{r['Benefice']:,.0f}" if r["Benefice"] is not None else "—"
        rent = f"{r['Rentabilite']:.2f}" if r["Rentabilite"] is not None else "—"
        line = (f"  {r['Nom'][:26]:26s} {r['Niveau']:3d} {r['Revenu_coeff100']:10,.0f} "
                f"{cout:>10s} {cmin:>9s} {benef:>11s} {rent:>6s}")
        if show_obs:
            creel = f"{r['Coeff_Reel']:,.0f}%" if r["Coeff_Reel"] is not None else "—"
            dbris = r["Dernier_Brisage"] or "—"
            line += f" {creel:>9s} {dbris:>10s}"
        print(line)

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
