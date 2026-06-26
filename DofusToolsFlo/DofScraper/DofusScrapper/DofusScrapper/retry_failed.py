"""
retry_failed.py
Retente uniquement les items qui ont échoué pendant scrap_ressources_full.py
ou DofusScrapper.py (coupures réseau passagères, timeouts DNS).

Ces items ont la clé "erreur" dans le JSON de sortie : ils ont leur
GID/Nom/Type/Niveau (depuis le listing) mais les champs détail vides.

Distingue :
  - échec transitoire (DNS/timeout) → re-fetch réussit → item corrigé
  - 404 permanent (fiche supprimée) → reste en erreur, listé en fin de run

Réutilise EXACTEMENT la logique de parsing des deux scrapers (import).
"""
import json
import time
import random
from pathlib import Path

import pandas as pd

# Réutilise les fonctions de parsing déjà validées
from scrap_ressources_full import scrape_detail as scrape_resource_detail
from DofusScrapper import scrape_detail as scrape_equip_detail

DELAY_MIN = 1.5
DELAY_MAX = 3.5

# (json, xlsx, fonction de scrape)
TARGETS = [
    ("ressources_dofus_touch_full.json",  "ressources_dofus_touch_full.xlsx",  scrape_resource_detail),
    ("equipements_dofus_touch_full.json", "equipements_dofus_touch_full.xlsx", scrape_equip_detail),
]


def retry_file(json_path: str, xlsx_path: str, scrape_fn):
    path = Path(json_path)
    if not path.exists():
        print(f"⏭️  {json_path} absent, ignoré")
        return

    with open(path, encoding="utf-8") as f:
        items = json.load(f)

    failed_idx = [i for i, it in enumerate(items) if it.get("erreur")]
    if not failed_idx:
        print(f"✅ {json_path} — aucun item en erreur, rien à faire")
        return

    print(f"\n🔁 {json_path} — {len(failed_idx)} items à retenter")
    still_failed = []

    for n, i in enumerate(failed_idx, 1):
        item = items[i]
        # On repart de la base listing (sans la clé erreur ni les champs vides)
        base = {k: item[k] for k in ("GID", "Nom_FR", "Type", "Niveau", "Categorie", "Lien")
                if k in item}
        print(f"  [{n}/{len(failed_idx)}] GID {base.get('GID')} — {base.get('Nom_FR')}")
        result = scrape_fn(base)
        if result.get("erreur"):
            still_failed.append(base)
            print(f"      ❌ toujours en échec (probablement 404 définitif)")
        else:
            items[i] = result
            print(f"      ✅ corrigé")
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    # Réécriture
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    pd.DataFrame(items).to_excel(xlsx_path, index=False)
    print(f"  💾 {json_path} + {xlsx_path} mis à jour")

    if still_failed:
        print(f"\n  ⚠️  {len(still_failed)} items définitivement en échec (404, fiche supprimée) :")
        for it in still_failed:
            print(f"      GID {it.get('GID')} — {it.get('Nom_FR')} — {it.get('Lien')}")


if __name__ == "__main__":
    for json_path, xlsx_path, fn in TARGETS:
        retry_file(json_path, xlsx_path, fn)
    print("\n🏁 Backfill terminé.")
