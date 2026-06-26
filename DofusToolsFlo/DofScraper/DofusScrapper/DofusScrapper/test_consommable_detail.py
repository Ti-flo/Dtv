"""
test_consommable_detail.py — Vérifie la sortie réelle de scrape_detail
(scrape_consommables_dofus_touch.py) sur quelques consommables connus.

Confirme, AVANT de relancer le run complet, que :
  - Effets sont dédupliqués (plus de "900 Vie | 900 Vie")
  - Conditions sont captées (ex: "< 25")
  - Drops_monstres + taux + GID monstre sont captés (ex: Chamane GID 447 <1%)
  - Utilise_dans est capté (ex: Bâton Feuillu…)

Usage :
    python test_consommable_detail.py
    python test_consommable_detail.py "URL1" "URL2"   # tes propres URLs
"""
import sys
import json
import time
import random

from scrape_consommables_dofus_touch import scrape_detail, DELAY_MIN, DELAY_MAX

DEFAULT_URLS = [
    "https://www.dofus-touch.com/fr/mmorpg/encyclopedie/consommables/468-pain-amakna",
    "https://www.dofus-touch.com/fr/mmorpg/encyclopedie/consommables/686-petit-parchemin-intelligence",
]


def main():
    urls = sys.argv[1:] or DEFAULT_URLS
    for u in urls:
        item = {"GID": None, "Nom_FR": "", "Type": "", "Niveau": "", "Lien": u}
        result = scrape_detail(item)
        print("\n" + "=" * 78)
        print(f"  {result.get('Nom_FR')}  ({u})")
        print("=" * 78)
        for k in ("Effets", "Conditions", "Recette", "Utilise_dans", "Drops_monstres"):
            val = result.get(k) or "—"
            print(f"  {k:<16}: {val}")
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


if __name__ == "__main__":
    main()
