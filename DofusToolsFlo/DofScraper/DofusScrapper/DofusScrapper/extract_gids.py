"""
extract_gids.py
Lit les fichiers Excel existants, extrait les GIDs depuis les slugs d'URL dofus-touch.com.

Source valide  : dofus-touch.com → GID = numéro dans l'URL (/encyclopedie/ressources/312-fer → GID 312)
Source invalide: dofusbook.net   → IDs internes ≠ GIDs en jeu (ex: Bottes de Bowisse = 25 ici, 127 en jeu)
"""
import re
import sys
from pathlib import Path
import pandas as pd

GID_RE = re.compile(r'/encyclopedie/[\w-]+/(\d+)-')

# (fichier, source_fiable, colonne_lien)
FILES_TO_PROCESS = [
    # dofus-touch.com → GIDs corrects
    ("ressources_dofus_touch_noms_final.xlsx",      True,  "Lien"),
    ("consommables_dofus_touch.xlsx",               True,  "Lien"),
    # dofusbook.net → IDs internes, PAS des GIDs en jeu
    ("equipements_dofus_touch_complets.xlsx",       False, "Lien"),
    ("armes_dofus_touch.xlsx",                      False, "Lien"),
    # Inconnus
    ("ingredients_dofus_touch.xlsx",                None,  "Lien"),
]


def extract_gid(url) -> int | None:
    if not isinstance(url, str):
        return None
    m = GID_RE.search(url)
    return int(m.group(1)) if m else None


def process(fname: str, trusted: bool | None, link_col: str):
    path = Path(fname)
    if not path.exists():
        print(f"⏭️  {fname} — fichier absent, ignoré")
        return

    if trusted is False:
        print(f"⚠️  {fname} — SOURCE DOFUSBOOK.NET : IDs internes ≠ GIDs. Fichier ignoré.")
        print(f"          Remplacer par les scripts utilisant dofus-touch.com.")
        return

    df = pd.read_excel(path)

    if link_col not in df.columns:
        print(f"⚠️  {fname} — colonne '{link_col}' introuvable. Colonnes : {list(df.columns)}")
        return

    if trusted is None:
        sample_url = df[link_col].dropna().iloc[0] if not df[link_col].dropna().empty else ""
        if "dofusbook" in str(sample_url):
            print(f"⚠️  {fname} — détecté dofusbook.net : IDs non fiables. Ignoré.")
            return
        elif "dofus-touch.com" in str(sample_url):
            print(f"ℹ️  {fname} — source dofus-touch.com détectée automatiquement.")
        else:
            print(f"⚠️  {fname} — source inconnue ({sample_url[:60]}…). GIDs peut-être incorrects.")

    df["GID"] = df[link_col].apply(extract_gid)
    cols = ["GID"] + [c for c in df.columns if c != "GID"]
    df = df[cols]

    missing = df["GID"].isna().sum()
    out_path = path.stem + "_avec_gid.xlsx"
    df.to_excel(out_path, index=False)
    print(f"✅ {fname} → {out_path}  ({len(df)} items, {missing} GIDs manquants)")
    if missing:
        bad = df[df["GID"].isna()][link_col].head(5).tolist()
        print(f"   Exemples sans GID : {bad}")


if __name__ == "__main__":
    for fname, trusted, link_col in FILES_TO_PROCESS:
        process(fname, trusted, link_col)
