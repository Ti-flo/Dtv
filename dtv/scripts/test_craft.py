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
    assert craft.estimate_n_crafts(2001) == 200
    assert craft.estimate_n_crafts(10_000) == 200
    assert craft.estimate_n_crafts(100_000) == 20
    assert craft.estimate_n_crafts(300_000) == 10
    assert craft.estimate_n_crafts(300_001) == 1
    assert craft.estimate_n_crafts(None) == 1
    print("✅ échelle n_crafts (1000/200/20/10/1, bornes incluses) OK")


def test_best_tier():
    tp = {1: 10, 10: 95, 100: 900, 1000: 8000}   # PU : 10 / 9.5 / 9 / 8
    assert craft.best_tier(tp, 5000) == (1000, 8.0)   # besoin large → plus gros lot
    assert craft.best_tier(tp, 50) == (10, 9.5)       # 100 et 1000 > besoin → x10
    assert craft.best_tier(tp, 1) == (1, 10.0)        # besoin 1 → x1
    # repli : pas de x1, besoin < plus petit lot → ce lot quand même
    assert craft.best_tier({1: None, 10: 95}, 3) == (10, 9.5)
    # meilleur PU même si petit lot (vendeur irrationnel sur les gros lots)
    assert craft.best_tier({1: 5, 10: 95, 100: 900, 1000: 8000}, 5000) == (1, 5.0)
    # aucun prix → None
    assert craft.best_tier({1: None, 10: 0}, 100) is None
    print("✅ best_tier (lot ≤ besoin, meilleur PU, repli, 0 ignoré) OK")


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


def test_plan_manquant():
    plan = craft.craft_plan([(1, "a"), (2, "b")], {"a": {1: 100}})
    assert not plan["complete"] and plan["missing"] == ["b"]
    assert craft.craft_plan([], {}) is None
    print("✅ plan : ingrédient sans prix signalé, recette vide → None OK")


def test_store_tier_prices():
    db = Path(tempfile.mktemp(suffix=".db"))
    conn = store.connect(db)
    now = datetime.now()
    recent = (now - timedelta(days=2)).isoformat()
    old = (now - timedelta(days=30)).isoformat()

    # GID 100 : 2 offres récentes (MIN par tier, un 0 ignoré) + 1 vieille hors fenêtre
    conn.execute("INSERT INTO hdv_offers(ts,gid,nom,prix_x1,prix_x10,prix_x100,prix_x1000,nb_offres,account)"
                 " VALUES (?,?,?,?,?,?,?,?,?)", (recent, 100, "Frene", 12, 95, 900, 0, 3, "j"))
    conn.execute("INSERT INTO hdv_offers(ts,gid,nom,prix_x1,prix_x10,prix_x100,prix_x1000,nb_offres,account)"
                 " VALUES (?,?,?,?,?,?,?,?,?)",
                 ((now - timedelta(days=1)).isoformat(), 100, "Frene", 10, 99, 850, 8000, 2, "j"))
    conn.execute("INSERT INTO hdv_offers(ts,gid,nom,prix_x1,prix_x10,prix_x100,prix_x1000,nb_offres,account)"
                 " VALUES (?,?,?,?,?,?,?,?,?)", (old, 100, "Frene", 1, 1, 1, 1, 1, "j"))
    # GID 200 : aucune offre HDV → repli avgprice (tier x1)
    conn.execute("INSERT INTO avg_prices(snapshot,ts,gid,nom,price,account) VALUES (?,?,?,?,?,?)",
                 ("s1", recent, 200, "Bois", 555, "j"))
    conn.commit()

    res = store.tier_prices_for_gids(conn, [100, 200, 999], days=7)
    assert res[100] == {1: 10, 10: 95, 100: 850, 1000: 8000}, res[100]
    assert res[200] == {1: 555, 10: None, 100: None, 1000: None}, res[200]
    assert 999 not in res
    conn.close()
    os.unlink(db)
    print("✅ store.tier_prices_for_gids (MIN/NULLIF/fenêtre 7j/repli avgprice) OK")


if __name__ == "__main__":
    test_echelle_n_crafts()
    test_best_tier()
    test_plan_bon_marche()
    test_plan_cher()
    test_plan_n_crafts_force()
    test_plan_manquant()
    test_store_tier_prices()
    print("\n🏁 Tous les tests craft passent.")
