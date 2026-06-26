"""
clean_effets_equipements.py — Nettoie les Effets dupliqués SANS re-scraper.

Le site dofus-touch.com liste 2 panels «Caractéristiques»/«Effets» identiques,
donc l'ancien run de DofusScrapper.py a écrit chaque bloc d'effets deux fois
(2773/2825 items). La condition (ex « PA < 12 ») fuite aussi dans les effets.

Ce script lit le JSON déjà produit, déduplique les Effets (en préservant
l'ordre) et retire les entrées déjà présentes dans Conditions, puis réécrit
JSON + Excel. Aucune requête réseau — c'est une simple opération sur les
chaînes déjà capturées (résultat identique à un re-scrape avec le code corrigé).

Idempotent : relançable sans risque (re-dédupliquer ne change rien).

Usage :
    python clean_effets_equipements.py
"""
import json
from pathlib import Path

import pandas as pd

JSON_PATH = Path("equipements_dofus_touch_full.json")
XLSX_PATH = Path("equipements_dofus_touch_full.xlsx")
SEP = " | "


def clean_effets(effets: str, conditions: str) -> str:
    if not isinstance(effets, str) or not effets:
        return effets or ""
    cond_set = set()
    if isinstance(conditions, str) and conditions:
        cond_set = {c.strip() for c in conditions.split(SEP) if c.strip()}
    parts = [p.strip() for p in effets.split(SEP) if p.strip()]
    # dict.fromkeys = dédup en préservant l'ordre
    cleaned = [p for p in dict.fromkeys(parts) if p not in cond_set]
    return SEP.join(cleaned)


def main():
    if not JSON_PATH.exists():
        print(f"❌ {JSON_PATH} introuvable — lance ce script depuis le dossier des scrapers.")
        return

    with open(JSON_PATH, encoding="utf-8") as f:
        items = json.load(f)

    changed = 0
    for it in items:
        before = it.get("Effets", "")
        after = clean_effets(before, it.get("Conditions", ""))
        if after != before:
            it["Effets"] = after
            changed += 1

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    pd.DataFrame(items).to_excel(XLSX_PATH, index=False)

    print(f"✅ {changed}/{len(items)} items nettoyés (effets dédupliqués)")
    print(f"💾 {JSON_PATH} + {XLSX_PATH} réécrits")

    # Aperçu de contrôle
    sample = next((it for it in items if it.get("Nom_FR") == "Coiffe Ranshi"), None)
    if sample:
        print("\n🔎 Contrôle — Coiffe Ranshi :")
        print(f"   Effets    : {sample.get('Effets')}")
        print(f"   Conditions: {sample.get('Conditions')}")


if __name__ == "__main__":
    main()
