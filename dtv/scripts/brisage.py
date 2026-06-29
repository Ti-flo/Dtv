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
from dtv.collector.catalog import (
    INGREDIENT_CATALOGS, build_name_prices, build_name_to_gid, build_recipes,
    load_catalog,
)


# Helpers de robustesse (xlsx pandas → NaN). Implémentation unique dans le moteur ;
# alias ici pour la lisibilité du CLI et la compat des tests.
_to_level = br.to_level
_to_gid = br.to_gid


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


# ── Rendu d'un classement ────────────────────────────────────────────────────
def _render_ranking(rows: list, top: int, craft: bool, show_obs: bool, *,
                    real_mode: bool, title: str, subtitle: str, sort_label: str,
                    rev_label: str, rev_key: str, ben_key: str, rent_key: str):
    """
    Affiche un tableau de rentabilité de brisage.

    rev_key/ben_key/rent_key : colonnes revenu/bénéfice/rentabilité à lire dans
    chaque ligne (théorique au coeff --coeff, ou réel au coeff observé).
    real_mode=True ajoute un marqueur ✓/✗ (rentable ou non au coeff réel).
    """
    cost_label = "Craft" if craft else "Coût"

    print(f"\n{title}")
    if subtitle:
        print(subtitle)
    print(f"   trié par {sort_label} — {min(top, len(rows))}/{len(rows)} items\n")

    mark = "  " if real_mode else ""   # 2 cols pour le marqueur ✓/✗ en mode réel
    header = (f"  {mark}{'Nom':26s} {'Niv':>3s} {rev_label:>10s} {cost_label:>10s} "
              f"{'CoeffMin':>9s} {'Bénéf':>11s} {'Rent':>6s}")
    if show_obs:
        header += f" {'CoeffRéel':>9s} {'DernBris':>10s}"
    print(header)
    print("  " + "─" * (84 + len(mark) + (21 if show_obs else 0)))
    for r in rows[:top]:
        cout = f"{r['Cout_HDV']:,.0f}" if r["Cout_HDV"] is not None else "—"
        cmin = f"{r['Coeff_Min']:,.0f}%" if r["Coeff_Min"] is not None else "—"
        ben = r.get(ben_key)
        ben_str = f"{ben:,.0f}" if ben is not None else "—"
        rent = r.get(rent_key)
        rent_str = f"{rent:.2f}" if rent is not None else "—"
        rev = r.get(rev_key)
        rev_str = f"{rev:,.0f}" if rev is not None else "—"
        # ✓ si rentable au coeff de ce tableau (bénéfice positif), ✗ sinon.
        flag = (("✓ " if (ben is not None and ben > 0) else "✗ ") if real_mode else "")
        line = (f"  {flag}{r['Nom'][:26]:26s} {r['Niveau']:3d} {rev_str:>10s} "
                f"{cout:>10s} {cmin:>9s} {ben_str:>11s} {rent_str:>6s}")
        if show_obs:
            creel = f"{r['Coeff_Reel']:,.0f}%" if r["Coeff_Reel"] is not None else "—"
            dbris = r["Dernier_Brisage"] or "—"
            line += f" {creel:>9s} {dbris:>10s}"
        print(line)


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

    # Observations (coeff réel + date dernier brisage, par item).
    # Priorité : fichier CSV explicite → sinon auto-chargement depuis la base SQLite.
    observations = {}
    if args.observations and args.observations.exists():
        observations = load_observations(args.observations)
        print(f"📝 {len(observations)} observations de brisage chargées (CSV)")
    else:
        try:
            obs_conn = store.connect()
            observations = store.brisage_observations(obs_conn)
            if observations:
                print(f"📝 {len(observations)} observations de brisage chargées (base SQLite auto)")
        except Exception:
            pass

    # Récursivité des sous-crafts : coût de craft unitaire par item (min achat/craft),
    # passé à craft_plan qui tranche par ingrédient. Cohérent avec le rapport HTML.
    craft_alt: dict = {}
    if args.craft and use_db_craft:
        recipes_all = build_recipes(args.catalog.parent)
        buy_unit = {nom: craft.best_unit_price(t) for nom, t in ing_tier_prices.items()}
        buy_unit = {k: v for k, v in buy_unit.items() if v is not None}
        resolved = craft.resolve_craft_unit_costs(recipes_all, buy_unit)
        craft_alt = {nom: r["craft_unit"] for nom, r in resolved.items()
                     if r["craft_unit"] is not None}

    # Stratégie de coût injectée dans build_ranking : craft optimisé par tiers
    # (base SQLite), craft avg_prices en repli, ou prix HDV de l'item hors --craft.
    def _cost_for(it):
        if args.craft:
            if use_db_craft:
                recipe_raw = br.parse_recipe(it.get("Recette") or "")
                if not recipe_raw:
                    return (None, None)
                recipe_items = [(qty, br.normalize_name(ing)) for qty, ing in recipe_raw]
                ing_p = {n: ing_tier_prices[n] for _, n in recipe_items if n in ing_tier_prices}
                plan = craft.craft_plan(recipe_items, ing_p, craft_alt=craft_alt)
                return (plan["cost_per_craft"] if plan else None,
                        len(plan["missing"]) if plan else None)
            cc = br.craft_cost(it.get("Recette") or "", name_prices)
            return (cc["cost"] if cc else None, len(cc["missing"]) if cc else None)
        gid = br.to_gid(it.get("GID"))
        return (item_prices.get(gid) if (gid is not None and item_prices) else None, None)

    rows, sort_label = br.build_ranking(
        catalog, _cost_for, rune_prices=rune_prices, observations=observations,
        coeff=args.coeff, sort=args.sort, min_rentabilite=args.min_rentabilite)

    # ── Affichage : DEUX tableaux distincts ─────────────────────────────────
    # 1. TOP THÉORIQUE   — tout le catalogue, coeff réel inconnu (découverte).
    #    Trié par Coeff Min (le pari le plus sûr d'abord).
    # 2. BRISAGES RÉELS  — uniquement les items déjà brisés en jeu (coeff observé),
    #    bénéfice/rentabilité calculés au VRAI coeff. C'est la watchlist : si le
    #    coût de craft d'un item connu rentable baisse, il remonte ici.
    show_obs = bool(observations)
    coeff_lbl = f"Rev@{args.coeff:g}%"
    _render_ranking(
        rows, args.top, args.craft, show_obs, real_mode=False,
        title="🏆 TOP THÉORIQUE — potentiel de brisage (coeff réel inconnu)",
        subtitle="   Coeff Min = coeff serveur minimal pour être rentable (plus bas = plus sûr).",
        sort_label=sort_label, rev_label=coeff_lbl,
        rev_key="Revenu_theo", ben_key="Benefice_theo", rent_key="Rent_theo",
    )

    real = [r for r in rows if r["Coeff_Reel"] is not None]
    if real:
        # Bénéfice au coeff RÉEL décroissant : le plus rentable maintenant en tête.
        real.sort(key=lambda r: (r["Benefice_reel"] is not None, r["Benefice_reel"] or 0),
                  reverse=True)
        rentables = sum(1 for r in real if (r["Benefice_reel"] or 0) > 0)
        _render_ranking(
            real, len(real), args.craft, show_obs=True, real_mode=True,
            title="🎯 BRISAGES RÉELS — watchlist (coeff observé en jeu appliqué)",
            subtitle=(f"   {rentables}/{len(real)} rentables au coeff réel actuel. "
                      f"Bénéf/Rent au VRAI coeff ; coût de craft à jour → top brisage du moment."),
            sort_label="bénéfice réel décroissant", rev_label="Rev@réel",
            rev_key="Revenu_reel", ben_key="Benefice_reel", rent_key="Rent_reel",
        )
    elif show_obs:
        print("\n🎯 BRISAGES RÉELS : aucune observation ne correspond à un item chiffrable "
              "(coût/prix manquant ou non craftable).")

    # Export
    if args.out and rows:
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
