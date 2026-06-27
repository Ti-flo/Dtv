"""
Test de non-régression du moteur de brisage (dtv/collector/brisage.py).

Vérifie :
  - la formule reproduit objets_runes_formule_modele.xlsx (RuneMaster) au centième
  - le parsing des effets (ranges, %, négatifs, conditions, lignes d'arme)
  - la déduplication des lignes d'effet identiques (catalogue non nettoyé)
  - le calcul de rentabilité

Lancer : python -m dtv.scripts.test_brisage
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dtv.collector import brisage as b


def test_formule():
    # (code, valeur, niveau, runes attendues) — extraits du modèle RuneMaster
    cases = [
        ("in", 8, 2, 1.16),
        ("vi", 5, 2, 1.02),       # rune spéciale (pas de division)
        ("pm", 1, 50, 0.5111),
        ("sa", 40.5, 200, 82.0),
        ("ta", 16, 150, 24.25),
        ("pu", 63, 200, 126.5),
        ("ch", 18, 50, 10.0),
        ("vi", 75.5, 100, 16.1),  # spéciale
        ("pod", 1, 200, 1.5),     # spéciale : (200/100)*1*0.25+1
    ]
    for code, v, niv, expected in cases:
        got = b.rune_yield(code, v, niv)
        assert abs(got - expected) < 0.01, f"{code} V={v} niv={niv}: {got} != {expected}"
    # valeur négative ou nulle → aucune rune
    assert b.rune_yield("fo", -5, 200) == 0.0
    assert b.rune_yield("fo", 0, 200) == 0.0
    print("✅ formule (9 points + bornes) OK")


def test_parsing():
    eff = ("351 à 400 Vitalité | 1 PA | 16 à 20 Prospection | "
           "-16 à 20 Dommages Critiques | PA < 12")
    lines = b.parse_effects(eff)
    by = {l["label"]: l for l in lines}
    assert by["Vitalité"]["valeur"] == 375.5 and by["Vitalité"]["code"] == "vi"
    assert by["PA"]["code"] == "pa"           # « PA » seul → rune pa
    assert by["Prospection"]["code"] == "pp"
    assert by["Dommages Critiques"]["valeur"] == 2.0   # (-16+20)/2
    # « PA < 12 » = condition (pas de nombre en tête) → ignorée
    assert "PA < 12" not in by
    # % vs fixe : « % Résistance Eau » → rep, distinct de « Résistance Eau » → re
    perc = b.parse_effects("6 à 8 % Résistance Eau")[0]
    fixe = b.parse_effects("6 à 8 Résistance Eau")[0]
    assert perc["code"] == "rep" and fixe["code"] == "re"
    # % collé au nombre : « 4 à 6% Coups Critiques » → cc
    assert b.parse_effects("4 à 6% Coups Critiques")[0]["code"] == "cc"
    # ligne d'attaque d'arme « (dommages Air) » → non brisable
    assert b.parse_effects("5 à 10 (dommages Air)")[0]["code"] is None
    print("✅ parsing (ranges, %, négatifs, condition, arme) OK")


def test_dedup():
    # catalogue non nettoyé : bloc d'effets dupliqué → ne doit pas compter ×2
    eff_simple = "351 à 400 Vitalité | 1 PA"
    eff_double = "351 à 400 Vitalité | 1 PA | 351 à 400 Vitalité | 1 PA"
    assert len(b.parse_effects(eff_double)) == 2
    assert b.brisage_revenue(eff_simple, 200) == b.brisage_revenue(eff_double, 200)
    print("✅ déduplication lignes identiques OK")


def test_recette_craft():
    # parsing recette : « qté nom », séparées par virgules, avec/sans préfixe « x »
    assert b.parse_recipe("2 Frêne, 1 Bois de Frêne, 10 Fleur de Lin") == [
        (2, "Frêne"), (1, "Bois de Frêne"), (10, "Fleur de Lin")]
    assert b.parse_recipe("x2 Frêne, 3x Sel") == [(2, "Frêne"), (3, "Sel")]
    assert b.parse_recipe("") == []
    assert b.parse_recipe(None) == []
    # coût de craft = Σ(qté × prix), insensible aux accents/casse
    np = {b.normalize_name("Frêne"): 5000, b.normalize_name("BOIS DE FRENE"): 20000}
    cc = b.craft_cost("2 frene, 1 Bois de Frêne", np)
    assert cc["cost"] == 2 * 5000 + 1 * 20000 and cc["complete"]
    # ingrédient sans prix → coût partiel + signalé incomplet
    cc2 = b.craft_cost("2 Frêne, 1 Truc Inconnu", np)
    assert cc2["cost"] == 10000 and not cc2["complete"] and cc2["missing"] == ["Truc Inconnu"]
    # pas de recette → None (item non craftable)
    assert b.craft_cost("", np) is None
    print("✅ recette + coût de craft (parsing, accents, manquants) OK")


def test_rentabilite():
    eff = "351 à 400 Vitalité | 1 PA"
    res = b.profitability(eff, 200, cout=100000)
    assert res["revenu"] > 0
    assert res["benefice"] == round(res["revenu"] - 100000, 2)
    assert abs(res["rentabilite"] - res["revenu"] / 100000) < 1e-4  # arrondi 4 déc.
    # coût inconnu → bénéfice/rentabilité None mais revenu calculé
    res2 = b.profitability(eff, 200, cout=None)
    assert res2["benefice"] is None and res2["revenu"] > 0
    print("✅ rentabilité (revenu/coût/bénéfice) OK")


def test_coefficient():
    eff = "351 à 400 Vitalité | 1 PA"
    base = b.profitability(eff, 200, cout=None)["revenu_coeff100"]
    # le revenu scale linéairement avec le coeff
    r200 = b.profitability(eff, 200, cout=None, coeff=200)
    assert abs(r200["revenu"] - base * 2) < 0.01
    r50 = b.profitability(eff, 200, cout=None, coeff=50)
    assert abs(r50["revenu"] - base * 0.5) < 0.01
    # coeff_min = coût/base × 100 (break-even, indépendant du coeff demandé)
    cout = base * 1.5            # il faut coeff 150% pour rentrer dans ses frais
    res = b.profitability(eff, 200, cout=cout, coeff=100)
    assert abs(res["coeff_min"] - 150.0) < 0.1
    # au coeff_min exact, bénéfice ≈ 0
    at_min = b.profitability(eff, 200, cout=cout, coeff=res["coeff_min"])
    assert abs(at_min["benefice"]) < 1.0
    print("✅ coefficient de brisage + coeff_min (break-even) OK")


def test_robustesse_cli():
    # le CLI lit des xlsx arbitraires → pandas met NaN pour les cellules vides
    from dtv.scripts import brisage as cli
    nan = float("nan")
    assert cli._to_level(nan) == 0.0          # niveau vide → 0, pas de NaN propagé
    assert cli._to_level("Niv. 200") == 200.0
    assert cli._to_level("") == 0.0
    assert cli._to_gid(nan) is None           # GID vide → None, pas de crash int(NaN)
    assert cli._to_gid(None) is None
    assert cli._to_gid(16186.0) == 16186      # GID float pandas → int
    assert cli._to_gid("123") == 123
    print("✅ robustesse CLI (NaN niveau/GID, xlsx vides) OK")


def test_reference_data():
    assert len(b.RUNES) == 43, f"attendu 43 runes, trouvé {len(b.RUNES)}"
    for special in ("vi", "ii", "pod"):
        assert b.RUNES[special]["special"], f"{special} doit être spéciale"
    assert b.RUNES["pa"]["poids"] == 100.0
    # Dommages Neutre et Terre = runes distinctes en jeu (Do Neutre ≠ Do Terre)
    assert b.effect_to_rune("Dommages Neutre") == "dnf"
    assert b.effect_to_rune("Dommages Terre") == "dtf"
    # PA/PM = géant uniquement
    assert b.RUNES["pa"]["giant_only"] and b.RUNES["pm"]["giant_only"]
    print(f"✅ données de référence ({len(b.RUNES)} runes, mapping {len(b.EFFET_VERS_CODE)}) OK")


if __name__ == "__main__":
    test_reference_data()
    test_formule()
    test_parsing()
    test_dedup()
    test_recette_craft()
    test_rentabilite()
    test_coefficient()
    test_robustesse_cli()
    print("\n🏁 Tous les tests brisage passent.")
