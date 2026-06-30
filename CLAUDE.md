# CLAUDE.md — DTV (DofusTradingView)

## Branche de travail
**Toujours** : `claude/dtv-project-assessment-7t8m3u`
Push : `git push -u origin claude/dtv-project-assessment-7t8m3u`

## Architecture
```
Capture (CDP passif) → CSV data/raw/ → dtv ingest → SQLite data/dtv.db → dtv report → data/report.html
```

## Fichiers clés
| Fichier | Rôle |
|---|---|
| `dtv/collector/_report_template.py` | Template HTML+JS (~1100 lignes). **Fichier principal.** Grep par nom de fonction, Read 30-40 lignes max. |
| `dtv/collector/report.py` | `build_report_data()` → JSON embarqué `DTV`. `build_brisage_data()`, `build_craft_data()` (onglet Craft revente), `build_rune_data()`. `_price_series()` enrichit nom/type/niveau/recette/used_in depuis les catalogues. |
| `dtv/collector/catalog.py` | `build_recipes`, `build_name_to_gid`, `build_gid_meta` (nom/type/niveau/recette/used_in FR pour les fiches). |
| `dtv/collector/brisage.py` | `build_ranking`, `RUNES` dict (43 runes), `EFFET_VERS_CODE`, `normalize_name`. |
| `dtv/collector/craft.py` | `craft_plan(recipe, ing_tier_prices, n_crafts, craft_alt)`, `best_tier`, `best_unit_price`. |
| `dtv/collector/store.py` | `connect`, `ingest_all`, `tier_prices_for_gids(conn, gids, days)`. |
| `dtv/collector/item_names.py` | `load_item_names()`, `load_gid_types()`. **`load_item_levels()` manquant** → crash latent (report.py:83). |
| `dtv/data/runes.json` | 43 runes : `nom`, `poids`, `tiers:[{tier,nom,mult_base}]`, `concassable`, `giant_only`. |

## Fonctions JS clés (`_report_template.py`)
Grep le nom → Read offset+limit. Numéros indicatifs.

| Symbole | Rôle |
|---|---|
| `DTV` | JSON embarqué. `items[{gid,nom,type,level,avg,hdv,recipe?,used_in?}]`, `brisage{coeff,theo,real}`, `craft{rows,...}`, `runes{runes,concassage,live_prices}` |
| `BATCH` modes | `budget` (bénéf total maxi sous plafond invest — le bon défaut métier), `smart` (marge unitaire), `auto`, `10/100/1000`. `MAX_INVEST`/`MIN_BENEF` = filtres globaux (en-tête). `passInvestBenef()`. |
| `sellBatchCols(real,lead,detail)` | Colonnes « produire puis revendre » partagées concassage + craft. `bestSell` avec repli prix moyen. |
| `renderCraft()` / `CRAFTMAP` | Onglet Craft (revente) : 2 tables `rows_other`/`rows_equip` (`is_equip`). `allowedBatches(r)` = équip x1/x10. Icône ⚒️/📈 entre fiches et popups (`openItemDetail`, `layoutModals`, bouton `#closeboth`). |
| `CRAFTLIST` / `renderCraftList()` | Onglet « 🧺 Ma liste » : panier persisté + liste d'ingrédients agrégée. `addToCraftList(gid,qty)` depuis les popups. |
| `recipeEconomie(r)` | Affaires induites : économie nette des promos (Σ qté×(médiane−prix)). |
| batch `budget` | Maximise bénéf total sous `MAX_INVEST`. `smartBatch`/`budgetBatch` itèrent `allowedBatches(r)`. |
| `COLS` | Colonnes tableau "Prix dans le temps" (fav,nom,type,niv,last,min,max,avg,varj,vars,varm,spark,vol,hdvn,hdvlast,gid) |
| `normName(s)` | `s.toLowerCase().replace(/\s+/g," ").trim()` — toujours utiliser pour croiser les noms |
| `seriesOf(it,src)` / `statsOf(s)` | Série de prix / stats {last,min,max,avg} |
| `varOver(s,days)` | Variation % sur N jours (point le plus proche de la cible) |
| `computeRows()` / `renderRows()` | Tableau "Prix dans le temps" |
| `deriveB(r,real)` / `bCost(r)` | Métriques batch courant {rev,cost,benef,rent,cmin,batchN} |
| `renderBTable(hostId,rows,real,sort,colsFn?)` | Tableau générique craft/brisage/concassage |
| `openBModal(r,real)` | Popup détail craft/brisage/concassage (gère `r.is_concassage`) |
| `renderBrisage()` / `renderAffaires()` / `renderRunes()` | Onglets principaux |
| `concassageCols(real)` | Colonnes table concassage (Résultat, Ingrédient, Prix vente, Coût×3, Batch, Bénéf, Ratio) |
| `openPriceModal(gid)` / `closePriceModal()` | Popup graphe de prix |
| `NAMEGID` | `normName(nom) → gid` pour tous les items |
| `BATCH` / `BATCHES` | Batch courant : "smart","auto","1","10","100","1000" |

## Tâches restantes
| # | Tâche | Statut |
|---|---|---|
| 1 | `load_item_levels()` dans `item_names.py` | ✅ existe |
| 3 | "Used in" étendu (catalogue `Utilise_dans`, chips cliquables dans le graphe) | ✅ |
| 4 | Coût de craft dans le graphe (recette + total) | ✅ |
| 7 | Onglet "Craft (revente)" | ✅ |
| — | **408 items brisables sans recette** = trou de scraping (catalogues), pas un bug code |
| — | GID sans nom/type = items captés absents du catalogue ET du cache jeu |
| 10 | Bonnes affaires : revoir calcul écart vs médiane (à vérifier) |

## Invariants
- CSV = source de vérité. SQLite reconstructible via `dtv ingest`.
- Rapport HTML autonome (pas de CDN, offline).
- Secrets (`HAAPI_*`, `.env`) **jamais** commités. Compte jetable pour captures.
- Ne PAS lire `KNOWLEDGE.md`, `ARCHITECTURE.md`, `docs/TODO.md` — ce fichier suffit.
