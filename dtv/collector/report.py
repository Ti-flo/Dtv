"""
Rapport HTML interactif de DTV — `dtv report`.

Génère UN SEUL fichier .html autonome (self-contained, ouvrable hors-ligne, zéro
serveur) à partir de la base SQLite (data/dtv.db). Les données sont embarquées en
JSON dans la page ; toute l'interactivité (onglets, tri, graphes) est en JS
vanilla — aucune dépendance externe, aucun CDN.

Architecture :
  build_report_data(conn)  -> dict  (le modèle de données, sérialisable JSON)
  render_html(data)        -> str   (la page complète, JSON embarqué)
  generate(conn, out_path) -> Path  (écrit le fichier, retourne le chemin)

Onglets (itératif, un par un) :
  (1) Prix dans le temps  — séries avg (prix moyen marché) + HDV par tier
                            (x1/x10/x100/x1000), min/max/moyen, graphe + tri. ✅
  (2) Ressources achetées — depuis transactions_observations.   (à venir)
  (3) Craft & Brisage     — réutilise craft.py + brisage.py.     (à venir)
  (4) Bonnes affaires     — prix actuel vs médiane historique.   (à venir)

stdlib pure (sqlite3, json).
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .. import config
from . import brisage as br
from . import catalog as catalog_mod
from . import craft, item_names, store


# ── Construction du modèle de données ────────────────────────────────────────
def _price_series(conn: sqlite3.Connection) -> list[dict]:
    """
    Une entrée par item présent dans la base, avec ses séries temporelles :

      {
        "gid": int, "nom": str,
        "avg": [[ts, price], ...],                       # prix moyen marché (x1)
        "hdv": [[ts, x1, x10, x100, x1000, nb], ...],    # prix plancher par tier
      }

    Les séries sont triées par horodatage croissant. `nom` = le nom non vide le
    plus récent rencontré (avg puis hdv).
    """
    items: dict[int, dict] = {}

    def _slot(gid: int) -> dict:
        return items.setdefault(gid, {"gid": gid, "nom": "", "type": "", "level": None,
                                      "avg": [], "hdv": []})

    # Prix moyens (ObjectAveragePrices) — la baseline « tendance ».
    for r in conn.execute(
        "SELECT gid, nom, ts, price FROM avg_prices "
        "WHERE price IS NOT NULL ORDER BY gid, ts"
    ):
        slot = _slot(r["gid"])
        if r["nom"]:
            slot["nom"] = r["nom"]
        slot["avg"].append([r["ts"], r["price"]])

    # Prix plancher HDV par tier — le « floor » temps réel.
    for r in conn.execute(
        "SELECT gid, nom, ts, prix_x1, prix_x10, prix_x100, prix_x1000, nb_offres "
        "FROM hdv_offers ORDER BY gid, ts"
    ):
        slot = _slot(r["gid"])
        if r["nom"]:
            slot["nom"] = r["nom"]
        slot["hdv"].append([
            r["ts"], r["prix_x1"], r["prix_x10"], r["prix_x100"],
            r["prix_x1000"], r["nb_offres"],
        ])

    # Noms manquants → résolution via le catalogue GID→nom (data/item_names.json,
    # alimenté par `dump_item_names`). Dernier repli : « GID <n> ».
    names = item_names.load_item_names()
    gid_types = item_names.load_gid_types()      # gid → type_id
    type_names = item_names.load_type_names()    # type_id → libellé
    levels = item_names.load_item_levels()       # gid → niveau
    # Enrichissement depuis les catalogues scrapés COMPLETS (nom/type/niveau FR),
    # en repli du cache de jeu qui n'a que les items déjà rencontrés.
    cat_meta: dict = {}
    try:
        cat_meta = catalog_mod.build_gid_meta(config.scraper_dir())
    except Exception:
        cat_meta = {}
    for slot in items.values():
        m = cat_meta.get(slot["gid"])
        if not slot["nom"]:
            slot["nom"] = names.get(slot["gid"]) or (m["nom"] if m and m["nom"] else "") \
                          or f"GID {slot['gid']}"
        tid = gid_types.get(slot["gid"])
        if tid is not None:
            slot["type"] = type_names.get(tid) or ""
        if not slot["type"] and m and m["type"]:
            slot["type"] = m["type"]
        lvl = levels.get(slot["gid"])
        if lvl is None and m:
            lvl = m["niveau"]
        slot["level"] = lvl

    return sorted(items.values(), key=lambda s: s["nom"].lower())


def _latest_avg_prices(conn: sqlite3.Connection) -> dict:
    """{gid → dernier prix moyen connu} (dernier snapshot par GID)."""
    rows = conn.execute(
        "SELECT gid, price FROM avg_prices ap "
        "WHERE price IS NOT NULL "
        "  AND ts = (SELECT MAX(ts) FROM avg_prices a2 WHERE a2.gid = ap.gid)"
    ).fetchall()
    return {r["gid"]: float(r["price"]) for r in rows}


# Colonnes embarquées par ligne de classement (sous-ensemble lisible/léger).
_BRISAGE_FIELDS = (
    "GID", "Nom", "Type", "Niveau", "Prix_Moyen", "Base_coeff100", "Cout_HDV",
    "Craft_Manquants", "Coeff_Min", "Coeff_Reel", "Dernier_Brisage",
    "Revenu_theo", "Benefice_theo", "Rent_theo",
    "Revenu_reel", "Benefice_reel", "Rent_reel", "Runes",
    "craft", "runes_detail",  # détail au clic (recette par batch + runes)
)
_BRISAGE_CAP = 500   # plafond du tableau théorique embarqué (les + rentables ; détail au clic embarqué)
_CRAFT_BATCHES = (1, 10, 100, 1000)


def build_brisage_data(conn: sqlite3.Connection, *, coeff: float = 100.0) -> dict:
    """
    Données de l'onglet « Craft & Brisage » : les 2 tableaux théorique/réel.

    Coût = COÛT DE CRAFT (tiers HDV optimisés depuis la base ; repli avgprices).
    Réutilise EXACTEMENT le moteur du CLI (brisage.build_ranking + craft.craft_plan)
    pour des chiffres identiques entre `dtv brisage` et le rapport.

    Sans catalogue scrapé → {"available": False, "reason": …}.
    """
    cat_path = config.catalog("equipements")
    extra = config.catalog("consommables")
    paths = [p for p in (cat_path, extra) if p and Path(p).exists()]
    if not paths:
        return {"available": False,
                "reason": "catalogue scrapé introuvable (equipements_dofus_touch_full.json). "
                          "Configure DTV_SCRAPER_DIR ou lance le scraper."}

    catalog: list[dict] = []
    for p in paths:
        try:
            catalog += catalog_mod.load_catalog(p)
        except Exception:
            continue
    if not catalog:
        return {"available": False, "reason": "catalogue illisible."}

    catalog_dir = Path(paths[0]).parent
    item_prices = _latest_avg_prices(conn)

    # Prix des runes (revenu) : depuis le HDV via rune_gids.json, sinon exemples.
    rune_prices = None
    rg_path = config.rune_gids_path()
    if rg_path.exists():
        try:
            code2gid = json.loads(rg_path.read_text(encoding="utf-8"))
            rp = {c: item_prices[int(g)] for c, g in code2gid.items()
                  if g is not None and int(g) in item_prices}
            rune_prices = rp or None
        except Exception:
            rune_prices = None

    # Coût de craft : prix HDV par tiers depuis la base (optimisation de lot),
    # repli avgprices x1 si la base n'a pas encore de relevés HDV.
    name2gid = catalog_mod.build_name_to_gid(catalog_dir)
    ing_tier_prices: dict = {}
    if name2gid:
        try:
            tp = store.tier_prices_for_gids(conn, list(name2gid.values()), days=7)
            ing_tier_prices = {nom: tp[gid] for nom, gid in name2gid.items() if gid in tp}
        except Exception:
            ing_tier_prices = {}
    use_db_craft = bool(ing_tier_prices)
    name_prices = catalog_mod.build_name_prices(item_prices, catalog_dir)

    # Récursivité des sous-crafts : un ingrédient craftable est chiffré au moins
    # cher entre l'acheter (HDV) et le crafter récursivement. craft_alt = coût de
    # craft unitaire par item ; passé à craft_plan qui tranche par ingrédient.
    craft_alt: dict = {}
    if use_db_craft:
        recipes_all = catalog_mod.build_recipes(catalog_dir)
        buy_unit = {nom: craft.best_unit_price(tiers)
                    for nom, tiers in ing_tier_prices.items()}
        buy_unit = {k: v for k, v in buy_unit.items() if v is not None}
        resolved = craft.resolve_craft_unit_costs(recipes_all, buy_unit)
        craft_alt = {nom: r["craft_unit"] for nom, r in resolved.items()
                     if r["craft_unit"] is not None}

    def _cost_for(it):
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

    observations = {}
    try:
        observations = store.brisage_observations(conn)
    except Exception:
        observations = {}

    rows, sort_label = br.build_ranking(
        catalog, _cost_for, rune_prices=rune_prices, observations=observations,
        coeff=coeff, sort="coeff-min")

    # Prix moyen de l'item fini à l'HDV (≠ coût de craft) → décision craft vs achat.
    for r in rows:
        r["Prix_Moyen"] = item_prices.get(r["GID"])

    # Détail au clic : recette + coût de craft à PLUSIEURS batchs (le moteur
    # craft_plan refait sa recherche de tier optimal pour chaque taille), + le
    # détail des runes. Calculé seulement pour les lignes embarquées.
    cat_by_gid: dict = {}
    for it in catalog:
        g = br.to_gid(it.get("GID"))
        if g is not None:
            cat_by_gid.setdefault(g, it)

    def _craft_detail(it):
        recipe_raw = br.parse_recipe(it.get("Recette") or "")
        if not recipe_raw:
            return None
        if use_db_craft:
            recipe_items = [(qty, br.normalize_name(ing)) for qty, ing in recipe_raw]
            ing_p = {n: ing_tier_prices[n] for _, n in recipe_items if n in ing_tier_prices}
            recipe = [{"nom": ing, "qty": qty,
                       "tiers": ing_tier_prices.get(br.normalize_name(ing)),
                       "craft_unit": craft_alt.get(br.normalize_name(ing))}
                      for qty, ing in recipe_raw]
            cpc = {}
            for B in _CRAFT_BATCHES:
                pl = craft.craft_plan(recipe_items, ing_p, n_crafts=B, craft_alt=craft_alt)
                cpc[str(B)] = round(pl["cost_per_craft"], 2) if pl else None
            pa = craft.craft_plan(recipe_items, ing_p, craft_alt=craft_alt)
            cpc["auto"] = round(pa["cost_per_craft"], 2) if pa else None
            return {"recipe": recipe, "n_auto": (pa["n_crafts"] if pa else None),
                    "cpc": cpc, "db": True}
        # Repli avgprices (pas de tiers) : coût plat, identique quel que soit le batch.
        cc = br.craft_cost(it.get("Recette") or "", name_prices)
        flat = round(cc["cost"], 2) if cc else None
        recipe = [{"nom": ing, "qty": qty, "tiers": None} for qty, ing in recipe_raw]
        return {"recipe": recipe, "n_auto": None, "db": False,
                "cpc": {k: flat for k in ("auto", "1", "10", "100", "1000")}}

    def _runes_detail(effets, niveau):
        out = []
        for code, q in sorted(br.breakdown(effets or "", niveau or 0).items(),
                              key=lambda kv: -kv[1]):
            out.append({"code": code, "nom": br.RUNES.get(code, {}).get("nom", code),
                        "qty": round(q, 3), "price": br.rune_price(code, rune_prices)})
        return out

    def _enrich(r):
        if "craft" in r:
            return r            # déjà enrichi (item présent dans theo ET real)
        it = cat_by_gid.get(r["GID"])
        r["craft"] = _craft_detail(it) if it else None
        r["runes_detail"] = _runes_detail(it.get("Effets") if it else "", r["Niveau"])
        return r

    def _trim(r):
        return {k: r.get(k) for k in _BRISAGE_FIELDS}

    real = [r for r in rows if r["Coeff_Reel"] is not None]
    real.sort(key=lambda r: (r["Benefice_reel"] is not None, r["Benefice_reel"] or 0),
              reverse=True)

    for r in real:
        _enrich(r)
    for r in rows[:_BRISAGE_CAP]:
        _enrich(r)

    # Entonnoir : catalogue → items avec effets brisables → chiffrables (coût connu).
    n_breakable = sum(
        1 for it in catalog
        if any(l["brisable"] for l in br.parse_effects(it.get("Effets") or ""))
    )
    # Couverture des recettes : combien d'items ont une recette exploitable, et
    # combien d'items BRISABLES n'en ont pas (= trou de scraping à combler).
    n_recipes = sum(1 for it in catalog if br.parse_recipe(it.get("Recette") or ""))
    n_breakable_norecipe = sum(
        1 for it in catalog
        if any(l["brisable"] for l in br.parse_effects(it.get("Effets") or ""))
        and not br.parse_recipe(it.get("Recette") or "")
    )

    return {
        "available": True,
        "craft_mode": use_db_craft,          # True = coût craft tiers HDV, False = avgprices
        "rune_live": rune_prices is not None,
        "coeff": coeff,
        "sort_label": sort_label,
        "n_catalog": len(catalog),
        "n_breakable": n_breakable,          # items avec ≥1 effet brisable
        "n_recipes": n_recipes,              # items avec une recette exploitable
        "n_breakable_norecipe": n_breakable_norecipe,  # brisables SANS recette (trou scraping)
        "n_priced": len(item_prices),
        "n_ranked": len(rows),
        "n_real": len(real),
        "theo": [_trim(r) for r in rows[:_BRISAGE_CAP]],
        "real": [_trim(r) for r in real],
    }


def build_rune_data(conn: sqlite3.Connection) -> dict:
    """
    Données de l'onglet Runes.

    - catalog  : 43 runes avec tiers enrichis ; GIDs résolus par nom depuis
                 avg_prices (pas besoin de rune_gids.json par tier).
    - concassage : rows BrisageRow-compatible pour renderBTable/openBModal.
                   Modélise 3×tier_inf → 1×tier_sup comme un craft_plan.
    """
    # ── GIDs des runes depuis la base (matching par nom normalisé) ──────────
    rune_tier_noms: dict[str, tuple] = {}
    for code, rune in br.RUNES.items():
        for t in rune["tiers"]:
            rune_tier_noms[br.normalize_name(t["nom"])] = (code, t["tier"], t["mult_base"])

    name_to_gid: dict[str, int] = {}
    try:
        for row in conn.execute(
            "SELECT DISTINCT gid, nom FROM avg_prices WHERE nom IS NOT NULL"
        ).fetchall():
            norm = br.normalize_name(row["nom"])
            if norm in rune_tier_noms:
                name_to_gid[norm] = row["gid"]
    except Exception:
        pass

    # Prix unitaires HDV par tier (7 derniers jours) pour les runes trouvées.
    ing_tier_prices: dict[str, dict] = {}
    if name_to_gid:
        try:
            tp = store.tier_prices_for_gids(conn, list(set(name_to_gid.values())), days=7)
            ing_tier_prices = {nom: tp[gid]
                               for nom, gid in name_to_gid.items() if gid in tp}
        except Exception:
            pass

    item_prices = _latest_avg_prices(conn)

    # ── Catalogue : une entrée par rune, tiers enrichis ─────────────────────
    catalog: dict = {}
    for code, rune in br.RUNES.items():
        tiers_out: list[dict] = []
        simple_price: float | None = None

        for t in rune["tiers"]:
            norm = br.normalize_name(t["nom"])
            gid = name_to_gid.get(norm)
            tiers_hdv = ing_tier_prices.get(norm)

            if tiers_hdv:
                prix = craft.best_unit_price(tiers_hdv)
                live = prix is not None
            elif gid and gid in item_prices:
                prix = item_prices[gid]
                live = True
            elif t["tier"] in ("simple", "ga"):
                prix = rune.get("prix_exemple")
                live = False
            elif simple_price is not None:
                prix = round(simple_price * t["mult_base"])
                live = False
            else:
                prix, live = None, False

            if t["tier"] in ("simple", "ga") and prix is not None:
                simple_price = prix

            tiers_out.append({
                "tier": t["tier"], "nom": t["nom"], "mult": t["mult_base"],
                "gid": gid, "prix": prix, "live": live,
            })

        catalog[code] = {
            "code": code, "nom": rune["nom"], "display": rune["display"],
            "nom_rune": rune.get("nom_rune", rune["display"]),
            "poids": rune["poids"], "special": rune.get("special", False),
            "concassable": rune.get("concassable", False),
            "giant_only": rune.get("giant_only", False),
            "tiers": tiers_out,
        }

    # ── Concassage : rows BrisageRow-like (3×inf → 1×sup) ───────────────────
    conc_rows: list[dict] = []
    for code, rune_data in catalog.items():
        tiers = rune_data["tiers"]
        craft_unit_costs: dict[str, float] = {}  # nom → coût craft d'1 unité via concassage
        for i in range(len(tiers) - 1):
            from_t, to_t = tiers[i], tiers[i + 1]
            from_norm = br.normalize_name(from_t["nom"])
            to_norm   = br.normalize_name(to_t["nom"])

            recipe_items = [(3, from_norm)]
            ing_p = {}
            if from_norm in ing_tier_prices:
                ing_p[from_norm] = ing_tier_prices[from_norm]
            # Sous-concassage : Pa peut être produit par concassage de 3 simples, etc.
            ca = {from_norm: craft_unit_costs[from_norm]} if from_norm in craft_unit_costs else {}

            pa = craft.craft_plan(recipe_items, ing_p, craft_alt=ca) if (ing_p or ca) else None
            cpc: dict = {"auto": round(pa["cost_per_craft"], 2) if pa else None}
            for nb in _CRAFT_BATCHES:
                pl = (craft.craft_plan(recipe_items, ing_p, n_crafts=nb, craft_alt=ca)
                      if (ing_p or ca) else None)
                cpc[str(nb)] = round(pl["cost_per_craft"], 2) if pl else None

            if pa:
                craft_unit_costs[to_norm] = pa["cost_per_craft"]

            if not ing_p and not ca:
                # Repli flat : avgprice × 3
                from_gid = from_t.get("gid")
                flat_u = item_prices.get(from_gid) if from_gid else from_t.get("prix")
                flat = round(3 * flat_u, 2) if flat_u else None
                cpc = {k: flat for k in ("auto", "1", "10", "100", "1000")}

            to_gid    = to_t.get("gid")
            prix_vente = (item_prices.get(to_gid) if to_gid else None) or to_t.get("prix")
            cout       = cpc.get("auto")
            benef      = round(prix_vente - cout, 2) if (prix_vente and cout) else None
            rent       = round(prix_vente / cout, 4) if (prix_vente and cout and cout > 0) else None

            recipe = [{
                "nom": from_t["nom"], "qty": 3,
                "tiers": ing_tier_prices.get(from_norm),
                "craft_unit": craft_unit_costs.get(from_norm),  # coût si concassage en sous-craft
            }]
            conc_rows.append({
                "GID": to_gid, "Nom": to_t["nom"], "Type": "Rune", "Niveau": None,
                "Code": code,
                "from_nom": from_t["nom"], "from_tier": from_t["tier"],
                "to_tier": to_t["tier"],
                # Champs BrisageRow (Revenu = prix de vente du résultat)
                "Revenu_theo": prix_vente, "Revenu_reel": None,
                "Cout_HDV": cout, "Base_coeff100": 0,  # base=0 → cmin=null
                "Prix_Moyen": prix_vente,
                "Coeff_Reel": None, "Coeff_Min": None, "Craft_Manquants": None,
                "craft": {"recipe": recipe, "cpc": cpc,
                          "n_auto": pa["n_crafts"] if pa else None, "db": bool(ing_p)},
                "runes_detail": [], "Runes": None,
                "is_concassage": True,
            })

    live_count = sum(1 for r in catalog.values() for t in r["tiers"] if t["live"])
    return {
        "runes": catalog,
        "concassage": conc_rows,
        "live_prices": live_count > 0,
    }


def build_report_data(conn: sqlite3.Connection) -> dict:
    """Assemble le dict complet (sérialisable JSON) consommé par la page."""
    st = store.stats(conn)
    snaps = conn.execute(
        "SELECT snapshot, MIN(ts) AS ts FROM avg_prices GROUP BY snapshot ORDER BY ts"
    ).fetchall()
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "db_path": str(config.DB_PATH),
        "stats": dict(st),
        "snapshots": [{"id": r["snapshot"], "ts": r["ts"]} for r in snaps],
        "items": _price_series(conn),
        "brisage": build_brisage_data(conn),
        "runes": build_rune_data(conn),
    }


# ── Rendu HTML ───────────────────────────────────────────────────────────────
def render_html(data: dict) -> str:
    """Page HTML complète, JSON embarqué. Autonome, hors-ligne, sans dépendance."""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # Empêche une fermeture prématurée de la balise <script> si une donnée
    # contenait "</script>".
    payload = payload.replace("</", "<\\/")
    return _HTML_TEMPLATE.replace("/*__DTV_DATA__*/", payload)


def generate(conn: sqlite3.Connection, out_path: Optional[Path] = None) -> Path:
    """Construit le rapport et l'écrit sur disque. Retourne le chemin écrit."""
    out = Path(out_path or (config.DATA_DIR / "report.html"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(build_report_data(conn)), encoding="utf-8")
    return out


# Le gabarit est dans un module séparé pour garder ce fichier lisible.
from ._report_template import HTML_TEMPLATE as _HTML_TEMPLATE  # noqa: E402
