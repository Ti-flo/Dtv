import pandas as pd
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
import time

# Charger les liens
df = pd.read_excel("ressources_dofus_touch_officiel.xlsx")
test_links = df["Lien"].dropna().tolist()

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:113.0) Gecko/20100101 Firefox/113.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Connection": "keep-alive",
}

def scrape_recette(url):
    try:
        time.sleep(2)  # anti-bot
        res = requests.get(url, headers=headers)
        if res.status_code != 200:
            print(f"❌ Erreur sur {url} — Code {res.status_code}")
            return "Erreur"

        soup = BeautifulSoup(res.content, "html.parser")
        craft_block = soup.select_one("div.ak-panel.ak-crafts")

        if not craft_block:
            return ""

        items = craft_block.select("div.ak-list-element")
        recette_finale = []

        for item in items:
            quantite_tag = item.select_one("div.ak-front")
            nom_tag = item.select_one("div.ak-title span.ak-linker")

            if quantite_tag and nom_tag:
                quantite = quantite_tag.text.strip()
                nom = nom_tag.text.strip()
                recette_finale.append(f"{quantite} {nom}")

        return ", ".join(recette_finale)
    except Exception as e:
        print(f"❌ Exception pour {url} — {e}")
        return "Erreur"

# Lancer le test
resultats = []
for lien in tqdm(test_links, desc="Test de scraping (10 items)"):
    recette = scrape_recette(lien)
    resultats.append({"Lien": lien, "Recette": recette})
    print(f"✅ {lien} traité.")

# Sauvegarder dans un fichier
df_result = pd.DataFrame(resultats)
df_result.to_excel("recettes_dofus_touch.xlsx", index=False)
print("✅ Fichier 'recettest_dofus_touch.xlsx' généré.")
