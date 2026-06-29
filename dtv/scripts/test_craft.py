"""
Test de non-régression du moteur de plan de craft (dtv/collector/craft.py) et de
la requête de prix de lot (dtv/collector/store.tier_prices_for_gids).

Vérifie :
  - l'échelle nombre de crafts (1000/200/20/10/1) selon le coût
  - le choix du tier d'achat optimal (lot ≤ besoin, meilleur prix unitaire)
  - le plan complet (craft bon marché → gros tiers ; cher → petits tiers)
  - la requête SQLite : MIN par tier, 0 ignoré, fenêtre temporelle, repli avgprice

Lancer : python -m dtv.scripts.test_craft
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dtv.collector import craft
from dtv.collector import store


def test_echelle_n_crafts():
    # bornes hautes incluses, sauts aux frontières
    assert craft.estimate_n_crafts(1) == 1000
    assert craft.estimate_n_crafts(2000) == 1000
    assert craft.estimate_n_crafts(2001) == 100
    assert craft.estimate_n_crafts(10_000) == 100
    assert craft.estimate_n_crafts(100_000) == 20
    assert craft.estimate_n_crafts(300_000) == 10
    assert craft.estimate_n_crafts(300_001) == 1
    assert craft.estimate_n_crafts(None) == 1
    print("✅ échelle n_crafts (1000/100/20/10/1, bornes incluses) OK")


def test_best_tier():
    tp = {1: 10, 10: 95, 100: 900, 1000: 8000}   # PU : 10 / 9.5 / 9 / 8
    # besoin 5000 → x1000 seul pratique (ceil(5000/1000)=5 ≤ 20) et meilleur PU
    assert craft.best_tier(tp, 5000) == (1000, 8.0)
    # besoin 50 → x10 seul ≤ 50 ET pratique (ceil(50/10)=5) ; x1 donne 50 achats > 20
    assert craft.best_tier(tp, 50) == (10, 9.5)
    # besoin 1 → seul x1 ≤ 1, pratique (1 achat)
    assert craft.best_tier(tp, 1) == (1, 10.0)
    # besoin 1000 → x100 (10 achats) et x1000 (1 achat) pratiques ; meilleur PU = x1000
    assert craft.best_tier(tp, 1000) == (1000, 8.0)
    # repli : besoin < plus petit lot disponible → ce lot (1 transaction)
    assert craft.best_tier({1: None, 10: 95}, 3) == (10, 9.5)
    # aucun tier pratique (seul x10 dispo, besoin 3000 → 300 achats) → plus grand usable
    assert craft.best_tier({1: None, 10: 95, 100: None, 1000: None}, 3000) == (10, 9.5)
    # vendeur irrationnel sur gros lots : x1 moins cher/u mais 5000 achats → x1000 (pratique)
    assert craft.best_tier({1: 5, 10: 95, 100: 900, 1000: 8000}, 5000) == (1000, 8.0)
    # aucun prix → None
    assert craft.best_tier({1: None, 10: 0}, 100) is None
    print("✅ best_tier (praticabilite ≤20 achats d'abord, meilleur PU ensuite) OK")


def test_plan_bon_marche():
    recipe = [(2, "frene"), (1, "bois de frene")]
    prices = {
        "frene": {1: 10, 10: 95, 100: 900, 1000: 8000},
        "bois de frene": {1: 50, 10: 480, 100: 4500, 1000: 40000},
    }
    plan = craft.craft_plan(recipe, prices)
    assert plan["complete"]
    assert plan["n_crafts"] == 1000             # coût naïf 56 ≤ 2000
    assert plan["cost_per_craft"] == 2 * 8 + 1 * 40   # tout en x1000
    assert all(d["tier"] == 1000 for d in plan["detail"])
    print("✅ plan craft bon marché → 1000 crafts → achat x1000 OK")


def test_plan_cher():
    recipe = [(5, "ressource chere")]
    prices = {"ressource chere": {1: 90000, 10: 880000, 100: None, 1000: None}}
    plan = craft.craft_plan(recipe, prices)
    assert plan["n_crafts"] == 1               # naïf 5×88000 = 440k > 300k
    assert plan["detail"][0]["tier"] == 1      # besoin 5 → x1 (lot 10 > besoin)
    print("✅ plan craft cher → 1 craft → achat x1 OK")


def test_plan_n_crafts_force():
    recipe = [(3, "x")]
    prices = {"x": {1: 100, 10: 950, 100: 9000, 1000: 80000}}
    plan = craft.craft_plan(recipe, prices, n_crafts=40)
    assert plan["n_crafts"] == 40
    # besoin = 3 × 40 = 120 → x100 utilisable (PU 90), pas x1000 (1000 > 120)
    assert plan["detail"][0]["tier"] == 100
    print("✅ plan avec --n-crafts forcé (tier suit le besoin) OK")


def test_plan_n_purchases():
    # besoin 3×1000 = 3000 → tier x1000 → 3 achats
    recipe = [(3, "x")]
    prices = {"x": {1: 10, 10: 95, 100: 900, 1000: 8000}}
    plan = craft.craft_plan(recipe, prices)
    d = plan["detail"][0]
    assert d["tier"] == 1000
    assert d["n_purchases"] == 3           # ceil(3000 / 1000)
    # si seul x10 dispo, besoin 3000 → 300 achats
    prices2 = {"x": {1: None, 10: 95, 100: None, 1000: None}}
    plan2 = craft.craft_plan(recipe, prices2)
    d2 = plan2["detail"][0]
    assert d2["tier"] == 10
    assert d2["n_purchases"] == 300        # ceil(3000 / 10) — impraticable !
    print("✅ n_purchases (nb de lots à acheter dans l'HDV) OK")


def test_plan_manquant():
    plan = craft.craft_plan([(1, "a"), (2, "b")], {"a": {1: 100}})
    assert not plan["complete"] and plan["missing"] == ["b"]
    assert craft.craft_plan([], {}) is None
    print("✅ plan : ingrédient sans prix signalé, recette vide → None OK")


def test_resolve_recursion():
    # lingot craftable depuis 2 minerai : crafter (2×20=40) < acheter (100).
    recipes = {"lingot": [(2, "minerai")]}
    buy = {"lingot": 100, "minerai": 20}
    res = craft.resolve_craft_unit_costs(recipes, buy)
    assert res["minerai"]["unit"] == 20 and res["minerai"]["method"] == "buy"
    assert res["lingot"]["craft_unit"] == 40
    assert res["lingot"]["unit"] == 40 and res["lingot"]["method"] == "craft"

    # si l'achat est moins cher que le craft → on achète.
    res2 = craft.resolve_craft_unit_costs({"x": [(5, "y")]}, {"x": 30, "y": 20})
    assert res2["x"]["method"] == "buy" and res2["x"]["unit"] == 30   # craft = 100 > 30

    # cycle a→b→a : pas de boucle infinie, repli sur l'achat.
    res3 = craft.resolve_craft_unit_costs({"a": [(1, "b")], "b": [(1, "a")]},
                                          {"b": 10})  # a non achetable
    assert res3["b"]["unit"] == 10                    # b se replie sur l'achat (cycle)
    assert res3["a"]["unit"] == 10                    # a = craft via b

    # ingrédient profond non chiffrable → craft impossible, item non résoluble.
    res4 = craft.resolve_craft_unit_costs({"top": [(1, "mid")], "mid": [(1, "leaf")]}, {})
    assert res4["top"]["unit"] is None
    print("✅ resolve_craft_unit_costs (min(achat,craft), cycle, manquant) OK")


def test_plan_craft_alt():
    # 2 lingots par craft ; lingot dispo à l'HDV (PU 100) MAIS craftable à 40.
    recipe = [(2, "lingot")]
    tp = {"lingot": {1: 100, 10: 1000, 100: 10000, 1000: 100000}}
    plan = craft.craft_plan(recipe, tp, n_crafts=10, craft_alt={"lingot": 40})
    d = plan["detail"][0]
    assert d["method"] == "craft" and d["tier"] is None and d["unit_price"] == 40
    assert plan["cost_per_craft"] == 2 * 40            # on craft l'ingrédient

    # craft plus cher que l'achat → on achète (comportement historique).
    plan2 = craft.craft_plan(recipe, tp, n_crafts=10, craft_alt={"lingot": 999})
    d2 = plan2["detail"][0]
    assert d2["method"] == "buy" and d2["unit_price"] == 100

    # sans craft_alt → identique à avant (achat HDV seul).
    plan3 = craft.craft_plan(recipe, tp, n_crafts=10)
    assert plan3["detail"][0]["method"] == "buy"
    print("✅ craft_plan avec craft_alt (min achat/craft par ingrédient) OK")


def test_store_tier_prices():
    db = Path(tempfile.mktemp(suffix=".db"))
    conn = store.connect(db)
    now = datetime.now()
    recent = (now - timedelta(days=2)).isoformat()
    yesterday = (now - timedelta(days=1)).isoformat()
    old = (now - timedelta(days=30)).isoformat()

    # GID 100 : 2 snapshots récents → on prend le DERNIER (yesterday), pas le MIN
    #   recent   : x1=12 x10=95  x100=900 x1000=0    (plus vieux)
    #   yesterday: x1=10 x10=99  x100=850 x1000=8000  (plus récent → utilisé)
    conn.execute("INSERT INTO hdv_offers(ts,gid,nom,prix_x1,prix_x10,prix_x100,prix_x1000,nb_offres,account)"
                 " VALUES (?,?,?,?,?,?,?,?,?)", (recent, 100, "Frene", 12, 95, 900, 0, 3, "j"))
    conn.execute("INSERT INTO hdv_offers(ts,gid,nom,prix_x1,prix_x10,prix_x100,prix_x1000,nb_offres,account)"
                 " VALUES (?,?,?,?,?,?,?,?,?)", (yesterday, 100, "Frene", 10, 99, 850, 8000, 2, "j"))
    # GID 100 aussi : snapshot périmé (>7j) → ignoré même s'il est plus récent que rien
    conn.execute("INSERT INTO hdv_offers(ts,gid,nom,prix_x1,prix_x10,prix_x100,prix_x1000,nb_offres,account)"
                 " VALUES (?,?,?,?,?,?,?,?,?)", (old, 100, "Frene", 1, 1, 1, 1, 1, "j"))
    # GID 200 : aucun snapshot HDV → repli avgprice (tier x1 uniquement)
    conn.execute("INSERT INTO avg_prices(snapshot,ts,gid,nom,price,account) VALUES (?,?,?,?,?,?)",
                 ("s1", recent, 200, "Bois", 555, "j"))
    # GID 300 : seul snapshot périmé → repli avgprice
    conn.execute("INSERT INTO hdv_offers(ts,gid,nom,prix_x1,prix_x10,prix_x100,prix_x1000,nb_offres,account)"
                 " VALUES (?,?,?,?,?,?,?,?,?)", (old, 300, "Vieux", 5, 45, 400, 0, 1, "j"))
    conn.execute("INSERT INTO avg_prices(snapshot,ts,gid,nom,price,account) VALUES (?,?,?,?,?,?)",
                 ("s1", recent, 300, "Vieux", 7, "j"))
    conn.commit()

    res = store.tier_prices_for_gids(conn, [100, 200, 300, 999], days=7)
    # GID 100 : dernier snapshot (yesterday) — x10=99 et x1000=8000, pas MIN
    assert res[100] == {1: 10, 10: 99, 100: 850, 1000: 8000}, res[100]
    # GID 200 : pas de HDV → avgprice au tier x1
    assert res[200] == {1: 555, 10: None, 100: None, 1000: None}, res[200]
    # GID 300 : seul snapshot périmé → repli avgprice
    assert res[300] == {1: 7, 10: None, 100: None, 1000: None}, res[300]
    # GID 999 : absent partout
    assert 999 not in res
    conn.close()
    os.unlink(db)
    print("✅ store.tier_prices_for_gids (dernier snapshot / repli avgprice si >7j) OK")


def test_store_brisage_observations():
    db = Path(tempfile.mktemp(suffix=".db"))
    conn = store.connect(db)
    now = datetime.now()
    old = (now - timedelta(days=5)).isoformat()
    recent = (now - timedelta(days=1)).isoformat()

    # GID 850 : 2 brisages → on prend le DERNIER (recent), coeff 57 (pas l'ancien 80)
    conn.execute("INSERT INTO brisage_obs(ts,gid,nom,coefficient_reel,dernier_brisage,runes_obtenues,account)"
                 " VALUES (?,?,?,?,?,?,?)", (old, 850, "Anneau Agilesque", 80.0, "2026-06-23", "ag×2", "j"))
    conn.execute("INSERT INTO brisage_obs(ts,gid,nom,coefficient_reel,dernier_brisage,runes_obtenues,account)"
                 " VALUES (?,?,?,?,?,?,?)", (recent, 850, "Anneau Agilesque", 57.0, "2026-06-28", "ag×2", "j"))
    # GID 900 : coeff NULL (brisage sans coeff capté) → exclu
    conn.execute("INSERT INTO brisage_obs(ts,gid,nom,coefficient_reel,dernier_brisage,runes_obtenues,account)"
                 " VALUES (?,?,?,?,?,?,?)", (recent, 900, "Sans Coeff", None, "2026-06-28", "", "j"))
    conn.commit()

    obs = store.brisage_observations(conn)
    assert obs[850]["coeff"] == 57.0, obs[850]              # dernier, pas l'ancien
    assert obs[850]["date"] == "2026-06-28", obs[850]
    assert 900 not in obs                                   # coeff NULL → exclu
    conn.close()
    os.unlink(db)
    print("✅ store.brisage_observations (dernier coeff par GID, NULL exclu) OK")


def test_parse_recycling_runes():
    from dtv.collector.passive_capture import parse_recycling_runes
    # Structure réelle du message (HAR) : objectGid / objectQty (casse Dofus)
    real = [{"_type": "RecyclingResult", "objectGid": 1519, "objectQty": 3}]
    assert parse_recycling_runes(real, {1519: "ag"}) == "ag×3"
    # GID rune non mappé → « gid<N> » et JAMAIS « gidNone » (l'ancien bug)
    assert parse_recycling_runes(real, {}) == "gid1519×3"
    # Aucune rune (coeff bas, resultObjects vide)
    assert parse_recycling_runes([], {1519: "ag"}) == ""
    # Repli ancienne casse objectGID/quantity (robustesse variantes serveur)
    assert parse_recycling_runes([{"objectGID": 1519, "quantity": 2}], {1519: "ag"}) == "ag×2"
    print("✅ parse_recycling_runes (objectGid/objectQty, plus de gidNone) OK")


if __name__ == "__main__":
    test_echelle_n_crafts()
    test_best_tier()
    test_plan_bon_marche()
    test_plan_cher()
    test_plan_n_crafts_force()
    test_plan_n_purchases()
    test_plan_manquant()
    test_resolve_recursion()
    test_plan_craft_alt()
    test_store_tier_prices()
    test_store_brisage_observations()
    test_parse_recycling_runes()
    print("\n🏁 Tous les tests craft passent.")
