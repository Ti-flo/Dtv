
import pandas as pd
import requests
import concurrent.futures
from tqdm import tqdm
import threading
import sys

# Charger les ingrédients
df = pd.read_excel("ingredients_dofus_touch.xlsx")
ingredient_names = df["Ingrédient"].dropna().str.lower().str.strip().tolist()

# URL de l'API
API_URL = "https://api.dofusdb.fr/items/"

# Résultats et compteur
results = []
found_counter = 0
lock = threading.Lock()

# Fonction de récupération par ID
def fetch_item_data(item_id):
    global found_counter
    try:
        response = requests.get(f"{API_URL}{item_id}", timeout=5)
        if response.status_code != 200:
            return None
        data = response.json()
        name = data.get("name", {}).get("fr", "").strip()
        level = data.get("level", "?")
        type_name = data.get("type", {}).get("name", "?")
        if name.lower().strip() in ingredient_names:
            with lock:
                found_counter += 1
                sys.stdout.write(f"\r🔎 Objets trouvés : {found_counter}")
                sys.stdout.flush()
            return {
                "Ingrédient": name,
                "Niveau": level,
                "Catégorie": type_name,
                "ID": item_id,
                "Lien": f"https://dofusdb.fr/fr/database/object/{item_id}"
            }
    except Exception:
        return None
    return None

# IDs à tester
ids_to_check = list(range(1, 30001))

# Progression avec tqdm
with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
    futures = [executor.submit(fetch_item_data, item_id) for item_id in ids_to_check]
    for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="🔍 Scraping DofusDB"):
        result = future.result()
        if result:
            results.append(result)

# Export
df_result = pd.DataFrame(results)
df_result.to_excel("ingredients_dofusdb_scrap_api_mt.xlsx", index=False)
print("\n✅ Fichier créé : ingredients_dofusdb_scrap_api_mt.xlsx")
input("Appuyez sur Entrée pour quitter...")
