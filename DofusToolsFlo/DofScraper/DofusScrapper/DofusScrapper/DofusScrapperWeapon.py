import requests
import openpyxl
from openpyxl.styles import Font
import time

SEARCH_URL = "https://touch.dofusbook.net/items/touch/search/weapon"
DETAIL_URL_TEMPLATE = "https://touch.dofusbook.net/items/touch/{}"
LINK_TEMPLATE = "https://touch.dofusbook.net/fr/encyclopedie/objet/{}"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr,fr-FR;q=0.8,en-US;q=0.5,en;q=0.3",
    "x-lang": "fr"
}

PARAMS = {
    "level_min": 0,
    "level_max": 200,
    "craft": "true",
    "sort": "level-asc",
    "page": 1
}

def fetch_page(page):
    PARAMS["page"] = page
    print(f"📦 Récupération de la page {page} (armes)...")
    response = requests.get(SEARCH_URL, headers=HEADERS, params=PARAMS)
    if response.status_code == 200:
        data = response.json().get("data", [])
        print(f"🔍 Armes trouvées sur cette page : {len(data)}")
        return data
    else:
        print(f"❌ Erreur {response.status_code}")
        return []

def fetch_details(item_id):
    url = DETAIL_URL_TEMPLATE.format(item_id)
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json().get("data", {})
    else:
        print(f"⚠️ Erreur pour l’arme {item_id}")
        return {}

def convert_effects(effects):
    if not effects:
        return "—"
    return ", ".join(
        f"+{e.get('min')} à {e.get('max')} ({e.get('name')})"
        for e in effects if e.get("min") is not None and e.get("max") is not None
    )

def convert_ingredients(ingredients):
    if not ingredients:
        return "—"
    return ", ".join(f"{i['count']} x {i['name']}" for i in ingredients)

def save_to_excel(data, filename="armes_dofus_touch.xlsx"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Armes"

    headers = ["Nom", "Niveau", "Catégorie", "Effets", "Recette", "Lien"]
    ws.append(headers)
    for col in range(1, len(headers) + 1):
        ws.cell(row=1, column=col).font = Font(bold=True)

    for item in data:
        ws.append(item)

    wb.save(filename)
    print(f"✅ Fichier sauvegardé : {filename}")
    print(f"📊 Total d’armes : {len(data)}")

# === LANCEMENT ===
all_weapons = []
page = 1

while True:
    page_data = fetch_page(page)
    if not page_data:
        print("🛑 Fin de la pagination des armes.")
        break

    for obj in page_data:
        item_id = obj.get("id")
        name = obj.get("name", "??")
        level = obj.get("level", "??")
        cat = obj.get("category_name", "??")
        link = LINK_TEMPLATE.format(item_id)

        details = fetch_details(item_id)
        effets_str = convert_effects(details.get("effects", []))
        ingredients_str = convert_ingredients(details.get("ingredients", []))

        all_weapons.append([name, level, cat, effets_str, ingredients_str, link])
        time.sleep(0.1)

    page += 1

save_to_excel(all_weapons)
