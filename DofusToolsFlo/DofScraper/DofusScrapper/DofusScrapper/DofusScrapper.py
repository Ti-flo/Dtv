"""
DofusScrapper.py — Équipements + Armes Dofus Touch
Source : dofus-touch.com → GIDs = IDs réels du jeu ✅
(ancienne version utilisait dofusbook.net dont les IDs sont internes et ≠ GIDs)

Stratégie en 2 phases :
  Phase 1 (listing)  → GID, Nom_FR, Type, Niveau, Categorie (depuis le tableau)
  Phase 2 (détails)  → Effets, Conditions, Recette, Panoplie

Catégories scrapées :
  /fr/mmorpg/encyclopedie/equipements  (armures, bijoux, capes, chapeaux…)
  /fr/mmorpg/encyclopedie/armes        (épées, bâtons, arcs, baguettes…)

Colonnes de sortie :
  GID | Nom_FR | Niveau | Type | Categorie
  Effets | Conditions | Recette | Panoplie | Lien

Note Nom_EN : slugs anglais ≠ slugs français → 404 sur /en/
  Source correcte = api.dofusdb.fr (PC uniquement)

Fonctionnalités :
  - Checkpoint/resume par catégorie
  - Délais 1.5–3.0s (identique au script ressources qui a tourné sans ban)
  - Sortie JSON + Excel en fin de run
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

DELAY_MIN   = 1.5
DELAY_MAX   = 3.5
MAX_PAGES   = 200
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

PANEL_EFFECTS_KW    = ("caractéristique", "effets", "statistique")
PANEL_RECIPE_KW     = ("recette",)
PANEL_CONDITIONS_KW = ("condition",)
PANEL_SET_KW        = ("panoplie",)


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


# ── Checkpoint ─────────────────────────────────────────────────────────────────
def load_checkpoint() -> dict:
    if CHECKPOINT.exists():
        with open(CHECKPOINT, encoding="utf-8") as f:
            return json.load(f)
    return {"items_base": [], "done_gids": [], "items": []}


def save_checkpoint(cp: dict):
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(cp, f, ensure_ascii=False)


# ── Phase 1 : listing → GID, Nom_FR, Type, Niveau, Categorie ─────────────────
def collect_from_listing() -> list:
    items = []
    for categorie, url_tpl in CATEGORIES.items():
        print(f"\n📄 Phase 1 — {categorie}")
        for page in tqdm(range(1, MAX_PAGES + 1), desc=categorie):
            html = get_html(url_tpl.format(page))
            if not html:
                break
            soup = BeautifulSoup(html, "html.parser")
            rows = soup.select("table.ak-responsivetable tbody tr")
            if not rows:
                print(f"\n🏁 Fin pagination {categorie} à la page {page}")
                break
            for row in rows:
                href, nom = "", ""
                for a in row.select(".ak-linker a"):
                    if a.get("href") and not href:
                        href = a["href"].strip()
                    txt = a.get_text(strip=True)
                    if txt and not nom:
                        nom = txt
                type_tag  = row.select_one("td.item-type")
                level_tag = row.select_one("td.item-level")
                if not href:
                    continue
                url = BASE_URL + href
                items.append({
                    "GID":       extract_gid(url),
                    "Nom_FR":    nom,
                    "Type":      type_tag.get_text(strip=True) if type_tag else "",
                    "Niveau":    (
                        level_tag.get_text(strip=True).replace("Niv. ", "").strip()
                        if level_tag else ""
                    ),
                    "Categorie": categorie,
                    "Lien":      url,
                })
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
    print(f"\n✅ {len(items)} équipements/armes trouvés")
    return items


# ── Phase 2 : fiche détail → effets, conditions, recette, panoplie ────────────
def scrape_detail(item: dict) -> dict:
    url  = item["Lien"]
    html = get_html(url)
    if not html:
        return {**item, "Effets": "", "Conditions": "", "Recette": "", "Panoplie": "", "erreur": "HTTP error"}

    soup = BeautifulSoup(html, "html.parser")
    effets, conditions, recette = [], [], []
    panoplie = ""

    # Filet de sécurité nom
    if not item.get("Nom_FR"):
        h1 = soup.select_one("h1.ak-return-link")
        if h1:
            item = {**item, "Nom_FR": h1.get_text(strip=True)}

    for panel in soup.select("div.ak-container.ak-panel"):
        title_tag = panel.select_one("div.ak-panel-title")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True).lower()
        elems = panel.select("div.ak-list-element")

        if any(kw in title for kw in PANEL_EFFECTS_KW):
            for el in elems:
                front = el.select_one("div.ak-front")
                label = el.select_one("div.ak-title")
                if front and label:
                    effets.append(f"{front.get_text(strip=True)} {label.get_text(strip=True)}")
                elif label:
                    effets.append(label.get_text(strip=True))
                else:
                    txt = el.get_text(" ", strip=True)
                    if txt:
                        effets.append(txt)

        elif any(kw in title for kw in PANEL_RECIPE_KW):
            for el in elems:
                qty  = el.select_one("div.ak-front")
                name = (el.select_one("div.ak-title span.ak-linker")
                        or el.select_one("div.ak-title"))
                if name:
                    qty_txt = qty.get_text(strip=True) if qty else ""
                    recette.append(f"{qty_txt} {name.get_text(strip=True)}".strip())

        elif any(kw in title for kw in PANEL_CONDITIONS_KW):
            for el in elems:
                txt = el.get_text(" ", strip=True)
                if txt:
                    conditions.append(txt)

        elif any(kw in title for kw in PANEL_SET_KW):
            a_tag = panel.select_one("a.ak-linker")
            panoplie = a_tag.get_text(strip=True) if a_tag else title_tag.get_text(strip=True)

    # Le site liste 2 panels «Caractéristiques»/«Effets» identiques → dédup.
    # La condition (ex « PA < 12 ») apparaît aussi dans le bloc d'effets →
    # on la retire des effets puisqu'elle est déjà en Conditions.
    cond_set = set(conditions)
    effets_clean = [e for e in dict.fromkeys(effets) if e not in cond_set]

    return {
        **item,
        "Effets":      " | ".join(effets_clean),
        "Conditions":  " | ".join(dict.fromkeys(conditions)),
        "Recette":     ", ".join(recette),
        "Panoplie":    panoplie,
    }


# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    cp = load_checkpoint()

    if cp["items_base"]:
        print(f"📎 {len(cp['items_base'])} items en checkpoint — phase 1 skippée")
        items_base = cp["items_base"]
    else:
        items_base = collect_from_listing()
        cp["items_base"] = items_base
        save_checkpoint(cp)

    done_gids = set(cp["done_gids"])
    results   = cp["items"]

    todo = [it for it in items_base if it.get("GID") not in done_gids]
    print(f"\n🔍 Phase 2 — {len(todo)} fiches à scraper ({len(done_gids)} déjà faites)")

    for item in tqdm(todo, desc="Scraping équipements"):
        result = scrape_detail(item)
        results.append(result)
        gid = result.get("GID")
        if gid:
            done_gids.add(gid)
        cp["done_gids"] = list(done_gids)
        cp["items"]     = results
        save_checkpoint(cp)
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n✅ JSON : {OUTPUT_JSON}")

    df = pd.DataFrame(results)
    df.to_excel(OUTPUT_XLSX, index=False)
    print(f"✅ Excel : {OUTPUT_XLSX}  ({len(df)} équipements/armes)")

    has_effects = (df["Effets"] != "").sum()
    has_recipe  = (df["Recette"] != "").sum()
    has_set     = (df["Panoplie"] != "").sum()
    print(f"\n📊 Résumé :")
    print(f"   {has_effects}  items avec effets/stats")
    print(f"   {has_recipe}  items craftables")
    print(f"   {has_set}  items en panoplie")
    print(f"\n💡 Nom_EN manquant → api.dofusdb.fr depuis ton PC")
