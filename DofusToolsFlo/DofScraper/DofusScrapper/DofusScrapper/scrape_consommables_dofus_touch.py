"""
scrape_consommables_dofus_touch.py — Consommables Dofus Touch
Source : dofus-touch.com → GIDs = IDs réels du jeu ✅

Réécrit (session 9) avec l'architecture Phase 1 / Phase 2 validée sur
scrap_ressources_full.py + DofusScrapper.py.

Corrige les bugs de l'ancienne version :
  - Niveau : capturé depuis le LISTING (td.item-level), plus depuis
    span.ak-encyclo-detail-level (sélecteur qui ne matchait jamais → 0/N)
  - Type : capturé depuis le LISTING (td.item-type), plus de préfixe "Type :"
  - GID : extrait du slug URL (manquant dans l'ancienne version)
  - Checkpoint/resume + délais humains 1.5–3.5s

Colonnes de sortie :
  GID | Nom_FR | Niveau | Type
  Effets | Conditions | Recette | Utilise_dans | Drops_monstres | Lien

Structure confirmée (debug_consommable.py sur Pain d'Amakna + Parchemin) :
  - 2 panels «Effets» + 1 «Description» listent les MÊMES effets → on déduplique
  - panel «Conditions» = restrictions (ex: « < 25 » pour un parchemin)
  - panel «Est utilisé pour les recettes» = used-in (ak-title span.ak-linker)
  - panel «Peut être obtenu sur» = drops ; taux dans div.ak-aside (ex: « <1% »)

Note Nom_EN : slugs anglais ≠ slugs français → 404 sur /en/
  Source correcte = api.dofusdb.fr (PC uniquement)
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
LIST_URL_FR = BASE_URL + "/fr/mmorpg/encyclopedie/consommables?page={}"

CHECKPOINT  = Path("checkpoint_consommables.json")
OUTPUT_JSON = "consommables_dofus_touch_full.json"
OUTPUT_XLSX = "consommables_dofus_touch_full.xlsx"

DELAY_MIN   = 1.5
DELAY_MAX   = 3.5
MAX_PAGES   = 120       # plafond de sécurité (~53 pages réelles)
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

GID_RE  = re.compile(r'/encyclopedie/[\w-]+/(\d+)-')
RATE_RE = re.compile(r'(\d+(?:[.,]\d+)?\s*%)')

PANEL_EFFECTS_KW = ("effets", "caractéristique", "statistique")
PANEL_COND_KW    = ("condition",)
PANEL_RECIPE_KW  = ("recette",)
PANEL_USEDBY_KW  = ("est utilisé pour", "utilisé pour les recettes")
# Confirmé sur ressources : panel drops = "Peut être obtenu sur"
PANEL_DROP_KW    = ("peut être obtenu sur", "obtenu sur", "monstre", "obtenu en tuant", "droppé")


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
            # Le 1er .ak-linker a peut être l'image (texte vide) → 1er non-vide
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
    print(f"✅ {len(items)} consommables trouvés")
    return items


# ── Phase 2 : fiche détail → effets, recette, utilisé_dans, drops ─────────────
def scrape_detail(item: dict) -> dict:
    url = item["Lien"]
    html = get_html(url)
    if not html:
        return {**item, "Effets": "", "Recette": "", "Utilise_dans": "",
                "Drops_monstres": "", "erreur": "HTTP error"}

    soup = BeautifulSoup(html, "html.parser")
    effets, conditions, recette, utilise_dans, drops = [], [], [], [], []

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

        elif any(kw in title for kw in PANEL_COND_KW):
            for el in elems:
                label = el.select_one("div.ak-title")
                txt = label.get_text(strip=True) if label else el.get_text(" ", strip=True)
                if txt:
                    conditions.append(txt)

        elif any(kw in title for kw in PANEL_RECIPE_KW) and "utilisé" not in title:
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
                monster_link = el.select_one("div.ak-title a, div.ak-image a")
                monster_gid  = (extract_gid(monster_link["href"])
                                if monster_link and monster_link.get("href") else None)

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
                    entry = monster_tag.get_text(strip=True)
                    if monster_gid:
                        entry += f" [GID:{monster_gid}]"
                    if rate_txt:
                        entry += f" ({rate_txt})"
                    drops.append(entry)

    # Le panel «Effets» du site inclut parfois la condition comme élément
    # (ex: « < 25 ») → on la retire des effets puisqu'elle est déjà en Conditions.
    cond_set = set(conditions)
    effets_clean = [e for e in dict.fromkeys(effets) if e not in cond_set]

    return {
        **item,
        "Effets":         " | ".join(effets_clean),
        "Conditions":     " | ".join(dict.fromkeys(conditions)),
        "Recette":        ", ".join(recette),
        "Utilise_dans":   ", ".join(utilise_dans),
        "Drops_monstres": " | ".join(drops),
    }


# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    cp = load_checkpoint()

    if cp["items_base"]:
        print(f"📎 {len(cp['items_base'])} consommables en checkpoint — phase 1 skippée")
        items_base = cp["items_base"]
    else:
        items_base = collect_from_listing()
        cp["items_base"] = items_base
        save_checkpoint(cp)

    done_gids = set(cp["done_gids"])
    results   = cp["items"]

    todo = [it for it in items_base if it.get("GID") not in done_gids]
    print(f"\n🔍 Phase 2 — {len(todo)} fiches à scraper ({len(done_gids)} déjà faites)")

    for item in tqdm(todo, desc="Scraping consommables"):
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
    print(f"✅ Excel : {OUTPUT_XLSX}  ({len(df)} consommables)")

    has_effects = (df["Effets"] != "").sum()
    has_cond    = (df["Conditions"] != "").sum()
    has_recipe  = (df["Recette"] != "").sum()
    has_usedin  = (df["Utilise_dans"] != "").sum()
    has_drops   = (df["Drops_monstres"] != "").sum()
    print(f"\n📊 Résumé :")
    print(f"   {has_effects}  consommables avec effets")
    print(f"   {has_cond}  consommables avec conditions")
    print(f"   {has_recipe}  consommables craftables (recette)")
    print(f"   {has_usedin}  consommables utilisés dans une recette")
    print(f"   {has_drops}  consommables avec drops monstres")
    print(f"\n💡 Nom_EN manquant → api.dofusdb.fr depuis ton PC")
