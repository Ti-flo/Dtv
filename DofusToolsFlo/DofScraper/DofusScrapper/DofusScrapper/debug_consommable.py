"""
debug_consommable.py — Inspecte la structure HTML d'une fiche consommable.

But : vérifier si les panels "drops monstres" et "utilisé dans les recettes"
existent sur les pages consommables et avec quel titre exact, pour savoir si
scrape_consommables_dofus_touch.py rate des données ou si elles sont absentes.

Usage :
    # avec des URLs précises (consommables que tu SAIS droppés / utilisés en recette)
    python debug_consommable.py https://www.dofus-touch.com/fr/mmorpg/encyclopedie/consommables/XXXX-nom

    # ou sans argument → utilise la liste DEFAULT_URLS ci-dessous (à éditer)

Pour chaque page il affiche :
  - tous les titres de panels trouvés
  - pour CHAQUE panel : le HTML du 1er élément (tronqué) pour voir où sont
    le nom du monstre, le taux %, le nom de la recette…
"""
import sys
import requests
from bs4 import BeautifulSoup

# ⬇️ ÉDITE cette liste : mets 2-3 consommables que tu sais droppés par un monstre
#    et/ou utilisés comme ingrédient dans une autre recette.
DEFAULT_URLS = [
    # "https://www.dofus-touch.com/fr/mmorpg/encyclopedie/consommables/XXXX-nom",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) "
        "Gecko/20100101 Firefox/124.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.8,en-US;q=0.5,en;q=0.3",
}


def dump(url: str):
    print("\n" + "=" * 78)
    print(f"URL : {url}")
    print("=" * 78)
    r = requests.get(url, headers=HEADERS, timeout=15)
    print(f"HTTP {r.status_code}")
    if r.status_code != 200:
        return
    soup = BeautifulSoup(r.text, "html.parser")

    h1 = soup.select_one("h1.ak-return-link")
    print(f"Nom (h1) : {h1.get_text(strip=True) if h1 else '—'}")

    panels = soup.select("div.ak-container.ak-panel")
    print(f"\n{len(panels)} panels trouvés :")
    for i, panel in enumerate(panels):
        title_tag = panel.select_one("div.ak-panel-title")
        title = title_tag.get_text(strip=True) if title_tag else "(sans titre)"
        elems = panel.select("div.ak-list-element")
        print(f"\n  ── Panel #{i}: «{title}»  ({len(elems)} éléments) ──")
        if elems:
            html = elems[0].prettify()
            # tronque pour rester lisible
            snippet = html[:1200]
            print("  " + snippet.replace("\n", "\n  "))


if __name__ == "__main__":
    urls = sys.argv[1:] or DEFAULT_URLS
    if not urls:
        print("⚠️  Aucune URL. Passe-les en argument ou édite DEFAULT_URLS.")
        print("    Exemple : python debug_consommable.py https://www.dofus-touch.com/fr/mmorpg/encyclopedie/consommables/548-pain-au-ble-complet")
        sys.exit(1)
    for u in urls:
        dump(u)
