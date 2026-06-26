import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
from tqdm import tqdm

base_url = "https://www.dofus-touch.com"
page_url = base_url + "/fr/mmorpg/encyclopedie/ressources?page={}"
all_items = []

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.8,en-US;q=0.5,en;q=0.3",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "DNT": "1",
}

def fetch_page(page):
    try_count = 0
    while try_count < 3:
        url = page_url.format(page)
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            return response.text
        elif response.status_code == 403:
            try_count += 1
            wait_time = 5 + try_count * 5
            print(f"🚫 403 sur la page {page} — attente {wait_time}s avant retry ({try_count}/3)")
            time.sleep(wait_time)
        else:
            print(f"❌ Erreur {response.status_code} sur la page {page}")
            return None
    return None

for page in tqdm(range(1, 79), desc="📄 Scraping pages"):
    html = fetch_page(page)
    if not html:
        continue

    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table.ak-responsivetable tbody tr")

    for row in rows:
        name_tag = row.select_one(".ak-linker a")
        type_tag = row.select_one("td.item-type")
        level_tag = row.select_one("td.item-level")

        if not (name_tag and type_tag and level_tag):
            continue

        name = name_tag.text.strip()
        link = base_url + name_tag.get("href").strip()
        item_type = type_tag.text.strip()
        level = level_tag.text.strip().replace("Niv. ", "")

        all_items.append({
            "Nom": name,
            "Type": item_type,
            "Niveau": int(level) if level.isdigit() else level,
            "Lien": link
        })

    # 🌙 Sleep aléatoire entre 1.5 et 3.5s
    sleep_time = round(random.uniform(1.5, 3.5), 2)
    time.sleep(sleep_time)

# ✅ Sauvegarde
df = pd.DataFrame(all_items)
df.to_excel("ressources_dofus_touch_officiel.xlsx", index=False)
print("✅ Fichier sauvegardé : ressources_dofus_touch_officiel.xlsx")
