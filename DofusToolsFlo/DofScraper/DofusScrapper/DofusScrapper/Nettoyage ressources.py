import pandas as pd

# Charger le fichier original
df = pd.read_excel("ressources_dofus_touch_officiel.xlsx")

# Nettoyage du niveau
df["Niveau"] = df["Niveau"].astype(str).str.extract(r"(\d+)").astype(int)

# Nettoyage du nom (juste pour enlever espaces ou caractères spéciaux)
df["Nom"] = df["Nom"].astype(str).str.strip()

# Création du lien complet vers la page officielle de la ressource
base_url = "https://www.dofus-touch.com"
df["Lien"] = df["Lien"].apply(lambda x: base_url + x if isinstance(x, str) and x.startswith("/") else x)

# Sauvegarde du nouveau fichier
df.to_excel("ressources_dofus_touch_officiel_cleaned.xlsx", index=False)

print("✅ Fichier nettoyé et prêt : ressources_dofus_touch_officiel_cleaned.xlsx")