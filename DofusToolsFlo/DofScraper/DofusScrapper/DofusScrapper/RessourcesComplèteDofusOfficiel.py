import pandas as pd
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

# Charger le fichier nettoyé
df = pd.read_excel("ressources_dofus_touch_officiel_cleaned.xlsx")

# Limiter à 10 objets pour test
df = df.head(10).copy()

# Colonnes à remplir
df["Recette"] = ""
df["Utilisé dans"] = ""

# Fonction de parsing
def get_recette_et_utilisation(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"❌ Erreur sur {url} — Code {response.status_code}")
            return "", ""

        soup = BeautifulSoup(response.text, "html.parser")
        sections = soup.select("div.ak-container.ak-panel")
        recette, utilise_dans = [], []

        for section in sections:
            title = section.select_one("div.ak-panel-title")
            if not title:
                continue
            title_text = title.text.strip().lower()

            # Si c'est une recette craftée
            if "recette" in title_text:
                elements = section.select("div.ak-list-element")
                for el in elements:
                    qty = el.select_one("div.ak-front")
                    name = el.select_one("div.ak-title span.ak-linker")
                    if qty and name:
                        recette.append(f"{qty.text.strip()} {name.text.strip()}")

            # Si c'est une ressource utilisée dans une recette
            elif "est utilisé pour les recettes" in title_text:
                elements = section.select("div.ak-list-element")
                for el in elements:
                    name = el.select_one("div.ak-title span.ak-linker")
                    if name:
                        utilise_dans.append(name.text.strip())

        return ", ".join(recette), ", ".join(utilise_dans)

    except Exception as e:
        print(f"❌ Erreur d’analyse pour {url} — {e}")
        return "", ""

# Traitement avec barre de progression
for i in tqdm(range(len(df))):
    url = df.loc[i, "Lien"]
    recette, utilise_dans = get_recette_et_utilisation(url)
    df.at[i, "Recette"] = recette
    df.at[i, "Utilisé dans"] = utilise_dans

# Sauvegarde
df.to_excel("ressources_dofus_touch_test_10.xlsx", index=False)
print("✅ Fichier sauvegardé : ressources_dofus_touch_test_10.xlsx")
