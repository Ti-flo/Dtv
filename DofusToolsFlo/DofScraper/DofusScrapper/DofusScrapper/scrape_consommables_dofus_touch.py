
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
from tqdm import tqdm

base_url = "https://www.dofus-touch.com"
consumables_url = base_url + "/fr/mmorpg/encyclopedie/consommables?page={}"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

def get_soup(url):
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return BeautifulSoup(response.text, "html.parser")
        else:
            print(f"❌ Erreur {response.status_code} pour {url}")
    except Exception as e:
        print(f"❌ Exception pour {url} : {e}")
    return None

def extract_links_from_page(page_num):
    url = consumables_url.format(page_num)
    soup = get_soup(url)
    if not soup:
        return []

    rows = soup.select("table.ak-responsivetable tbody tr")
    links = []
    for row in rows:
        link_tag = row.select_one("td span.ak-linker a")
        if link_tag:
            href = link_tag.get("href")
            if href:
                links.append(base_url + href)
    return links

def extract_data_from_link(link):
    soup = get_soup(link)
    if not soup:
        return None

    try:
        name_tag = soup.select_one("div.ak-title-container.ak-backlink h1.ak-return-link")
        item_name = name_tag.text.strip() if name_tag else ""

        item_level = soup.select_one("div.ak-panel-content span.ak-encyclo-detail-level")
        item_level = item_level.text.replace("Niv. ", "").strip() if item_level else ""

        item_type = soup.select_one("div.ak-encyclo-detail-type")
        item_type = item_type.text.strip() if item_type else ""

        recipe_block = soup.select("div.ak-container.ak-panel.ak-crafts div.ak-list-element")
        recipe_list = []

        for element in recipe_block:
            quantity_tag = element.select_one("div.ak-front")
            name_tag = element.select_one("div.ak-title span.ak-linker")
            if quantity_tag and name_tag:
                quantity = quantity_tag.text.strip()
                ingredient = name_tag.text.strip()
                recipe_list.append(f"{quantity} {ingredient}")

        recipe_string = ", ".join(recipe_list) if recipe_list else ""

        return {
            "Nom": item_name,
            "Niveau": item_level,
            "Type": item_type,
            "Recette": recipe_string,
            "Lien": link
        }

    except Exception as e:
        print(f"❌ Erreur d'extraction sur {link} : {e}")
        return None

# Main scraping
all_links = []
for page in tqdm(range(1, 54), desc="🔗 Récupération des liens"):
    page_links = extract_links_from_page(page)
    all_links.extend(page_links)
    time.sleep(random.uniform(2, 4))

print(f"📦 {len(all_links)} consommables à scraper.")

# Extraction de données
data = []
for link in tqdm(all_links, desc="🔍 Scraping des consommables"):
    info = extract_data_from_link(link)
    if info:
        data.append(info)
    time.sleep(random.uniform(2, 4))

# Sauvegarde
df = pd.DataFrame(data)
df.to_excel("consommables_dofus_touch.xlsx", index=False)
print("✅ Fichier sauvegardé : consommables_dofus_touch.xlsx")
