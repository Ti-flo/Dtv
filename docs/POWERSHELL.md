# DTV — Référence commandes PowerShell

> Chemins absolus confirmés sur le PC de Flo. Ces chemins ne changent pas.
> Copier-coller direct depuis ce fichier.

---

## Chemins de base

```
Repo DTV         : C:\Users\GAMING3\Desktop\dtv
ADB platform-tools: C:\Users\GAMING3\AppData\Local\Android\Sdk\platform-tools
Scrapers          : C:\Users\GAMING3\Desktop\dtv\DofusToolsFlo\DofScraper\DofusScrapper\DofusScrapper
```

---

## Git

```powershell
cd "C:\Users\GAMING3\Desktop\dtv"
git pull origin claude/dtv-project-assessment-7t8m3u
```

---

## ADB / Émulateur

```powershell
# Voir les devices connectés
cd "C:\Users\GAMING3\AppData\Local\Android\Sdk\platform-tools"
.\adb.exe devices

# Vérifier que la WebView du jeu est visible (lancer après avoir ouvert Dofus Touch)
.\adb.exe shell cat /proc/net/unix | findstr devtools

# Forward manuel (si WebView = chrome_devtools_remote)
.\adb.exe forward tcp:9222 localabstract:chrome_devtools_remote

# Forward manuel (si WebView = webview_devtools_remote_<pid>)
.\adb.exe forward tcp:9222 localabstract:webview_devtools_remote_<pid>

# Vérifier que le forward marche (doit retourner un JSON avec les targets)
curl http://localhost:9222/json
```

---

## Capture passive (capture_phone)

> **Ordre impératif** : ouvrir Dofus Touch → écran launcher/login → lancer la capture → PUIS se connecter.

```powershell
cd "C:\Users\GAMING3\Desktop\dtv"

# Capture avec forward ADB automatique (cas normal émulateur USB/local)
python -m dtv.scripts.capture_phone --account jetable

# Si ADB déjà forwardé manuellement (ou si l'auto-détection rate)
python -m dtv.scripts.capture_phone --no-adb --port 9222 --account jetable

# Avec filtre si plusieurs WebViews debuggables
python -m dtv.scripts.capture_phone --target-filter dofus --account jetable

# Résultat attendu au login :
#   "✓ average-price snapshot saved: ~4906 items → avgprices_<timestamp>.csv"
# Résultat à chaque item HDV ouvert :
#   "✓ recorded item GID=<N> (X offers) — prix_x1=<kamas>"
```

---

## Diagnostics prix moyens

```powershell
cd "C:\Users\GAMING3\Desktop\dtv"

# Lister les fichiers de prix
ls data\raw\avgprices_*.csv

# Diagnostic : combien de prix > 1 kama ?
python -c "import csv; rows=list(csv.DictReader(open('data/raw/avgprices_XXXXXX.csv'))); v=[int(r['avg_price_x1']) for r in rows]; print('total', len(v), '| >1:', sum(x>1 for x in v), '| max', max(v), '| GID468=', next((r['avg_price_x1'] for r in rows if r['item_gid']=='468'), 'absent'))"

# Voir les prix dans le dashboard
python -m dtv.scripts.analyze --avg
```

---

## Collecte et analyse

```powershell
cd "C:\Users\GAMING3\Desktop\dtv"

# Dashboard HDV
python -m dtv.scripts.analyze

# Seulement les prix moyens
python -m dtv.scripts.analyze --avg

# Dump item names/types depuis le jeu via CDP
python -m dtv.scripts.dump_item_names

# Voir les fichiers collectés
ls data\raw\
ls data\raw\hdv_passive_*.csv
ls data\raw\avgprices_*.csv
```

---

## Scrapers

```powershell
cd "C:\Users\GAMING3\Desktop\dtv\DofusToolsFlo\DofScraper\DofusScrapper\DofusScrapper"

# Ressources complètes (~78 pages listing + ~1861 fiches détail)
python scrap_ressources_full.py

# Test rapide ressources (2 pages listing seulement)
python scrap_ressources_test.py

# Équipements + armes (~200 pages listing + ~2825 fiches détail)
python DofusScrapper.py

# Consommables (~53 pages listing)
python scrape_consommables_dofus_touch.py

# Backfill des items en erreur (réseau transitoire)
python retry_failed.py

# Enrichir les vieux Excel avec la colonne GID
python extract_gids.py
```

---

## Nettoyage des sorties scrapers (effets dupliqués)

dofus-touch.com sert 2 panels « Effets » identiques → valeurs dupliquées.
Nettoyage en place, **sans re-scraper** (instantané, idempotent).

```powershell
cd "C:\Users\GAMING3\Desktop\dtv\DofusToolsFlo\DofScraper\DofusScrapper\DofusScrapper"

# Nettoie les 3 catalogues d'un coup (équipements + conso + ressources)
python clean_scraper_outputs.py

# Ou juste les équipements (ancien script spécifique, équivalent pour ce fichier)
python clean_effets_equipements.py

# Inspecter la structure HTML d'une fiche (debug sélecteurs)
python debug_consommable.py "URL_consommable"
```

---

## Brisage — rentabilité (porté de RuneMaster)

> Référence complète : `docs/BRISAGE.md`. Le moteur calcule la valeur des runes
> obtenues en brisant chaque item × prix HDV → classement des items rentables.

```powershell
cd "C:\Users\GAMING3\Desktop\dtv"

# Test du moteur (formule + parsing + rentabilité)
python -m dtv.scripts.test_brisage

# Classement par revenu de brisage (prix exemple — tourne tout de suite)
python -m dtv.scripts.brisage --catalog "DofusToolsFlo\DofScraper\DofusScrapper\DofusScrapper\equipements_dofus_touch_full.xlsx" --top 50

# 1) construire le mapping code rune → GID (depuis le catalogue ressources)
python -m dtv.scripts.build_rune_gids --catalog "DofusToolsFlo\DofScraper\DofusScrapper\DofusScrapper\ressources_dofus_touch_full.xlsx"

# 2) classement avec prix HDV live (coût items + prix runes via GID) + export
python -m dtv.scripts.brisage --catalog "DofusToolsFlo\DofScraper\DofusScrapper\DofusScrapper\equipements_dofus_touch_full.xlsx" --avg-prices data\raw\avgprices_AAAAMMJJ.csv --rune-gids dtv\data\rune_gids.json --top 100 --out top_brisage.xlsx
```

---

## Fichiers de sortie des scrapers

```
C:\Users\GAMING3\Desktop\dtv\DofusToolsFlo\DofScraper\DofusScrapper\DofusScrapper\
  ressources_dofus_touch_full.json     ← 1861 ressources
  ressources_dofus_touch_full.xlsx
  equipements_dofus_touch_full.json    ← 2825 équipements + armes
  equipements_dofus_touch_full.xlsx
  consommables_dofus_touch_full.json   ← à venir
  consommables_dofus_touch_full.xlsx
  checkpoint_ressources.json           ← reprise auto si coupure
  checkpoint_equipements.json
  checkpoint_consommables.json
```
