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

## Capture passive — guide complet (émulateur)

> **Résultat obtenu :** `avgprices_<timestamp>.csv` (~4906 items) dans `data\raw\`
> + `hdv_passive_<date>.csv` (chaque item HDV ouvert).

### Étape 0 — Prérequis une seule fois

`adb.exe` n'est PAS dans le PATH → toutes les commandes adb se font depuis
`C:\Users\GAMING3\AppData\Local\Android\Sdk\platform-tools`.

### Étape 1 — Ouvrir l'émulateur + Dofus Touch

Lance l'émulateur Android Studio, ouvre Dofus Touch.
**Reste sur l'écran de login — ne te connecte pas encore.**

### Étape 2 — Trouver le nom du socket WebView

```powershell
cd "C:\Users\GAMING3\AppData\Local\Android\Sdk\platform-tools"
.\adb.exe shell cat /proc/net/unix | findstr devtools
```

Résultat typique (le PID change à chaque lancement) :
```
... @webview_devtools_remote_7403
```
Note le nom complet après le `@` : `webview_devtools_remote_7403`

### Étape 3 — Forwarder le socket

```powershell
# Remplace 7403 par le PID trouvé à l'étape 2
.\adb.exe forward tcp:9222 localabstract:webview_devtools_remote_7403
# doit retourner : 9222
```

### Étape 4 — Lancer la capture

```powershell
cd "C:\Users\GAMING3\Desktop\dtv"
python -m dtv.scripts.capture_phone --no-adb --port 9222 --account jetable
```

Attendre :
```
INFO cdp_client — Attaching to WebView: title='Dofus Touch' ...
INFO cdp_client — CDP attached — Network domain enabled, streaming frames
```

### Étape 5 — Se connecter en jeu

Connecte-toi sur le compte jetable dans Dofus Touch.
Au login le snapshot part automatiquement :
```
INFO — average-price snapshot saved: ~4906 items → avgprices_<timestamp>.csv
```

**Ctrl+C** pour arrêter la capture quand tu as fini.

---

### Résumé en 3 blocs copier-coller

```powershell
# BLOC 1 — socket (à faire à chaque lancement, le PID change)
cd "C:\Users\GAMING3\AppData\Local\Android\Sdk\platform-tools"
.\adb.exe shell cat /proc/net/unix | findstr devtools
```

```powershell
# BLOC 2 — forward (remplacer 7403 par le PID du bloc 1)
.\adb.exe forward tcp:9222 localabstract:webview_devtools_remote_7403
```

```powershell
# BLOC 3 — capture (depuis dtv, AVANT de se connecter en jeu)
cd "C:\Users\GAMING3\Desktop\dtv"
python -m dtv.scripts.capture_phone --no-adb --port 9222 --account jetable
```

### Capturer le protocole de BRISAGE (dump brut)

Pour rétro-ingénier le Concasseur (coefficient + runes obtenues), ajouter
`--dump-raw` : ça enregistre TOUTES les frames de jeu dans
`data\raw\ws_raw_<jour>.jsonl` et affiche chaque nouveau type de message vu.
Lancer la capture, **briser quelques items**, puis Ctrl+C. Le message clé est
`ExchangeCraftInformationObjectMessage` (et le résultat avec les runes).

```powershell
python -m dtv.scripts.capture_phone --no-adb --port 9222 --account jetable --dump-raw
# → puis va au Concasseur, brise 2-3 items, Ctrl+C
# → m'envoyer data\raw\ws_raw_<jour>.jsonl (ou les lignes "Exchange...")
```

---

## Diagnostics prix moyens

```powershell
cd "C:\Users\GAMING3\Desktop\dtv"

# Lister les fichiers de prix capturés
ls data\raw\avgprices_*.csv

# Enrichir un snapshot avec les noms d'items -> XLSX lisible (Nom + Type + Prix)
python -m dtv.scripts.enrich_avgprices --avgprices data\raw\avgprices_XXXXXX.csv
# Produit : data\raw\avgprices_XXXXXX_named.xlsx  (trié par prix décroissant)

# Avec chemin de sortie explicite
python -m dtv.scripts.enrich_avgprices --avgprices data\raw\avgprices_XXXXXX.csv --out data\raw\prix_nommes.xlsx
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

# 2-bis) COÛT DE CRAFT (recommandé) : coût = Σ ingrédients × prix moyen, pas le
#        prix HDV de l'item fini. C'est le vrai coût pour « fabriquer puis briser ».
python -m dtv.scripts.brisage --catalog "DofusToolsFlo\DofScraper\DofusScrapper\DofusScrapper\equipements_dofus_touch_full.xlsx" --avg-prices data\raw\avgprices_AAAAMMJJ.csv --rune-gids dtv\data\rune_gids.json --craft --top 100 --out top_brisage_craft.xlsx

# 2-ter) DIAGNOSTIC coût de craft d'un item (détail ingrédient par ingrédient)
python -m dtv.scripts.brisage --catalog "DofusToolsFlo\DofScraper\DofusScrapper\DofusScrapper\equipements_dofus_touch_full.xlsx" --avg-prices data\raw\avgprices_AAAAMMJJ.csv --explain "Bâton de Boisaille"

# 3) avec coeff supposé (ex 250%) trié par bénéfice
python -m dtv.scripts.brisage --catalog "...\equipements_dofus_touch_full.xlsx" --avg-prices data\raw\avgprices_AAAAMMJJ.csv --rune-gids dtv\data\rune_gids.json --coeff 250 --sort benefice

# 4) avec les coeffs réels observés en jeu (colonnes Coeff Réel + Dernier Brisage)
#    copier dtv\data\brisage_observations_template.csv -> brisage_observations.csv et remplir
python -m dtv.scripts.brisage --catalog "...\equipements_dofus_touch_full.xlsx" --avg-prices data\raw\avgprices_AAAAMMJJ.csv --rune-gids dtv\data\rune_gids.json --observations brisage_observations.csv
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
