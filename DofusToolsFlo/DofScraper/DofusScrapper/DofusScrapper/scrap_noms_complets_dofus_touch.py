import requests
from bs4 import BeautifulSoup
import pandas as pd
from time import sleep
import random
from tqdm import tqdm

# Charger le fichier avec les liens
df = pd.read_excel("recettes_dofus_touch_noms_affines_nettoyes.xlsx")

# Headers réalistes pour contourner les protections
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.8,en-US;q=0.5,en;q=0.3",
    "Referer": "https://www.dofus-touch.com/fr/mmorpg/encyclopedie/ressources",
    "Connection": "keep-alive",
}

noms_trouves = []

# Scraping
for index, row in tqdm(df.iterrows(), total=len(df), desc="Scraping noms depuis les pages"):
    url = row["Lien"]
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            titre_tag = soup.select_one("h1.ak-return-link")
            if titre_tag:
                nom = titre_tag.get_text(strip=True)
                noms_trouves.append(nom)
                print(f"✅ {nom} récupéré depuis {url}")
            else:
                noms_trouves.append("")
                print(f"⚠️ Nom non trouvé sur {url}")
        else:
            noms_trouves.append("")
            print(f"❌ Erreur {response.status_code} sur {url}")

        # Pause random entre 2 et 4 sec
        sleep(random.uniform(2, 4))

    except Exception as e:
        noms_trouves.append("")
        print(f"🔥 Exception sur {url} — {e}")

# Ajouter les noms trouvés dans une nouvelle colonne
df["Nom_scrape"] = noms_trouves

# Sauvegarde
df.to_excel("recettes_dofus_touch_noms_completes_test.xlsx", index=False)
print("✅ Fichier enregistré : recettes_dofus_touch_noms_completes_test.xlsx")
