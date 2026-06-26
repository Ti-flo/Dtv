"""
scrap_ressources_test.py  v2
VERSION DE TEST de scrap_ressources_full.py — 2 pages de listing (~48 ressources).

Corrections v2 :
  - Niveau + Nom_FR + Type capturés dès le LISTING (td.item-level / td.item-type)
    → plus de sélecteur raté sur la page détail
  - Nom_EN supprimé : dofus-touch.com /en/ utilise des slugs anglais différents
    → 404 systématique sur les slugs français. Remplir via api.dofusdb.fr (PC uniquement).
  - Prix_PNJ supprimé : non affiché sur les pages ressources
  - DEBUG panels : affiche tous les titres de panels trouvés sur les 3 premières
    ressources pour identifier le bon sélecteur pour les drops monstres
"""
import re
import json
import time
import random
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
import pandas as pd

# ── Configuration (TEST) ───────────────────────────────────────────────────────
BASE_URL    = "https://www.dofus-touch.com"
LIST_URL_FR = BASE_URL + "/fr/mmorpg/encyclopedie/ressources?page={}"

OUTPUT_JSON = "ressources_dofus_touch_test.json"
OUTPUT_XLSX = "ressources_dofus_touch_test.xlsx"

DELAY_MIN   = 1.0
DELAY_MAX   = 2.0
MAX_PAGES   = 2
MAX_RETRIES = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) "
        "Gecko/20100101 Firefox/124.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.8,en-US;q=0.5,en;q=0.3",
    "Connection": "keep-alive",
}

GID_RE = re.compile(r'/encyclopedie/[\w-]+/(\d+)-')

PANEL_RECIPE_KW = ("recette",)
PANEL_USEDBY_KW = ("est utilisé pour", "utilisé pour les recettes")
# Mots-clés drops à ajuster après avoir vu le debug des titres de panels
PANEL_DROP_KW   = ("monstre", "obtenu en tuant", "droppé", "larguée", "drop")


# ── HTTP helper ────────────────────────────────────────────────────────────────
def get_html(url: str) -> str | None:
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                return r.text
            if r.status_code == 403:
                wait = 10 + attempt * 15
                print(f"\n🚫 403 — pause {wait}s (essai {attempt+1}/{MAX_RETRIES})")
                time.sleep(wait)
            else:
                print(f"\n❌ HTTP {r.status_code} : {url}")
                return None
        except Exception as exc:
            print(f"\n⚠️  Exception : {exc}")
            time.sleep(5)
    return None


def extract_gid(url: str) -> int | None:
    m = GID_RE.search(url)
    return int(m.group(1)) if m else None


# ── Phase 1 : listing → nom, type, niveau (fiable depuis le tableau) ──────────
def collect_from_listing() -> list:
    items = []
    print(f"📄 Phase 1 — collecte depuis listing ({MAX_PAGES} pages)…")
    for page in tqdm(range(1, MAX_PAGES + 1), desc="Pages listing"):
        html = get_html(LIST_URL_FR.format(page))
        if not html:
            break
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("table.ak-responsivetable tbody tr")
        if not rows:
            print(f"\n🏁 Fin pagination à la page {page}")
            break
        for row in rows:
            a         = row.select_one(".ak-linker a")
            type_tag  = row.select_one("td.item-type")
            level_tag = row.select_one("td.item-level")
            if not (a and a.get("href")):
                continue
            url = BASE_URL + a["href"].strip()
            items.append({
                "GID":    extract_gid(url),
                "Nom_FR": a.get_text(strip=True),
                "Type":   type_tag.get_text(strip=True) if type_tag else "",
                "Niveau": (
                    level_tag.get_text(strip=True).replace("Niv. ", "").strip()
                    if level_tag else ""
                ),
                "Lien":   url,
            })
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
    print(f"✅ {len(items)} ressources trouvées")
    return items


# ── Phase 2 : fiche détail → recette, utilisé_dans, drops ────────────────────
_debug_count = 0   # affiche les titres de panels pour les 3 premières fiches

