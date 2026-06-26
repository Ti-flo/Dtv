"""
DofusScrapper.py — Équipements + Armes Dofus Touch
Source : dofus-touch.com → GIDs = IDs réels du jeu ✅
(ancienne version utilisait dofusbook.net dont les IDs sont internes et ≠ GIDs)

Catégories scrapées :
  /fr/mmorpg/encyclopedie/equipements  (armures, bijoux, capes, chapeaux…)
  /fr/mmorpg/encyclopedie/armes        (épées, bâtons, arcs, baguettes…)

Colonnes de sortie :
  GID | Nom_FR | Nom_EN | Niveau | Type | Categorie
  Effets | Conditions | Recette | Prix_PNJ | Lien

Fonctionnalités :
  - Checkpoint/resume par catégorie
  - Pause aléatoire anti-403
  - Nom EN via URL /en/ (best-effort)
  - Effets, conditions et recette depuis les panneaux de la fiche
  - Sauvegarde JSON + Excel en fin de run
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

# ── Configuration ──────────────────────────────────────────────────────────────
BASE_URL    = "https://www.dofus-touch.com"
CATEGORIES  = {
    "equipements": BASE_URL + "/fr/mmorpg/encyclopedie/equipements?page={}",
    "armes":       BASE_URL + "/fr/mmorpg/encyclopedie/armes?page={}",
}

CHECKPOINT  = Path("checkpoint_equipements.json")
OUTPUT_JSON = "equipements_dofus_touch_full.json"
OUTPUT_XLSX = "equipements_dofus_touch_full.xlsx"

DELAY_MIN   = 1.8
DELAY_MAX   = 3.8
MAX_PAGES   = 200
MAX_RETRIES = 3

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

PANEL_EFFECTS_KW    = ("caractéristique", "effets", "statistique")
PANEL_RECIPE_KW     = ("recette",)
PANEL_CONDITIONS_KW = ("condition",)
PANEL_SET_KW        = ("panoplie",)


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


# ── Checkpoint ─────────────────────────────────────────────────────────────────
def load_checkpoint() -> dict:
    if CHECKPOINT.exists():
        with open(CHECKPOINT, encoding="utf-8") as f:
            return json.load(f)
    return {"links": [], "done_gids": [], "items": []}


def save_checkpoint(cp: dict):
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(cp, f, ensure_ascii=False)


# ── Phase 1 : collecte des liens ───────────────────────────────────────────────
def collect_links(existing: list) -> list:
    if existing:
        print(f"📎 {len(existing)} liens en checkpoint — phase 1 skippée")
        return existing

    links = []
    for category, url_tpl in CATEGORIES.items():
        print(f"\n📄 Collecte liens — {category}")
        for page in tqdm(range(1, MAX_PAGES + 1), desc=category):
            html = get_html(url_tpl.format(page))
            if not html:
                break
            soup = BeautifulSoup(html, "html.parser")
            rows = soup.select("table.ak-responsivetable tbody tr")
            if not rows:
                print(f"\n🏁 Fin pagination {category} à la page {page}")
                break
            for row in rows:
                a = row.select_one(".ak-linker a")
                if a and a.get("href"):
                    links.append(BASE_URL + a["href"].strip())
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    print(f"\n✅ {len(links)} équipements/armes trouvés (toutes catégories)")
    return links


# ── Phase 2 : scrape d'une fiche objet ────────────────────────────────────────
def scrape_item(url_fr: str) -> dict:
    gid    = extract_gid(url_fr)
    url_en = url_fr.replace("/fr/mmorpg/", "/en/mmorpg/")

    # Détecter la catégorie depuis l'URL
    categorie = "equipements"
    if "/armes/" in url_fr or "/armes?" in url_fr or url_fr.split("/encyclopedie/")[1].startswith("armes"):
        categorie = "armes"

    html_fr = get_html(url_fr, "fr")
    if not html_fr:
        return {"GID": gid, "Lien": url_fr, "erreur": "HTTP error"}

    soup = BeautifulSoup(html_fr, "html.parser")

    # ── Nom FR ──────────────────────────────────────────────────────────────
    nom_fr = ""
    h1 = soup.select_one("h1.ak-return-link")
    if h1:
        nom_fr = h1.get_text(strip=True)

    # ── Niveau ──────────────────────────────────────────────────────────────
    niveau = ""
    for sel in ("span.ak-encyclo-detail-level",
                "div.ak-panel-content span.ak-encyclo-detail-level"):
        tag = soup.select_one(sel)
        if tag:
            niveau = tag.get_text(strip=True).replace("Niv. ", "").strip()
            break

    # ── Type ────────────────────────────────────────────────────────────────
    item_type = ""
    for sel in ("div.ak-encyclo-detail-type span",
                "div.ak-encyclo-detail-type"):
        tag = soup.select_one(sel)
        if tag:
            item_type = tag.get_text(strip=True).replace("Type : ", "").strip()
            break

    # ── Prix PNJ ────────────────────────────────────────────────────────────
    prix_pnj = ""
    tag = soup.select_one("div.ak-encyclo-detail-price")
    if tag:
        prix_pnj = tag.get_text(separator=" ", strip=True)

    # ── Panels ──────────────────────────────────────────────────────────────
    effets     = []
    conditions = []
    recette    = []
    panoplie   = ""

    for panel in soup.select("div.ak-container.ak-panel"):
        title_tag = panel.select_one("div.ak-panel-title")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True).lower()
        elems = panel.select("div.ak-list-element")

        if any(kw in title for kw in PANEL_EFFECTS_KW):
            for el in elems:
                # Essayer de lire quantité + nom (format "+100 à 150 / Vitalité")
                front = el.select_one("div.ak-front")
                label = el.select_one("div.ak-title")
                if front and label:
                    effets.append(f"{front.get_text(strip=True)} {label.get_text(strip=True)}")
                elif label:
                    effets.append(label.get_text(strip=True))
                else:
                    text = el.get_text(separator=" ", strip=True)
                    if text:
                        effets.append(text)

        elif any(kw in title for kw in PANEL_RECIPE_KW):
            for el in elems:
                qty  = el.select_one("div.ak-front")
                name = el.select_one("div.ak-title span.ak-linker")
                if not name:
                    name = el.select_one("div.ak-title")
                if name:
                    qty_txt = qty.get_text(strip=True) if qty else ""
                    recette.append(f"{qty_txt} {name.get_text(strip=True)}".strip())

        elif any(kw in title for kw in PANEL_CONDITIONS_KW):
            for el in elems:
                text = el.get_text(separator=" ", strip=True)
                if text:
                    conditions.append(text)

        elif any(kw in title for kw in PANEL_SET_KW):
            a_tag = panel.select_one("a.ak-linker")
            if a_tag:
                panoplie = a_tag.get_text(strip=True)
            else:
                panoplie = title_tag.get_text(strip=True)

    # ── Nom EN (best-effort) ─────────────────────────────────────────────────
    nom_en = ""
    html_en = get_html(url_en, "en")
    if html_en:
        soup_en = BeautifulSoup(html_en, "html.parser")
        h1_en = soup_en.select_one("h1.ak-return-link")
        if h1_en:
            nom_en = h1_en.get_text(strip=True)

    return {
        "GID":        gid,
        "Nom_FR":     nom_fr,
        "Nom_EN":     nom_en,
        "Niveau":     niveau,
        "Type":       item_type,
        "Categorie":  categorie,
        "Effets":     " | ".join(effets),
        "Conditions": " | ".join(conditions),
        "Recette":    ", ".join(recette),
        "Panoplie":   panoplie,
        "Prix_PNJ":   prix_pnj,
        "Lien":       url_fr,
    }


# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    cp    = load_checkpoint()
    links = collect_links(cp["links"])
    cp["links"] = links
    save_checkpoint(cp)

    done_gids = set(cp["done_gids"])
    items     = cp["items"]

    todo = [u for u in links if extract_gid(u) not in done_gids]
    print(f"\n🔍 Phase 2 — {len(todo)} items à scraper ({len(done_gids)} déjà faits)")

    for url in tqdm(todo, desc="Scraping équipements"):
        result = scrape_item(url)
        items.append(result)
        gid = result.get("GID")
        if gid:
            done_gids.add(gid)
        cp["done_gids"] = list(done_gids)
        cp["items"]     = items
        save_checkpoint(cp)
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    # ── Sauvegarde finale ─────────────────────────────────────────────────────
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"\n✅ JSON : {OUTPUT_JSON}")

    df = pd.DataFrame(items)
    df.to_excel(OUTPUT_XLSX, index=False)
    print(f"✅ Excel : {OUTPUT_XLSX}  ({len(df)} équipements/armes)")

    # Résumé
    has_recipe  = (df["Recette"] != "").sum()
    has_effects = (df["Effets"] != "").sum()
    has_set     = (df["Panoplie"] != "").sum()
    print(f"\n📊 Résumé :")
    print(f"   {has_effects} items avec effets/stats")
    print(f"   {has_recipe} items avec recette craft")
    print(f"   {has_set} items faisant partie d'une panoplie")
