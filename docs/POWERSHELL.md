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

## ⭐ Commande unique `dtv` (DofusTradingView)

> Une seule surface pour tout. Tous les chemins (adb, catalogues, base) sont
> résolus automatiquement. Architecture : `docs/ARCHITECTURE.md`.

```powershell
cd "C:\Users\GAMING3\Desktop\dtv"

python -m dtv.scripts.dtv doctor                 # état config (adb/catalogues) + base
python -m dtv.scripts.dtv capture --account jetable   # capture passive AUTO (adb+socket)
python -m dtv.scripts.dtv ingest                 # historise les CSV dans la base SQLite
python -m dtv.scripts.dtv prices "Frêne"         # dernier prix moyen des items « Frêne »
python -m dtv.scripts.dtv history "Frêne"        # tendance du prix dans le temps
python -m dtv.scripts.dtv movers --top 30        # plus fortes variations (2 derniers snapshots)
python -m dtv.scripts.dtv brisage --craft --top 50    # classement brisage (avg-prices auto)
python -m dtv.scripts.dtv craft "Bâton de Boisaille"  # détail coût de craft d'un item
python -m dtv.scripts.dtv craftplan "Bâton de Boisaille"  # plan d'achat optimisé (tiers + n_crafts)
```

### Plan de craft optimisé (`craftplan`)

> Calcule le **coût de craft réel** en choisissant le bon tier d'achat
> (x1/x10/x100/x1000) pour chaque ingrédient, selon le nombre de crafts qu'on
> fera. Prix réels HDV des 7 derniers jours (repli sur le prix moyen serveur).
> Nécessite `dtv ingest` au préalable (lit la base SQLite).

```powershell
python -m dtv.scripts.dtv craftplan "Épée de Boued"            # n_crafts estimé d'après le coût
python -m dtv.scripts.dtv craftplan "Marteau" --n-crafts 50    # forcer 50 crafts
python -m dtv.scripts.dtv craftplan "Dague" --days 14          # élargir la fenêtre de prix réels
```

Échelle nombre de crafts (selon le coût unitaire) : `≤2k → 1000` · `≤10k → 200`
· `≤100k → 20` · `≤300k → 10` · `>300k → 1` (item à vendre, pas à briser en masse).

> `dtv brisage` / `dtv craft` piochent tout seuls le dernier `avgprices_*.csv`,
> le catalogue équipements et `rune_gids.json`. Ajoute des flags pour surcharger
> (ex `--coeff 250 --sort benefice`).

---

## Capture passive — UNE commande (auto)

> **Résultat :** `avgprices_<timestamp>.csv` (~4906 items) + `hdv_passive_<date>.csv`
> + `brisage_observations.csv` (si tu brises), tous dans `data\raw\`.

Depuis la v config, **plus besoin de trouver le PID du socket ni de forwarder à la
main** : le script localise `adb.exe` (SDK Android), détecte l'émulateur, découvre
le socket WebView et forwarde tout seul.

### Procédure

1. Lance l'émulateur + Dofus Touch (**reste sur l'écran de login**).
2. Une seule commande :

```powershell
cd "C:\Users\GAMING3\Desktop\dtv"
python -m dtv.scripts.capture_phone --account jetable
```

3. Quand tu vois `CDP attached — streaming frames`, **connecte-toi en jeu**.
   Le snapshot de prix part automatiquement au login. **Ctrl+C** pour arrêter.

> Si `adb` est introuvable, définir le chemin une fois :
> `setx DTV_ADB "C:\Users\GAMING3\AppData\Local\Android\Sdk\platform-tools\adb.exe"`
> (rouvrir PowerShell ensuite). Diagnostic complet : `python -m dtv.scripts.dtv doctor`.

### Briser des items (auto-collecte coeff + runes)

Brise normalement au Concasseur pendant la capture : chaque brisage écrit une ligne
dans `data\raw\brisage_observations.csv` (coeff réel + runes obtenues). Aucun flag
spécial requis. Pour un dump brut de debug (rétro-ingénierie), ajouter `--dump-raw`.

### Repli manuel (si l'auto échoue)

```powershell
# socket (le PID change à chaque lancement de l'émulateur)
cd "C:\Users\GAMING3\AppData\Local\Android\Sdk\platform-tools"
.\adb.exe shell cat /proc/net/unix | findstr devtools
.\adb.exe forward tcp:9222 localabstract:webview_devtools_remote_<pid>
cd "C:\Users\GAMING3\Desktop\dtv"
python -m dtv.scripts.capture_phone --no-adb --port 9222 --account jetable
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