def scrape_detail(item: dict) -> dict:
    global _debug_count
    url = item["Lien"]

    html = get_html(url)
    if not html:
        return {**item, "Recette": "", "Utilise_dans": "", "Drops_monstres": "", "erreur": "HTTP error"}

    soup = BeautifulSoup(html, "html.parser")
    recette, utilise_dans, drops = [], [], []

    # ── DEBUG : afficher tous les titres de panels (3 premières ressources) ──
    if _debug_count < 3:
        all_titles = [
            t.get_text(strip=True)
            for t in soup.select("div.ak-container.ak-panel div.ak-panel-title")
        ]
        print(f"\n  [DEBUG GID {item['GID']} — {item['Nom_FR']}]")
        print(f"  Panels trouvés : {all_titles}")
        _debug_count += 1

    for panel in soup.select("div.ak-container.ak-panel"):
        title_tag = panel.select_one("div.ak-panel-title")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True).lower()
        elems = panel.select("div.ak-list-element")

        if any(kw in title for kw in PANEL_RECIPE_KW) and "utilisé" not in title:
            for el in elems:
                qty  = el.select_one("div.ak-front")
                name = (el.select_one("div.ak-title span.ak-linker")
                        or el.select_one("div.ak-title"))
                if name:
                    qty_txt = qty.get_text(strip=True) if qty else ""
                    recette.append(f"{qty_txt} {name.get_text(strip=True)}".strip())

        elif any(kw in title for kw in PANEL_USEDBY_KW):
            for el in elems:
                name = (el.select_one("div.ak-title span.ak-linker")
                        or el.select_one("div.ak-title"))
                if name:
                    utilise_dans.append(name.get_text(strip=True))

        elif any(kw in title for kw in PANEL_DROP_KW):
            for el in elems:
                monster = (el.select_one("div.ak-title span.ak-linker")
                           or el.select_one("div.ak-title"))
                rate    = el.select_one("div.ak-front")
                if monster:
                    entry = monster.get_text(strip=True)
                    if rate:
                        entry += f" ({rate.get_text(strip=True)})"
                    drops.append(entry)

    return {
        **item,
        "Recette":        ", ".join(recette),
        "Utilise_dans":   ", ".join(utilise_dans),
        "Drops_monstres": " | ".join(drops),
    }


# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    items = collect_from_listing()

    print(f"\n🔍 Phase 2 — {len(items)} fiches à scraper")
    results = []
    for item in tqdm(items, desc="Scraping fiches"):
        results.append(scrape_detail(item))
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n✅ JSON : {OUTPUT_JSON}")

    df = pd.DataFrame(results)
    df.to_excel(OUTPUT_XLSX, index=False)
    print(f"✅ Excel : {OUTPUT_XLSX}  ({len(df)} ressources)")

    # ── Aperçu console ────────────────────────────────────────────────────────
    print("\n📋 Aperçu des 3 premières ressources :")
    for r in results[:3]:
        print(f"\n  GID {r.get('GID')} — {r.get('Nom_FR')}")
        print(f"    Niveau : {r.get('Niveau')}  |  Type : {r.get('Type')}")
        print(f"    Recette : {r.get('Recette') or '—'}")
        print(f"    Utilisé dans : {(r.get('Utilise_dans') or '—')[:90]}")
        print(f"    Drops : {(r.get('Drops_monstres') or '—')[:90]}")

    # ── Diagnostic remplissage ────────────────────────────────────────────────
    print("\n🔎 Diagnostic remplissage :")
    for col in ["Nom_FR", "Niveau", "Type", "Recette", "Utilise_dans", "Drops_monstres"]:
        filled = sum(1 for r in results if r.get(col))
        flag = "✅" if filled else "⚠️ VIDE"
        print(f"   {col:<16} : {filled}/{len(results)} {flag}")

    print("\n💡 Note : Nom_EN doit venir de api.dofusdb.fr (slugs EN différents → 404 sur dofus-touch.com)")
