"""
scrap_ressources_full.py
Scrape complet des ressources Dofus Touch depuis dofus-touch.com.
Source : dofus-touch.com → GIDs = IDs réels du jeu ✅

Stratégie en 2 phases :
  Phase 1 (listing)  → GID, Nom_FR, Type, Niveau  (depuis le tableau, fiable)
  Phase 2 (détails)  → Recette, Utilise_dans, Drops_monstres + taux + GID monstre

Colonnes de sortie :
  GID | Nom_FR | Niveau | Type
  Recette | Utilise_dans | Drops_monstres | Lien

Note Nom_EN : dofus-touch.com utilise des slugs anglais différents des slugs FR
  → 404 systématique si on remplace /fr/ par /en/. Source correcte = api.dofusdb.fr
  (à lancer depuis le PC, pas depuis le cloud).

Fonctionnalités :
  - Checkpoint/resume (fichier JSON) : reprend sans repartir de zéro
  - Délais 1.5–3.0s (identique au script original qui a tourné sans ban)
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
LIST_URL_FR = BASE_URL + "/fr/mmorpg/encyclopedie/ressources?page={}"

CHECKPOINT  = Path("checkpoint_ressources.json")
OUTPUT_JSON = "ressources_dofus_touch_full.json"
OUTPUT_XLSX = "ressources_dofus_touch_full.xlsx"

DELAY_MIN   = 1.5
DELAY_MAX   = 3.5
MAX_PAGES   = 120       # plafond de sécurité (~78 pages réelles)
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

GID_RE      = re.compile(r'/encyclopedie/[\w-]+/(\d+)-')
RATE_RE     = re.compile(r'(\d+(?:[.,]\d+)?\s*%)')

PANEL_RECIPE_KW = ("recette",)
PANEL_USEDBY_KW = ("est utilisé pour", "utilisé pour les recettes")
# Confirmé via debug : panel drops = "Peut être obtenu sur"
PANEL_DROP_KW   = ("peut être obtenu sur", "obtenu sur", "monstre", "obtenu en tuant", "droppé")


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


# ── Phase 1 : listing → GID, Nom_FR, Type, Niveau (fiable) ───────────────────
def collect_from_listing() -> list:
    items = []
    print(f"📄 Phase 1 — collecte depuis le listing ({MAX_PAGES} pages max)…")
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
            href, nom = "", ""
            # Le 1er .ak-linker a peut être l'image (texte vide) → on prend le 1er non-vide
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
                "GID":    extract_gid(url),
                "Nom_FR": nom,
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


# ── Phase 2 : fiche détail → recette, utilisé_dans, drops ─────────────────────
def scrape_detail(item: dict) -> dict:
    url = item["Lien"]
    html = get_html(url)
    if not html:
        return {**item, "Recette": "", "Utilise_dans": "", "Drops_monstres": "", "erreur": "HTTP error"}

    soup = BeautifulSoup(html, "html.parser")
    recette, utilise_dans, drops = [], [], []

    # Filet de sécurité nom : si listing n'a rien donné, on prend le h1
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
                monster_tag = (el.select_one("div.ak-title span.ak-linker")
                               or el.select_one("div.ak-title"))
                # GID du monstre depuis le href (bonus pour le futur tableau farming)
                monster_link = el.select_one("div.ak-title a, div.ak-image a")
                monster_gid  = extract_gid(monster_link["href"]) if monster_link and monster_link.get("href") else None

                # Taux : chercher % partout dans l'élément (pas seulement ak-front)
                rate_txt = ""
                for sel in ("div.ak-front", "div.ak-aside", "div.ak-rate", "span.ak-rate"):
                    rate_tag = el.select_one(sel)
                    if rate_tag:
                        rate_txt = rate_tag.get_text(strip=True)
                        break
                if not rate_txt:
                    m = RATE_RE.search(el.get_text(" ", strip=True))
                    if m:
                        rate_txt = m.group(1)

                if monster_tag:
                    nom_m = monster_tag.get_text(strip=True)
                    entry = nom_m
                    if monster_gid:
                        entry += f" [GID:{monster_gid}]"
                    if rate_txt:
                        entry += f" ({rate_txt})"
                    drops.append(entry)

    # dict.fromkeys = dédup défensive en préservant l'ordre (dofus-touch.com peut
    # servir 2 panels identiques, comme les 2 panels « Effets » des équipements)
    return {
        **item,
        "Recette":        ", ".join(dict.fromkeys(recette)),
        "Utilise_dans":   ", ".join(dict.fromkeys(utilise_dans)),
        "Drops_monstres": " | ".join(dict.fromkeys(drops)),
    }


# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    cp = load_checkpoint()

    # Phase 1 (skippée si checkpoint déjà là)
    if cp["items_base"]:
        print(f"📎 {len(cp['items_base'])} ressources en checkpoint — phase 1 skippée")
        items_base = cp["items_base"]
    else:
        items_base = collect_from_listing()
        cp["items_base"] = items_base
        save_checkpoint(cp)

    done_gids = set(cp["done_gids"])
    results   = cp["items"]

    todo = [it for it in items_base if it.get("GID") not in done_gids]
    print(f"\n🔍 Phase 2 — {len(todo)} fiches à scraper ({len(done_gids)} déjà faites)")

    for item in tqdm(todo, desc="Scraping fiches"):
        result = scrape_detail(item)
        results.append(result)
        gid = result.get("GID")
        if gid:
            done_gids.add(gid)
        cp["done_gids"] = list(done_gids)
        cp["items"]     = results
        save_checkpoint(cp)
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    # ── Sauvegarde finale ─────────────────────────────────────────────────────
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n✅ JSON : {OUTPUT_JSON}")

    df = pd.DataFrame(results)
    df.to_excel(OUTPUT_XLSX, index=False)
    print(f"✅ Excel : {OUTPUT_XLSX}  ({len(df)} ressources)")

    # Résumé
    has_drops   = (df["Drops_monstres"] != "").sum()
    has_recipe  = (df["Recette"] != "").sum()
    has_usedin  = (df["Utilise_dans"] != "").sum()
    print(f"\n📊 Résumé :")
    print(f"   {has_recipe}  ressources craftables (recette)")
    print(f"   {has_usedin}  ressources utilisées dans une recette")
    print(f"   {has_drops}  ressources avec drops monstres")
    print(f"\n💡 Nom_EN manquant → lancer scrap_ingredients_dofusdb_api_mt_final.py")
    print(f"   depuis ton PC pour enrichir via api.dofusdb.fr")
