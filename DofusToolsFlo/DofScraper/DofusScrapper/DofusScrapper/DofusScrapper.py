import requests
import openpyxl
from openpyxl.styles import Font
import time

# === CONFIG ===
SEARCH_URL = "https://touch.dofusbook.net/items/touch/search/equipment"
DETAIL_URL_TEMPLATE = "https://touch.dofusbook.net/items/touch/{item_id}"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr,fr-FR;q=0.8,en-US;q=0.5,en;q=0.3",
    "x-lang": "fr",
    "Referer": "https://touch.dofusbook.net/fr/encyclopedie/items",
}

PARAMS = {
    "context": "item",
    "level_min": 0,
    "level_max": 200,
    "craft": "true",
    "include": "12-13-19-17-18-15-16-21",  # am, an, bo, ca, ce, ch, tr
    "sort": "level-asc",
    "page": 1
}

def fetch_objects_page(page_number):
    PARAMS["page"] = page_number
    print(f"📦 Récupération de la page {page_number}...")
    response = requests.get(SEARCH_URL, headers=HEADERS, params=PARAMS)
    if response.status_code == 200:
        return response.json().get("data", [])
    else:
        print(f"❌ Erreur {response.status_code}")
        return []

def fetch_item_details(item_id):
    url = DETAIL_URL_TEMPLATE.format(item_id=item_id)
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json().get("data", {})
    else:
        print(f"⚠️ Erreur {response.status_code} pour l’objet {item_id}")
        return {}

def save_to_excel(data, filename="equipements_dofus_touch_complets.xlsx"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Équipements"

    headers = ["Nom", "Niveau", "Catégorie", "Effets", "Recette", "Lien"]
    ws.append(headers)
    for col in range(1, len(headers)+1):
        ws.cell(row=1, column=col).font = Font(bold=True)

    for row in data:
        ws.append(row)

    wb.save(filename)
    print(f"✅ Fichier sauvegardé : {filename}")

# === LANCEMENT ===
all_rows = []
page = 1

while True:
    items_page = fetch_objects_page(page)
    if not items_page:
        print("🛑 Fin de la pagination.")
        break

    for item in items_page:
        item_id = item.get("id")
        name = item.get("name", "??")
        level = item.get("level", "??")
        cat = item.get("category_name", "??")
        link = f"https://touch.dofusbook.net/fr/encyclopedie/objet/{item_id}"

        # 🔍 Détails complets
        details = fetch_item_details(item_id)

        # Effets
        effets = details.get("effects", [])
        effets_str = ", ".join(
            f"+{e.get('min', '')} à {e.get('max', '')} ({e.get('name')})"
            for e in effets if e.get("min") is not None and e.get("max") is not None
        ) or "—"

        # Recette
        ingredients = details.get("ingredients", [])
        ingredients_str = ", ".join(f"{ing['count']} x {ing['name']}" for ing in ingredients) or "—"

        all_rows.append([name, level, cat, effets_str, ingredients_str, link])

        time.sleep(0.2)  # Pause légère pour éviter de spam le serveur

    page += 1

save_to_excel(all_rows)
