# CLAUDE.md — DTV (DofusTradingView)

## Branche de travail
**Toujours** : `claude/dtv-project-assessment-7t8m3u`
Push : `git push -u origin claude/dtv-project-assessment-7t8m3u`

## Architecture en 30 secondes
```
Capture (CDP passif) → CSV data/raw/  →  dtv ingest  →  SQLite data/dtv.db
                                                              ↓
                                                       dtv report  →  data/report.html
```
- **Capture** : `dtv/scripts/capture_phone.py` + `dtv/collector/cdp_client.py` — lit les frames WebSocket du vrai client Dofus Touch via CDP, zéro bot.
- **Store** : `dtv/collector/store.py` — SQLite, idempotent. Tables : `avg_prices`, `hdv_offers`, `brisage_obs`.
- **Analyse** : `dtv/collector/brisage.py` + `dtv/collector/craft.py` — rentabilité brisage/craft.
- **Vue** : `dtv/scripts/dtv.py` (CLI) + `dtv/collector/report.py` (HTML autonome).

## Fichiers clés
| Fichier | Rôle |
|---|---|
| `dtv/collector/_report_template.py` | Template HTML+JS du rapport (≈1000 lignes). **Fichier principal des tâches en cours.** |
| `dtv/collector/report.py` | Génère le rapport : construit `DTV` (JSON embarqué), appelle brisage, rend le template. |
| `dtv/collector/brisage.py` | Moteur brisage : `build_ranking`, `profitability`, `breakdown`, `RUNES` dict, `EFFET_VERS_CODE`. |
| `dtv/collector/craft.py` | Moteur craft : `craft_plan`, `resolve_craft_unit_costs`, `best_tier`, `estimate_n_crafts`. |
| `dtv/collector/store.py` | SQLite : `connect`, `ingest_all`, `search`, `price_history`, `movers`, `tier_prices_for_gids`. |
| `dtv/collector/catalog.py` | Charge les JSON scrapés : `build_recipes`, `build_name_to_gid`, `build_name_prices`. |
| `dtv/collector/item_names.py` | `load_item_names()`, `load_gid_types()`, `load_type_names()`. **Manque `load_item_levels()`** (appelé dans report.py:83 — crash latent). |
| `dtv/config.py` | Résout tous les chemins (adb, catalogues, DB). `catalog(kind)`, `rune_gids_path()`. |
| `dtv/data/runes.json` | 43 runes : `nom`, `poids`, `special` (vi/ii/pod), `tiers` (liste), `concassable`, `giant_only`. |
| `dtv/data/rune_gids.json` | Mapping prix HDV par tier : `code → GID` (simple), `code_pa → GID`, `code_ra → GID`. |

## Structure des données JS dans le rapport

```js
DTV = {
  items: [{
    gid: int,
    nom: str,
    type: str,          // "Épée", "Ressource", etc.
    level: int|null,
    avg:  [[ts_str, prix], ...],   // snapshots prix moyen marché
    hdv:  [[ts_str, x1, x10, x100, x1000, nb], ...],  // relevés HDV réels
  }],
  brisage: {
    available: bool,
    coeff: float,       // coeff théorique global (%)
    theo: [BrisageRow],  // tous les items du catalogue (equipements + consommables)
    real: [BrisageRow],  // items avec coeff réel observé
  }
}

BrisageRow = {
  GID, Nom, Niveau, Type,
  Cout,              // coût de craft (1 unité)
  Revenu,            // revenu runes @coeff théo
  Benefice,
  Rentabilite,       // Revenu/Cout
  Coeff_Min,         // coeff minimum pour être rentable
  Coeff_Reel,        // null si pas observé
  Benefice_reel,
  Prix_Moyen,        // prix HDV de l'item fini
  craft: {
    recipe: [{nom, qty, tiers:{x1,x10,x100,x1000}|null, craft_unit:float|null}],
    cpc: {auto, "1","10","100","1000"},  // coût/craft selon batch
    n_auto: int,
    db: bool,        // true=prix HDV tiers, false=avgprices
  },
  runes_detail: [{code, nom, qty, price}],
}
```

