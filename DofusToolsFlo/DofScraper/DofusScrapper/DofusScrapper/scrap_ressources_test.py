"""
scrap_ressources_test.py
VERSION DE TEST de scrap_ressources_full.py — ne scrappe que les 2 premières pages
de listing (~2 × ~24 ressources). Sert à valider les sélecteurs et le format de
sortie AVANT de lancer le scrap complet.

Différences avec scrap_ressources_full.py :
  - MAX_PAGES = 2 (au lieu de 120)
  - Fichiers checkpoint/sortie séparés (préfixe "test_")
  - Délais raccourcis (le run complet garde les délais prudents)

Une fois le résultat validé → lancer scrap_ressources_full.py.
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
BASE_URL      = "https://www.dofus-touch.com"
LIST_URL_FR   = BASE_URL + "/fr/mmorpg/encyclopedie/ressources?page={}"

CHECKPOINT    = Path("checkpoint_ressources_test.json")
OUTPUT_JSON   = "ressources_dofus_touch_test.json"
OUTPUT_XLSX   = "ressources_dofus_touch_test.xlsx"

DELAY_MIN     = 1.0
DELAY_MAX     = 2.0
MAX_PAGES     = 2            # ← TEST : seulement 2 pages de listing
MAX_RETRIES   = 3

HEADERS_FR = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) "
        "Gecko/20100101 Firefox/124.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.8,en-US;q=0.5,en;q=0.3",
    "Connection": "keep-alive",
}
HEADERS_EN = {**HEADERS_FR, "Accept-Language": "en-US,en;q=0.9,fr;q=0.3"}

GID_RE = re.compile(r'/encyclopedie/[\w-]+/(\d+)-')

PANEL_DROP_KW   = ("monstre", "obtenu en tuant", "droppé", "larguée par", "larguée", "larguées")
PANEL_RECIPE_KW = ("recette",)
PANEL_USEDBY_KW = ("est utilisé pour", "utilisé pour les recettes")


# ── HTTP helper ────────────────────────────────────────────────────────────────
def get_html(url: str, lang: str = "fr") -> str | None:
    headers = HEADERS_FR if lang == "fr" else HEADERS_EN
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, headers=headers, timeout=15)
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


# ── Phase 1 : collecte des liens (2 pages) ─────────────────────────────────────
def collect_links() -> list:
    links = []
    print(f"📄 Phase 1 (TEST) — collecte des URLs sur {MAX_PAGES} pages…")
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
            a = row.select_one(".ak-linker a")
            if a and a.get("href"):
                links.append(BASE_URL + a["href"].strip())
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
    print(f"✅ {len(links)} ressources trouvées (test)")
    return links


# ── Phase 2 : scrape d'une fiche ressource ────────────────────────────────────
def scrape_resource(url_fr: str) -> dict:
    gid = extract_gid(url_fr)
    url_en = url_fr.replace("/fr/mmorpg/", "/en/mmorpg/")

    html_fr = get_html(url_fr, "fr")
    if not html_fr:
        return {"GID": gid, "Lien": url_fr, "erreur": "HTTP error"}

    soup = BeautifulSoup(html_fr, "html.parser")

    nom_fr = ""
    h1 = soup.select_one("h1.ak-return-link")
    if h1:
        nom_fr = h1.get_text(strip=True)

    niveau = ""
    for sel in ("span.ak-encyclo-detail-level",
                "div.ak-panel-content span.ak-encyclo-detail-level"):
        tag = soup.select_one(sel)
        if tag:
            niveau = tag.get_text(strip=True).replace("Niv. ", "").strip()
            break

    item_type = ""
    for sel in ("div.ak-encyclo-detail-type span",
                "div.ak-encyclo-detail-type"):
        tag = soup.select_one(sel)
        if tag:
            item_type = tag.get_text(strip=True).replace("Type : ", "").strip()
            break

    prix_pnj = ""
    tag = soup.select_one("div.ak-encyclo-detail-price")
    if tag:
        prix_pnj = tag.get_text(separator=" ", strip=True)

    recette, utilise_dans, drops = [], [], []

    for panel in soup.select("div.ak-container.ak-panel"):
        title_tag = panel.select_one("div.ak-panel-title")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True).lower()
        elems = panel.select("div.ak-list-element")

        if any(kw in title for kw in PANEL_RECIPE_KW) and "utilisé" not in title:
            for el in elems:
                qty  = el.select_one("div.ak-front")
                name = el.select_one("div.ak-title span.ak-linker") or el.select_one("div.ak-title")
                if name:
                    qty_txt = qty.get_text(strip=True) if qty else ""
                    recette.append(f"{qty_txt} {name.get_text(strip=True)}".strip())

        elif any(kw in title for kw in PANEL_USEDBY_KW):
            for el in elems:
                name = el.select_one("div.ak-title span.ak-linker") or el.select_one("div.ak-title")
                if name:
                    utilise_dans.append(name.get_text(strip=True))

        elif any(kw in title for kw in PANEL_DROP_KW):
            for el in elems:
                monster = el.select_one("div.ak-title span.ak-linker") or el.select_one("div.ak-title")
                rate = el.select_one("div.ak-front")
                if monster:
                    entry = monster.get_text(strip=True)
                    if rate:
                        entry += f" ({rate.get_text(strip=True)})"
                    drops.append(entry)

    nom_en = ""
    html_en = get_html(url_en, "en")
    if html_en:
        soup_en = BeautifulSoup(html_en, "html.parser")
        h1_en = soup_en.select_one("h1.ak-return-link")
        if h1_en:
            nom_en = h1_en.get_text(strip=True)

    return {
        "GID":           gid,
        "Nom_FR":        nom_fr,
        "Nom_EN":        nom_en,
        "Niveau":        niveau,
        "Type":          item_type,
        "Prix_PNJ":      prix_pnj,
        "Recette":       ", ".join(recette),
        "Utilise_dans":  ", ".join(utilise_dans),
        "Drops_monstres": " | ".join(drops),
        "Lien":          url_fr,
    }


# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    links = collect_links()
    items = []

    print(f"\n🔍 Phase 2 (TEST) — {len(links)} ressources à scraper")
    for url in tqdm(links, desc="Scraping ressources"):
        items.append(scrape_resource(url))
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"\n✅ JSON : {OUTPUT_JSON}")

    df = pd.DataFrame(items)
    df.to_excel(OUTPUT_XLSX, index=False)
    print(f"✅ Excel : {OUTPUT_XLSX}  ({len(df)} ressources)")

    # ── Aperçu console pour vérifier que tout est bien rempli ────────────────
    print("\n📋 Aperçu des 3 premières ressources :")
    for item in items[:3]:
        print(f"\n  GID {item.get('GID')} — {item.get('Nom_FR')} / {item.get('Nom_EN')}")
        print(f"    Niveau : {item.get('Niveau')}  |  Type : {item.get('Type')}")
        print(f"    Prix PNJ : {item.get('Prix_PNJ') or '—'}")
        print(f"    Recette : {item.get('Recette') or '—'}")
        print(f"    Utilisé dans : {(item.get('Utilise_dans') or '—')[:80]}")
        print(f"    Drops : {(item.get('Drops_monstres') or '—')[:80]}")

    # ── Diagnostic : colonnes vides ? ────────────────────────────────────────
    print("\n🔎 Diagnostic remplissage des colonnes :")
    for col in ["Nom_FR", "Nom_EN", "Niveau", "Type", "Prix_PNJ",
                "Recette", "Utilise_dans", "Drops_monstres"]:
        filled = sum(1 for it in items if it.get(col))
        flag = "✅" if filled else "⚠️ VIDE"
        print(f"   {col:<16} : {filled}/{len(items)} {flag}")
