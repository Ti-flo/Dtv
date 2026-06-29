# DTV — Architecture (DofusTradingView)

> Vue d'ensemble de la structure. Objectif : **une seule commande pour tout
> faire et tout voir**, zéro chemin à saisir, données historisées pour comparer
> les prix dans le temps. C'est le « TradingView » du marché Dofus Touch.

---

## Les 4 couches

```
┌─────────────┐   ┌──────────────┐   ┌───────────────┐   ┌──────────────┐
│  CAPTURE    │ → │    STORE     │ → │    ANALYSE    │ → │     VUE      │
│ (collecte)  │   │ (historique) │   │  (décision)   │   │  (CLI dtv)   │
└─────────────┘   └──────────────┘   └───────────────┘   └──────────────┘
 capture_phone     data/raw/*.csv     brisage / craft     dtv prices
 (auto adb +       + data/dtv.db       prix dans le temps  dtv history
  socket + CDP)    (SQLite, idempot.)  movers / tendances  dtv movers
                                                           dtv brisage
```

Chaque couche est indépendante : on peut rejouer l'ingestion sans recapturer,
relancer une analyse sans réingérer, etc. Les CSV restent la **source de vérité**
(la base SQLite n'est qu'un index rapide reconstructible par `dtv ingest`).

---

## 1. CAPTURE — `dtv capture`

Capture **passive** du client officiel via CDP (Chrome DevTools Protocol) :
on lit les frames WebSocket que le vrai client a déjà déchiffrées. Aucun bot,
aucun mitmproxy, **trafic 100 % légitime**.

- **Automatique** : `dtv config` localise `adb.exe` (PATH ou SDK Android), détecte
  l'émulateur, découvre le socket WebView (`webview_devtools_remote_<pid>`) et
  forwarde — **plus de PID à saisir ni de `--no-adb`**.
- **Ce qu'on capte tout seul** :
  - `avgprices_<ts>.csv` — snapshot marché complet (~4900 items) au login
  - `hdv_passive_<jour>.csv` — prix plancher réel de chaque item ouvert à l'HDV
  - `brisage_observations.csv` — coeff réel + runes obtenues à chaque brisage
- Modules : `dtv/scripts/capture_phone.py`, `dtv/collector/cdp_client.py`,
  `dtv/collector/passive_capture.py`.

> Détail wire-level du protocole : [`PROTOCOL.md`](PROTOCOL.md).

## 2. STORE — `dtv ingest`

Entrepôt **SQLite** (`data/dtv.db`) pour l'historique des prix. L'ingestion est
**idempotente** (clés primaires : réimporter un CSV ne duplique rien).

| Table | Contenu | Clé |
|---|---|---|
| `avg_prices` | 1 snapshot marché par login | (snapshot, gid) |
| `hdv_offers` | 1 ligne par item ouvert à l'HDV | (ts, gid) |
| `brisage_obs` | 1 observation de brisage | (ts, gid) |

Module : `dtv/collector/store.py` (`connect`, `ingest_all`, `price_history`,
`movers`, `search`, `stats`). stdlib pure (sqlite3).

## 3. ANALYSE

Croise les données pour la **décision** :

- **Brisage / craft** — `dtv/collector/brisage.py` + `dtv/scripts/brisage.py` :
  rentabilité de brisage par item, coût = **craft** (`Σ ingrédients × prix`) plutôt
  que l'avgprice (périmé). Coefficient réel auto-collecté → valide la formule.
- **Prix dans le temps** — requêtes `store.price_history` / `store.movers` :
  tendance d'une ressource, plus fortes variations entre snapshots.

> Détail brisage : [`BRISAGE.md`](BRISAGE.md).

## 4. VUE — `dtv …`

Surface unique (`dtv/scripts/dtv.py`). Chaque sous-commande résout ses chemins
seule (config) :

| Commande | Effet |
|---|---|
| `dtv doctor` | état config (adb, catalogues) + base |
| `dtv capture --account jetable` | lance la capture passive (auto) |
| `dtv ingest` | charge les CSV dans la base |
| `dtv prices <nom>` | dernier prix moyen des items qui matchent |
| `dtv history <nom\|gid>` | historique du prix dans le temps |
| `dtv movers [--top N]` | plus fortes variations (2 derniers snapshots) |
| `dtv brisage [...]` | classement rentabilité (catalogue auto) |
| `dtv craft <nom>` | détail du coût de craft d'un item |

---

## Config centrale — `dtv/config.py`

Résout **tout** par ordre de priorité (env → emplacement connu → recherche) :

| Élément | Variable d'env | Défaut |
|---|---|---|
| adb | `DTV_ADB` | PATH, puis SDK Android |
| dossier catalogues | `DTV_SCRAPER_DIR` | dossier scrapers, puis recherche repo |
| data dir | `DTV_DATA_DIR` | `data/` |
| base SQLite | `DTV_DB` | `data/dtv.db` |

`dtv doctor` affiche la config résolue → diagnostic en un coup d'œil.

---

## Flux type (routine quotidienne)

```
1. dtv capture --account jetable     # joue, ouvre l'HDV, brise — Ctrl+C à la fin
2. dtv ingest                        # historise la capture
3. dtv movers                        # qu'est-ce qui a bougé ?
   dtv history "Frêne"               # tendance d'une ressource
   dtv brisage --craft --avg-prices …  # quoi briser de rentable
```

---

## Sécurité (rappel, non négociable)

- Compte **jetable** uniquement, **jamais** le vrai compte.
- **IP résidentielle** uniquement en prod, jamais un VPN datacenter.
- **Pas de mitmproxy** pendant une collecte (la capture CDP est passive, OK).
- Max **4 comptes** par IP/serveur.
- Les secrets (`HAAPI_*`, `.env`) **jamais** commités.

> Détails exploitation : [`OPERATIONS.md`](OPERATIONS.md). Vue d'ensemble &
> sécurité réseau : [`KNOWLEDGE.md`](KNOWLEDGE.md).

---

## État & pistes

- ✅ Capture auto, store SQLite, CLI unique, brisage (coeff réel + craft).
- 🔜 Branchements à enrichir :
  - `dtv brisage` pourrait piocher l'avgprice + rune_gids automatiquement (auj. en args).
  - Export HTML/graph des séries (`analyze.py` fait déjà un export HTML CSV-based).
  - Valuation par palier de runes (Pa/Ra) si plus rentable.
  - Planificateur (Task Scheduler) pour capturer N fois/jour automatiquement.