## Carte des fonctions `_report_template.py`
Rechercher par nom avec Grep — les numéros sont indicatifs et dérivent après chaque commit.

| Fonction/Constante | ~Ligne | Rôle |
|---|---|---|
| `DTV` | 204 | Données JSON parsées |
| `COLS` | 344 | Colonnes du tableau "Prix dans le temps" |
| `seriesOf / statsOf` | 225 | Série de prix d'un item par source |
| `varOver(series, days)` | 299 | Variation % sur N jours (closest-to-target) |
| `volumeIndex(series)` | 322 | Indice 0–10 avec 1 décimale |
| `computeRows / renderHead / renderRows` | 366 | Tableau "Prix dans le temps" |
| `showDetail(gid, root)` | 426 | Panneau détail item (graphe + stats) |
| `drawChart / drawLegend` | 462 | SVG du graphe de prix |
| `B` | 563 | Données brisage (`DTV.brisage`) |
| `bestTier / deriveB` | 573 | Calcul coût/bénéf brisage au batch courant |
| `USEDIN` | 632 | Index `normName(ing) → [BrisageRow]` (crafts utilisant un item) |
| `renderUsedIn` | 638 | Affiche "crafts utilisant cet item" dans le détail |
| `brisageCols / renderBTable` | 659 | Tableau craft & brisage |
| `renderBrisage` | 737 | Onglet "Craft & Brisage" |
| `openBModal(r, real)` | 775 | Popup détail d'un item brisage/craft |
| `dealStats / DEALS / DEALMAP` | 864 | Stats "bonnes affaires" (écart vs médiane) |
| `NAMEGID` | 884 | Lookup `normName(nom) → gid` (tous les items) |
| `renderAffaires` | 902 | Onglet "Bonnes affaires" |
| `openPriceModal(gid)` | 975 | Popup graphe de prix (appelle `showDetail`) |

## Tâches en cours (rapport HTML)

| # | Tâche | Statut |
|---|---|---|
| 1 | `load_item_levels()` manquant dans `item_names.py` | ❌ crash latent |
| 2 | Clic ingrédient (popup craft) → graphe popup | ✅ fait (commit e0ce460) |
| 3 | "Used in" : étendre aux ressources/consommables | ❌ todo |
| 4 | Coût de craft dans "Prix dans le temps" | ❌ todo |
| 5 | Nouvel onglet Runes (concassage = craft) | ✅ fait |
| 6 | Coût/bénéf batch dans les vues listes | ❌ todo |
| 7 | Nouvel onglet Craft sans brisage (craft + revente) | ❌ todo |
| 8 | Volume décimales + varOver fix | ✅ fait (commit e0ce460) |
| 9 | Tooltips colonnes Prix dans le temps | ✅ fait (commit e0ce460) |
| 10 | Bonnes affaires : vérifier bug calcul écart | ❌ à investiguer |

## Conventions et invariants
- `normName(s)` = `s.toLowerCase().replace(/\s+/g," ").trim()` — **toujours** utiliser pour croiser noms d'items.
- CSV = source de vérité. SQLite est reconstructible via `dtv ingest`.
- Catalogues scrapés : `equipements_dofus_touch_full.json`, `consommables_dofus_touch_full.json`, `ressources_dofus_touch_full.json` dans `DofusToolsFlo/DofScraper/…`.
- Le rapport HTML est **autonome** (tout embarqué, pas de CDN). Ouvrable offline.
- Secrets (`HAAPI_*`, `.env`) **jamais** commités.
- Compte jetable uniquement pour les captures, jamais le vrai compte.

## Stratégie de lecture efficace
- `_report_template.py` : utiliser `Grep` sur le nom de fonction, puis `Read` avec `offset`+`limit` de 30–40 lignes max.
- Ne PAS lire `KNOWLEDGE.md`, `ARCHITECTURE.md`, `docs/TODO.md` sauf besoin spécifique — le présent fichier suffit.
