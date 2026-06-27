# DTV — Base de connaissances technique

> Fichier de référence à compléter au fil des sessions.
> Toutes les découvertes confirmées par captures réseau, analyse de code ou tests.
>
> 📖 **Référence wire-level complète du protocole : [`PROTOCOL.md`](PROTOCOL.md)**
> (séquences exactes confirmées sur 3 captures HAR, catalogue des messages, formats).
> 🛠️ **Exploitation (maintenance, MAJ, bans, codes de sortie) : [`OPERATIONS.md`](OPERATIONS.md)**
> 💥 **Moteur de brisage (rentabilité runes) : [`BRISAGE.md`](BRISAGE.md)** (porté de RuneMaster).
> 🖥️ **Commandes PowerShell prêtes au copier-coller : [`POWERSHELL.md`](POWERSHELL.md)** (chemins Flo).
> Ce fichier-ci reste la vue d'ensemble (architecture, sécurité, état du projet).

---

## 🏗️ Architecture réseau de Dofus Touch

### Canaux de communication (confirmé PCAPdroid + mitmproxy)

| Domaine | IP | Proto | Rôle |
|---|---|---|---|
| `haapi.ankama.com` | 3.174.255.11 | HTTPS | Auth (apikey + refresh_token → game_token). Bootstrap initial via OAuth2 `auth.ankama.com/token` |
| `dt-proxy-production-login.ankama-games.com` | 34.248.24.94 | WebSocket/TLS | Login server (sélection serveur + personnage) |
| `dt-proxy-production-france.ankama-games.com` | 18.202.155.164 | WebSocket/HTTPS | Game server France (protocole de jeu) |
| `dofustouch.cdn.ankama.com` | 3.160.188.6 | HTTPS | CDN assets (images, sons, data) |
| `dofustouch-logstash-clients.ankama-games.com` | 54.170.227.121 | TLS | **Télémétrie anti-cheat** (ELK Stack) |
| `firebaselogging.googleapis.com` | 216.239.34.223 | HTTPS | Firebase Analytics (comportement joueur) |
| `app.adjust.com` | 185.151.204.9 | HTTPS | Attribution marketing (moins sensible) |
| `dt-proxy-production-early.ankama-games.com` | — | — | Serveur "early access" (vu dans script.js) |

**Points clés :**
- Le game server varie selon le serveur de jeu sélectionné. La France utilise `dt-proxy-production-france.ankama-games.com`. Il doit exister des équivalents pour les autres régions.
- L'IP du game server peut changer (AWS load balancer) — utiliser le hostname, pas l'IP.
- `config.json` chargé depuis le login server avant toute auth : `GET https://dt-proxy-production-login.ankama-games.com/config.json?lang=fr`

### Flux d'authentification complet — ✅ CONFIRMÉ + TESTÉ LIVE BOUT EN BOUT (session 7)

> ⚠️ **CORRECTION MAJEURE S7** : l'ancien flux `CreateApiKey {login, password}` était **faux
> pour un compte Ankama régulier** (`/Api/CreateApiKey` est réservé aux comptes invités ;
> `/Account/Login` n'existe pas en HAAPI v5 → 404). Le vrai flux a 2 niveaux :

**Niveau 0 — Bootstrap initial (une seule fois, manuel, OAuth2 PKCE)**
Fait par l'app au login « se souvenir de moi ». Capturé via DevTools mais **non
réimplémenté** (nécessite un navigateur pour le `code` PKCE) :
```
POST auth.ankama.com/token   (Content-Type: application/x-www-form-urlencoded)
  Body: grant_type=authorization_code&client_id=18&code=<PKCE code>
        &code_verifier=<verifier>&redirect_uri=dofustouch://authorized
  → produit l'apikey longue durée (UUID) + refresh_token (UUID)
```
On **extrait apikey + refresh_token une fois** depuis l'app (DevTools Network →
en-tête `apikey` + `refresh_token` du body RefreshApiKey) et on les met dans `.env`
(`DTV_APIKEY`, `DTV_REFRESH_TOKEN`).

**Niveau 1 — Refresh à chaque run du bot (réimplémenté, `haapi.py`)** :
```
1. POST haapi.ankama.com/json/Ankama/v5/Api/RefreshApiKey
   Content-Type: text/plain;charset=UTF-8     ← PAS form-encoded ni JSON
   Header: apikey: <apikey>
   Body: game_id=18&refresh_token=<refresh_token>&long_life_token=1
   → Retourne (13 champs confirmés S7) : {key, account_id, account_uuid, ip, added_date,
     meta, data, game_id, certificate_id, external_auth_id, access, refresh_token, expiration_date}
   ⚠️ TESTÉ : avec long_life_token=1, `key` (apikey) NE TOURNE PAS (même UUID renvoyé
      sur 3 refresh consécutifs). Le refresh_token est re-renvoyé à chaque fois.
      → token réutilisable, pas single-use. Bonus : `expiration_date` dispo pour pré-check.

2. GET haapi.ankama.com/json/Ankama/v5/Account/CreateToken?game=18   ← "Account" PAS "Game"
   Header: apikey: <key>
   → Retourne: {token: "..."}  ← game_token UUID 36 chars (ex: bd829158-9348-49a1-9c34-7a0eff0d4a5a)
   ✅ CONFIRMÉ live 3 captures + testé S7. game_token CHANGE à chaque appel (jetable).
```

**Niveau 2 — WebSocket (inchangé)** :
```
3. WebSocket wss://dt-proxy-production-login.ankama-games.com/primus?STICKER=<id>&_primuscb=<cb>
   ✅ Chemin = /primus CONFIRMÉ + testé S7
   STICKER = id de session généré côté client. ✅ TESTÉ S7 : charset base64 (`/`,`+`,`-`)
            accepté par le serveur, et la MÊME valeur est réutilisée sur les 2 WS
            (login + jeu), seul `_primuscb` change. Sticky-session du load balancer.

   → send "connecting": {language:"en", server:"login", client:"android",
                         appVersion:"3.11.0", buildVersion:"1.72.12"}   ← PAS de token ici !
   → reçoit ProtocolRequired {requiredVersion:1595, currentVersion:1595}
   → reçoit HelloConnectMessage {salt:"...", key:[bytes signés]}
   → send "login": {username:"<account_id>", token:"<game_token>",
                    salt:"<echo du Hello>", key:[<echo du Hello>]}   ← username = account_id !
   → reçoit CredentialsAcknowledgementMessage
   → reçoit IdentificationSuccessMessage {login, nickname, accountId, ...}  ← PAS de login_token
   → reçoit ServersListMessage {servers:[{id, status, completion, isSelectable, charactersCount, _name}]}
   → send ServerSelectionMessage {serverId:N}   (via wrapper "sendMessage")
   → reçoit SelectedServerDataMessage {serverId, address:"<IP interne AWS>", port:5555,
                ticket:"<ticket game>", _access:"https://dt-proxy-production-canada.ankama-games.com"}
      ⚠️ Le host du game server = champ "_access" (hostname), PAS "address" (IP interne 172.x.x.x inutilisable)
   → send "disconnecting": "SWITCHING_TO_GAME"
   → reçoit "primus::server::close"

4. WebSocket wss://<_access host>/primus?STICKER=...&_primuscb=...
   → send "connecting": {language:"en", server:{address, port, id}, client:"android",
                         appVersion:"3.11.0", buildVersion:"1.72.12"}
   → reçoit ProtocolRequired puis HelloGameMessage
   → send AuthenticationTicketMessage {ticket:"<ticket de SelectedServerData>", lang:"en"}  (via sendMessage)
   → reçoit AuthenticationTicketAcceptedMessage
   → send "pingSession": <nonce>          ← parité client (anti-fingerprint)
   → send CharactersListRequestMessage
   → reçoit CharactersListMessage {characters:[{id, level, name, breed, sex}]}
   → send CharacterSelectionMessage {id}
   → reçoit CharacterSelectedSuccessMessage
   → send ClientKeyMessage {key:<21 chars aléatoires>}   ← parité client
   → send GameContextCreateRequestMessage
   → reçoit SequenceNumberRequestMessage   ← ⚠️ ANTI-CHEAT
   → send SequenceNumberMessage {number:N}  ← N incrémental par connexion (1,2,3…)
   → reçoit GameContextCreateMessage + CurrentMapMessage {mapId} ← stocker pour npcMapId HDV
```

**⚠️ SequenceNumber (anti-cheat) — confirmé S6, désormais géré :**
Le serveur envoie `SequenceNumberRequestMessage` (vide) quand il veut ; le client
répond `SequenceNumberMessage{number:N}` avec N **incrémental par connexion** (repart
à 0 à chaque reconnexion). Ne PAS répondre = session anormale. `ClientKeyMessage` et
`pingSession` sont des trames de parité client (non bloquantes mais émises par le vrai
client) — ajoutées pour réduire l'empreinte. Détail complet : `PROTOCOL.md` §3.

**Région du game server :** dépend du compte. Ce compte (anglais) → **canada** (serverId 533).
Il existe `dt-proxy-production-{france,canada,early,...}`. Toujours utiliser `_access`, jamais coder en dur.

**Calls spéciaux Primus (hors wrapper sendMessage) :** `connecting`, `login`, `disconnecting`,
`pingSession`, `moneyGoultinesAmountRequest`, `arenaPlayerRank`, etc. Le reste passe par
`{"call":"sendMessage","data":{"type":..., "data":...}}`.

---

## 📡 Protocole de jeu

### Type : JSON over WebSocket (Primus)

**Pas de binaire DofusProtocol** (contrairement à Dofus 2 PC).

Confirmé par analyse de `script.js` (bundle webpack 5MB extrait du device Android).

**Format message envoyé :**
```json
{"call": "sendMessage", "data": {"type": "NomDuMessage", "data": {champs...}}}
```

**Format message reçu :**
```json
{"_messageType": "NomDuMessage", champ1: ..., champ2: ...}
```

**Primus heartbeat :**
```
← "primus::ping::1234567890"
→ "primus::pong::1234567890"
```
Doit être répondu dans ~30s sinon le serveur déconnecte.

**⚠️ Frames de contrôle Primus en string JSON-encodé (découvert + corrigé S7) :**
Le serveur envoie des frames de contrôle comme `"primus::server::open"` **encodées en
JSON** (avec guillemets) juste après le handshake. `json.loads()` les renvoie comme un
`str` Python (pas un dict) → `msg.get()` plantait avec `'str' object has no attribute 'get'`.
Le WebView du navigateur les absorbe en interne → **invisibles dans les captures DevTools**,
d'où leur absence des HAR. `primus_client._on_message` gère désormais le cas `isinstance(msg, str)`
(ignore `server::open`, traite `ping`/`close` même JSON-encodés).

**Note :** Le login server utilise des calls spéciaux ("connecting", "login") en plus du standard "sendMessage".

### HDV — architecture — ✅ CONFIRMÉ PAR CAPTURE LIVE (session 4)

**L'HDV dans Dofus Touch est accessible depuis n'importe où** (bouton dans l'interface),
pas besoin d'être près d'un PNJ physique. Niveau min confirmé : **10** (confirmé en jeu session 4).

#### ⚠️ Le flow HDV est en DEUX étapes (correction majeure session 4)

```
1. → NpcGenericActionRequestMessage {npcId:0, npcActionId:6, npcMapId:<mapId réel>}
2. ← ExchangeStartedBidBuyerMessage {buyerDescriptor:{quantities, types, taxPercentage, maxItemLevel}}

   Pour CHAQUE type T de buyerDescriptor.types :
3. → ExchangeBidHouseTypeMessage {type:T}
4. ← ExchangeTypesExchangerDescriptionForUserMessage {typeDescription:[GID1, GID2, ...]}
        ← liste des objectGID qui ONT des offres dans ce type (peut être vide)

   Pour CHAQUE objectGID G de typeDescription :
5. → ExchangeBidHouseListMessage {id:G}
6. ← ExchangeTypesItemsExchangerDescriptionForUserMessage {itemTypeDescriptions:[{objectUID, effects, prices}]}
        ← les offres réelles (prix) pour cet objet

7. → LeaveDialogRequestMessage {} (data:null)
8. ← ExchangeLeaveMessage {dialogType:11}
```

**Distinction critique entre les deux messages de réponse :**
- `ExchangeTypesExchangerDescriptionForUserMessage` (SANS "Items") = liste de GIDs d'un type → réponse à `ExchangeBidHouseTypeMessage`
- `ExchangeTypesItemsExchangerDescriptionForUserMessage` (AVEC "Items") = prix d'un objet → réponse à `ExchangeBidHouseListMessage`

| Message | Sens | Rôle |
|---|---|---|
| `NpcGenericActionRequestMessage` | → | Ouvrir HDV (`npcId:0, npcActionId:6, npcMapId:<mapId réel>`) |
| `ExchangeStartedBidBuyerMessage` | ← | HDV ouvert — `buyerDescriptor` (quantities, types) |
| `ExchangeBidHouseTypeMessage` | → | Demander les GIDs d'un type (`{type:T}`) |
| `ExchangeTypesExchangerDescriptionForUserMessage` | ← | Liste des GIDs (`typeDescription:[...]`) |
| `ExchangeBidHouseListMessage` | → | Demander les prix d'un objet (`{id:GID}`) |
| `ExchangeTypesItemsExchangerDescriptionForUserMessage` | ← | Offres/prix (`itemTypeDescriptions:[...]`) |
| `ExchangeBidHouseBuyMessage` | → | Acheter (`{uid, qty, price}`) — pas utile pour la collecte |
| `LeaveDialogRequestMessage` | → | Fermer HDV |
| `ExchangeLeaveMessage` | ← | HDV fermé |

**`npcMapId` = le vrai mapId** (ex: `146540544`), pris de `CurrentMapMessage.mapId`. PAS -1.
`npcActionId: 6` = mode achat. Référence : `openBidHouse()` dans script.js.

#### Format réel de `ExchangeTypesItemsExchangerDescriptionForUserMessage` (capture live)

```json
{
  "_messageType": "ExchangeTypesItemsExchangerDescriptionForUserMessage",
  "itemTypeDescriptions": [
    {
      "_type":     "BidExchangerObjectInfo",
      "objectUID": 1221817,
      "effects":   [{"_type": "ObjectEffectInteger", "actionId": 110, "value": 10}],
      "prices":    [14, 280, 2978, 0]
    }
  ]
}
```

**Points clés :**
- `objectUID` = id unique de l'offre (pas du type d'item)
- `prices` a **4 éléments** : `[x1, x10, x100, x1000]` — indexé sur `buyerDescriptor.quantities`
- `0` = pas d'offre à cette quantité (ici x1000 = 0)
- PAS de champ `tutorialPrice` dans la capture réelle (était une supposition)
- `objectGID` = l'`id` envoyé dans `ExchangeBidHouseListMessage` (le client le connaît déjà)

#### `buyerDescriptor` dans `ExchangeStartedBidBuyerMessage` (capture live S6)
- `quantities` = **`[1, 10, 100, 1000]`** ← 4 tiers CONFIRMÉ (x1000 existe)
- `types` = liste des GIDs de types (**128 types**, pas 126 : `[1,2,3,…226]`)
- `taxPercentage` = **3** (taxe de vente HDV % — utile pour calcul de rentabilité)
- `maxItemLevel` = 1000
- `maxItemPerAccount` = **75** (nb max d'objets en vente par compte)
- `unsoldDelay` = **672** (heures avant retour des invendus = 28 jours)

Capturé dans `HdvCollector.economics` à l'ouverture de l'HDV.

#### ⭐ Prix moyens — `ObjectAveragePrices` (snapshot marché complet)

**Un seul message = ~4906 prix d'items.** Le client le demande pendant l'init ;
trafic 100 % légitime.
```
→ ObjectAveragePricesGetMessage {}                       (aucun paramètre)
← ObjectAveragePricesMessage {ids:[…], avgPrices:[…]}    (2 tableaux parallèles)
```
- Prix **unitaire x1**, **par serveur**, moyenne des ventes récentes (volume + récence).
- **PAS figé 24 h** : 115 GID ont bougé entre 2 captures à 51 min d'écart → collecte
  multi-fois/jour pertinente.
- Complémentaire de l'HDV : avg = tendance/baseline, HDV = floor temps réel (x1…x1000).
- Module : `dtv/collector/avg_prices.py` (`AveragePricesCollector`). Voir `PROTOCOL.md` §4.

#### Ressources (superTypeId=9) — whitelist de collecte
`dtv/collector/item_types.py` : **64 types ressources** extraits de
`window.gui.databases.ItemTypes`. `collect_resources()` n'interroge que ceux présents
dans le `buyerDescriptor` (61/64 ; absents : Souvenir 125, Awakening 211, Vouchers 241).
Le projet se concentre sur les ressources (équipements hors scope — rolls variables).

#### `CurrentMapMessage` (reçu quand le joueur change de map)
```json
{ "_messageType": "CurrentMapMessage", "mapId": 123456789 }
```
Nécessaire pour `npcMapId` dans l'ouverture HDV.

### Headers Android requis (✅ alignés sur l'émulateur réel, capture har_3 S7)

> ⚠️ **CORRECTION S7** : l'ancien UA (`SM-S908E / Android 9 / Chrome/129`) ne correspondait
> PAS à l'émulateur de capture. Le vrai UA de l'AVD (Android 12, Chrome/91) est ci-dessous.
> Mis à jour dans `haapi.py` (HAAPI) ET `primus_client.py` (WebSocket) pour cohérence.

```
User-Agent: Mozilla/5.0 (Linux; Android 12; sdk_gphone64_x86_64 Build/SE1A.220826.008; wv)
            AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/91.0.4472.114
            Mobile Safari/537.36 DofusTouch Client 3.11.0
x-requested-with: com.ankama.dofustouch
accept-language: en-US,en;q=0.9      ← en-US (le compte est anglais/canada), PAS fr-FR
```
HAAPI (POST RefreshApiKey) : `Content-Type: text/plain;charset=UTF-8`.
WebSocket upgrade : ajoute `Origin: file://` + `Accept-Language: en-US,en;q=0.9`.

---

## 🛡️ Système de détection Ankama

### Niveau réseau (côté serveur)

**1. IP reputation — risque le plus élevé**
- IPs datacenter, VPN, proxy → ban quasi-immédiat
- Ankama bloque activement les plages IP des fournisseurs VPN connus
- **Règle absolue : IP résidentielle uniquement en production**
- Un compte a déjà été banni à cause de WireGuard (VPN datacenter) actif pendant les tests

**2. TLS fingerprinting (JA3/JA4)**
- Ankama utilise Cloudflare (confirmé sur `haapi.ankama.com`) qui fait du JA3 fingerprinting natif
- Un client Python standard (`requests`/`websocket-client`) a un JA3 hash complètement différent d'un Android WebView Chrome
- **Solution : `curl_cffi` avec `impersonate="chrome_android"` pour HAAPI**
- ✅ **WebSocket Primus — RISQUE LEVÉ EN PRATIQUE (testé S7)** : `websocket-client` (JA3 Python)
  a connecté **sans souci aux DEUX serveurs** (login + jeu) jusqu'à « game ready ». Les proxies
  `dt-proxy-production-*` ne sont PAS derrière Cloudflare et ne semblent pas faire de JA3 sur le
  WebSocket. Migration vers `curl_cffi.ws_connect` non nécessaire (reste en réserve si bans inexpliqués).

**3. Détection de proxy/MITM**
- PCAPdroid seul semble toléré (nos captures récentes OK)
- mitmproxy change le fingerprint TLS → flag
- PCAPdroid + mitmproxy + WireGuard simultanément = ban (vécu)
- L'interface VPN de PCAPdroid cause du DoT sur port 853 (visible dans les captures) → comportement réseau anormal

### Niveau télémétrie (Ankama côté client)

**`dofustouch-logstash-clients.ankama-games.com` — le mouchard principal**
- Le jeu envoie des rapports en temps réel vers le stack ELK d'Ankama
- Se connecte au démarrage ET après certaines actions en jeu (2 connexions dans le CSV "avec HDV")
- Contient probablement : fingerprint device, état réseau, processus actifs, anomalies détectées
- Notre client Python **ne fera pas ces connexions** → signal d'absence potentiel
  - Risque estimé : faible à court terme (les bots existants probablement non plus)
  - Surveiller si des bans surviennent sans autre cause

**`firebaselogging.googleapis.com`**
- Firebase Analytics : sessions, événements, comportements
- Ankama peut croiser ces données avec l'activité en jeu

### Niveau comportement en jeu (anti-bot timing)

Source : documentation AnkaBot (communauté de bots Dofus) — retours d'expérience 2022-2024.

**Comment Ankama détecte les bots :**
1. **Timing trop régulier** — les actions humaines ont de la variance. Un bot qui fait exactement la même action toutes les X ms est flaggé.
2. **Vitesse inhumaine** — actions plus rapides que ce qu'un humain peut faire (clic après clic sans délai).
3. **Répétitivité parfaite** — même séquence d'actions répétée en boucle sans variation.
4. **"Pause time"** — Ankama a placé un antibot dans les déplacements qui monitore le temps de pause entre les maps.
5. **Volume d'actions inhabituel** — trop de transactions HDV sur une courte période.

**Mécanisme de ban :**
- Les antibots **flagguent** les comptes, ils ne bannissent pas automatiquement
- Les bans sont ensuite appliqués **manuellement par vague** (wave bans)
- Les anciens comptes avec du temps de jeu accumulé sont moins touchés
- Les comptes neufs (comme nos throwaway) sont plus surveillés

**Spécifique HDV :**
- Requêtes trop rapides entre catégories
- Ouverture/fermeture répétitive du HDV
- Consultation systématique de toutes les catégories à intervalles fixes

### Niveau client (détection dans l'app)

**Ankama Shield** — middleware de sécurité (vu dans script.js : `Ankama/Shield`)
- Détecte les VPN/proxy au niveau du compte (pas seulement réseau)
- Incompatible avec les VPNs selon les forums officiels

**Détection d'émulateur**
- L'AVD Android Studio et BlueStacks ont des fingerprints détectables (Build.FINGERPRINT = "generic", IMEI factice, etc.)
- Actuellement pas de ban immédiat observé sur émulateur seul (nos sessions sans VPN OK)
- Risque à surveiller long terme

**Détection de Frida**
- `/data/local/tmp/frida-server` détectable par le jeu
- Hooks sur les fonctions SSL BoringSSL laissent des traces mémoire
- Potentiellement reporté via Logstash

### Niveau protocole (empreinte wire-level) — analysé S6

Une réimplémentation se trahit par des **différences de sérialisation** invisibles
fonctionnellement mais détectables par inspection serveur. Vérifié sur 3 captures :

- **Omission de `data`** : le vrai client omet le champ `data` interne pour les messages
  sans argument (`{"type":"CharactersListRequestMessage"}`, pas `…,"data":{}`).
  ✅ Corrigé S6 (`primus_client.send_message` : `data` falsy → omis). Voir `PROTOCOL.md` §1.
- **Formats anti-cheat** à respecter exactement : `ClientKey` = 21 chars alphanum,
  `pingSession` = 9 chiffres, `SequenceNumber` démarre à 1 puis +1 par connexion.
- **Réponse au `SequenceNumberRequest`** obligatoire (anti-cheat). Déclenché par les
  **actions de jeu** ; le HDV en lecture ne le déclenche pas → empreinte bot minimale.

**Signaux de suspicion à monitorer** (santé compte) : `TrustStatus.trusted=false`,
`AuthenticationTicketRefusedMessage`, ou `SequenceNumberRequest` inattendu pendant la
collecte HDV. Tant que `trusted=true` (cas des 3 sessions), le compte est OK côté serveur.

**Invariants auth/anti-cheat (constant vs variable entre sessions)** : table complète
dans `PROTOCOL.md` §9. Résumé : ne changent à chaque run que `token` (HAAPI), `salt`/`key`
(challenge serveur), `STICKER` (client) et `ticket` (game server). Compte, serveur,
versions et IP interne (`172.29.2.186:5555`) sont stables.

---

## 🎯 Stratégie de collecte : capture PASSIVE via CDP (décision S8)

> Conclusion de l'analyse de détection ci-dessus : **le risque dominant n'est ni
> le fingerprint réseau ni l'absence de télémétrie — c'est le COMPORTEMENT.** Un
> bot qui ne fait que l'HDV à heures fixes finit flaggé quoi qu'on fasse sur le
> fingerprint. D'où le pivot : **on ne rejoue pas un client, on écoute le vrai.**

### Principe
Le **vrai client officiel** (sur le téléphone rooté de Flo) joue normalement. Un
**mini PC dédié** s'attache à la WebView du jeu via **Chrome DevTools Protocol
(CDP)** — exactement comme les captures HAR S4/S7, mais automatisé — et lit les
frames WebSocket que le client a **déjà déchiffrées pour lui-même**.

```
[S22 rooté, 4G] ──TLS natif──────────────►  Ankama
   │  (le trafic de jeu NE passe PAS par le mini PC)
   │ CDP / ADB sans fil (via WireGuard maison)
   ▼
[Mini PC] capture_phone.py → cdp_client.py → passive_capture.py → data/raw/*.csv
```

### Pourquoi c'est le plus safe possible
- **Aucune empreinte réseau** : c'est le client natif qui parle à Ankama (TLS,
  JA3, heartbeats, télémétrie Logstash, SequenceNumber — tout authentique). On
  n'intercepte ni ne ré-encrypte rien → **mitmproxy n'est PAS utilisé** (CDP lit
  au niveau applicatif, pas réseau).
- **Comportement 100% humain** : c'est Flo qui joue et clique. Plus de pattern bot.
- **CDP est purement local** (téléphone ↔ mini PC). Ankama ne peut pas voir qu'un
  debugger est attaché.

### Pré-requis (résolu S8)
- **Root Magisk** sur le S22 (BeyondROM 5.2, Knox déjà `0x1`, banque OK avec
  Shamiko + DenyList + PlayIntegrityFix). Nécessaire pour forcer le WebView
  debugging du client release + lire `/proc/net/unix`.
- **ADB sans fil** + **WireGuard vers la maison** : seul le canal ADB/CDP transite
  par WireGuard ; le **trafic de jeu sort en 4G résidentielle directe** → pas
  d'IP VPN vue par Ankama (voir nuance dans les règles ci-dessous).

### Ce qui est capturé
- **Chaque item ouvert en HDV** (`hdv_passive_<jour>.csv`, append en continu) :
  corrélation FIFO entre `ExchangeBidHouseListMessage` *envoyé* (le clic) et
  `ExchangeTypesItemsExchangerDescriptionForUserMessage` *reçu* (les prix).
- **Le snapshot prix moyens à chaque connexion** (`avgprices_<ts>.csv`, ~4900 items).

### Code (S8)
- `dtv/collector/cdp_client.py` — `CDPClient` : attache la WebView, stream les
  frames WS, reconnexion auto si le jeu ferme.
- `dtv/collector/passive_capture.py` — `PassiveCollector` : parse les frames
  observées, réutilise `hdv._aggregate_offers`, écrit les CSV.
- `dtv/scripts/capture_phone.py` — runner : `adb forward` auto + capture continue.

> Le **bot actif** (`collect.py`) reste valable en repli/test sur compte jetable,
> mais la voie de production privilégiée est la capture passive.

---

## ⚠️ Règles de sécurité opérationnelles

```
JAMAIS le vrai compte Flo  (sauf capture PASSIVE : c'est lui qui joue, aucun trafic injecté)
JAMAIS un VPN datacenter (NordVPN, ExpressVPN...) comme IP de SORTIE du jeu
JAMAIS mitmproxy actif pendant une session de collecte réelle (on passe par CDP/DevTools)
Max 4 comptes par IP/serveur
IP résidentielle uniquement en production
Compte Gmail jetable créé depuis l'IP de production (pas depuis VPN)
Ankama bloque Protonmail à l'inscription
```

> **Nuance WireGuard (S8)** : la règle « jamais de VPN datacenter » vise l'**IP de
> sortie** vue par Ankama. En capture passive, le **trafic de jeu sort en 4G
> directe** ; WireGuard ne transporte que le canal **ADB/CDP** (téléphone ↔ mini PC).
> Un WireGuard vers **son propre réseau résidentiel** (IP de sortie résidentielle)
> est acceptable ; c'est l'exit datacenter qui a causé le ban historique, pas le
> tunnel en soi.

**Délais minimum recommandés :**
- Entre deux requêtes de catégorie HDV : 2-5s avec variance aléatoire
- Entre ouverture HDV et première requête : 1-3s
- Entre sessions de collecte : respecter le planning (7h, 12h, 18h, 22h, 2h)

---

## 🔧 Stack technique

### APK Dofus Touch 3.11.0
- Type : Apache Cordova (JavaScript)
- Le code JS n'est **pas** dans l'APK — téléchargé au runtime
- Chemin sur device : `/data/data/com.ankama.dofustouch/files/files/js/build/script.js`
- Taille : 5MB (bundle webpack minifié)
- Contient toutes les définitions de messages du protocole
- Nécessite `adb root` + `su -c` pour y accéder (stockage interne)

### Émulateurs
- **AVD Android Studio** (Pixel_6_Pro, API 31 x86_64) — recommandé pour Frida
  - `adb root` natif
  - `adb -s emulator-5554`
  - IP hôte depuis AVD : `10.0.2.2`
  - Port mitmproxy : 8082
- **BlueStacks 5** (Pie64 / Android 9) — recommandé pour extraction de fichiers
  - Rooté Magisk → `su -c "commande"` pour accès root
  - `adb connect 127.0.0.1:5555`
  - **Frida freeze BlueStacks** → ne pas utiliser Frida ici

### Outils de capture
- **PCAPdroid** — capture réseau (VPN local) — OK seul, pas avec mitmproxy+WireGuard
- **mitmproxy** port 8082 — capture HTTPS (ne voit pas le WebSocket game, uniquement REST)
- **Frida 17.12.0** — hook SSL sur AVD uniquement

---

## 🚦 État actuel du projet (pour reprise de session)

### Ce qui est codé et prêt à tester

| Fichier | État | Notes |
|---|---|---|
| `dtv/collector/haapi.py` | ✅ **Réécrit S7 + TESTÉ** | Flux **RefreshApiKey → CreateToken** ; `authenticate(apikey, refresh_token)` → (account_id, token, new_apikey, new_rt) |
| `dtv/collector/primus_client.py` | ✅ **MAJ S7** | + gestion frames string JSON (`primus::server::open`) ; UA émulateur |
| `dtv/collector/connection.py` | ✅ **MAJ S7** | + STICKER session-stable base64 ; buildVersion 1.72.12 ; login flow **testé OK** |
| `dtv/collector/hdv.py` | ✅ MAJ S6 | Flow HDV 2 étapes + `collect_resources()` + `economics` |
| `dtv/collector/avg_prices.py` | ✅ Nouveau S6 | **Snapshot prix moyens (~4900 items / message)** |
| `dtv/collector/item_types.py` | ✅ Nouveau S5 | 64 types ressources (superTypeId=9) + 41 core |
| `dtv/collector/timing.py` | ✅ Prêt | human_delay, jitter, backoff_delay |
| `dtv/scripts/test_auth.py` | ✅ Prêt | Test HAAPI isolé |
| `dtv/scripts/test_connect.py` | ✅ Prêt | Test WebSocket connectivité |
| `dtv/scripts/test_login.py` | ✅ Prêt | Test login flow complet |
| `dtv/scripts/collect.py` | ✅ MAJ S6 | Pipeline bot actif : avg-prices + HDV ressources (repli/test) |
| `dtv/collector/cdp_client.py` | ✅ **Nouveau S8 + testé** | **Capture passive** : attache la WebView via CDP, stream les frames WS |
| `dtv/collector/passive_capture.py` | ✅ **Nouveau S8 + testé** | Parse les frames observées (clic→prix + snapshot), écrit les CSV |
| `dtv/scripts/capture_phone.py` | ✅ **Nouveau S8** | Runner capture passive : `adb forward` auto + capture continue |
| `dtv/scripts/dump_session.py` | ✅ Nouveau S8 | Dump bot : toutes les frames WS → JSONL (debug/MAJ protocole) |

### Prochaine étape immédiate : première COLLECTE live (auth + login ✅ testés S7)

```
# 0. Bootstrap (une fois) : extraire apikey + refresh_token depuis l'app via DevTools
#    → mettre dans .env : DTV_APIKEY, DTV_REFRESH_TOKEN, DTV_SERVER_ID=533

# 1. Installer les dépendances
pip install -r requirements.txt

# 2. ✅ Auth HAAPI (TESTÉ OK S7) — rafraîchit le token, met à jour .env
python -m dtv.scripts.test_auth

# 3. ✅ Login complet jusqu'à « game ready » (TESTÉ OK S7)
python -m dtv.scripts.test_login

# 4. ⏳ PROCHAIN TEST : collecte prix moyens (1 message, ~4900 items)
python -m dtv.scripts.collect --avg-prices-only

# 5. Puis collecte HDV ressources
python -m dtv.scripts.collect
```

⚠️ **Ne pas lancer l'app Ankama sur le compte pendant que le bot tourne** (chaîne de
tokens partagée → risque d'invalidation mutuelle si le refresh_token venait à tourner).

### ✅ Inconnues résolues par les captures live (sessions 4–6)

- ✅ Chemin Primus = `/primus`
- ✅ IDs serveurs : Tiliwan=530, Kelerog=531, Blair=532, **Talok=533** (compte test), Tournament=411
- ✅ `npcMapId` = le vrai mapId (de `CurrentMapMessage` = `MapComplementaryInfo`), PAS -1
- ✅ Quantités = `[1, 10, 100, 1000]` (4 tiers)
- ✅ `SelectedServerDataMessage` : host dans `_access`, ticket dans `ticket`, address = IP interne inutile
- ✅ Flow HDV en DEUX étapes (type→GIDs, puis GID→prix)
- ✅ Login : `username`=account_id, token dans "login" pas "connecting"
- ✅ **Version protocole = 1595** (login + game)
- ✅ **SequenceNumber anti-cheat** : serveur demande → client répond N incrémental (géré S6)
- ✅ **ClientKeyMessage** : clé 21 chars aléatoires avant GameContextCreate (géré S6)
- ✅ **buyerDescriptor** : 128 types, tax 3%, maxItemPerAccount 75, unsoldDelay 672h
- ✅ **ObjectAveragePrices** : ~4906 items/message, x1, par serveur, dynamique (115 chgts/51min)
- ✅ **64 types ressources** (superTypeId=9) extraits ; 61 présents en HDV
- ✅ **Auth réelle = RefreshApiKey → CreateToken** (S7) ; `CreateApiKey`=invités, `Account/Login`=404
- ✅ **apikey ne tourne PAS** avec `long_life_token=1` (token réutilisable, pas single-use)
- ✅ **WebSocket Python connecte OK** aux 2 serveurs (JA3 non vérifié sur les proxies de jeu)
- ✅ **STICKER** : charset base64 accepté, réutilisé sur les 2 WS (testé S7)
- ✅ **Frames de contrôle Primus string** (`primus::server::open`) invisibles en HAR (géré S7)

### Ce qui reste à investiguer

- Endpoint token : `Account/CreateToken` **confirmé live + testé** (S7) ; `Game/CreateToken` abandonné
- Le paramètre `STICKER` est-il *omettable* ? (non bloquant — il fonctionne tel quel)
- Expiration du `refresh_token` longue durée : durée de vie réelle ? (`expiration_date` dispo dans la réponse RefreshApiKey — à logger/surveiller)
- Re-bootstrap : si le refresh_token expire un jour, refaire l'extraction OAuth depuis l'app (ou implémenter le flux PKCE complet)
- Logstash télémétrie : confirmée active (config.json `mediatorUrl`). Absence non simulée par notre client. Risque faible à court terme.
- Fréquence exacte de rafraîchissement du prix moyen (semble continu/au fil des ventes, pas 24h)

---

## 📋 TODO / Inconnues à résoudre

- [x] ~~Tester le code (S6/S7) contre le serveur réel — login flow + SequenceNumber~~ ✅ **S7 : auth + login testés OK bout en bout**
- [x] ~~Token HAAPI : single-use ou réutilisable ?~~ ✅ **S7 : apikey réutilisable (long_life_token=1), game_token jetable**
### Données statiques (scrapers)

- [ ] **⚠️ Vérifier les 9 items 404 en jeu** — GIDs 14002, 8123, 8126, 15617, 11747, 11633, 8097, 6661 (équipements) + 2000 (ressource). Voir KNOWLEDGE.md § Items 404 permanents.
- [ ] **Nom_EN enrichissement** : lancer `scrap_ingredients_dofusdb_api_mt_final.py` depuis le PC (api.dofusdb.fr bloqué depuis le cloud). Enrichit ressources + équipements avec les noms EN.
- [ ] **Consommables scraper** : `scrape_consommables_dofus_touch.py` existant a des bugs (Niveau vide, Type avec préfixe). À réécrire avec la même architecture Phase1/Phase2 validée (comme scrap_ressources_full.py).

### Collecte de prix live

- [ ] ⏳ **PROCHAIN : tester `collect --avg-prices-only`** (1 message, ~4900 items) puis collecte HDV complète
- [ ] Mesurer la durée d'un run `--avg-prices-only` (1 message) vs collecte HDV ressources complète
- [ ] Logger `expiration_date` du refresh_token et surveiller sa durée de vie
- [ ] Tester si l'absence de Logstash est détectée sur plusieurs jours
- [ ] Watchlist / pruning : retirer les items dont le prix ne bouge jamais (après quelques jours de données)
- [ ] Scheduler multi-comptes : rotation horaires + rotation des types consultés (anti-pattern)
- [ ] **Scheduler : éviter la fenêtre de maintenance (mardi 7h30-11h Paris)** + gérer codes 2/3

### DTV — intégration et analyses

- [ ] **Tableau "meilleurs items à farmer"** : croiser prix HDV (CSV `capture_phone`) × drops monstres (maintenant dispo dans `ressources_dofus_touch_full.xlsx` colonne `Drops_monstres` avec GID monstre + taux %)
- [x] ~~**Porter RuneMaster dans DTV** : moteur de brisage~~ ✅ **S10-11 : `dtv/collector/brisage.py` + CLI + tests** (formule + coefficient + paliers, voir [`BRISAGE.md`](BRISAGE.md))
- [ ] ⭐ **IMPORTANT (Flo) — Auto-collecte du coefficient de brisage via CDP au moment du brisage** :
  - **Confirmé (captures Concasseur Dofus Touch)** : le coefficient n'est affiché qu'**APRÈS**
    brisage, par item (ex : Hache du Mulou 439 %, Roncier 727 %, Cerberus ~130 %). Les runes
    sont en **unités SIMPLES** (grandes quantités : 99, 837, 1211…), pas en paliers Ra.
  - **Bonne nouvelle** : le jeu affiche « Valeur estimée des objets détruits » +
    « Valeur estimée des runes obtenues » → le client **reçoit déjà** un message avec,
    par item : **coefficient + liste (rune, quantité)**. C'est la cible de capture.
  - **Formule validée** sur ces captures (Hache du Mulou/Brèche non magées : prédit ≈ observé
    direct). Caveat : items **magés** rendent plus (stats réelles > base catalogue).
  - **Plan** : DevTools/CDP ouvert pendant un brisage réel (comme la capture passive des
    prix) → identifier le message (`*BreakMessage` / `*RunesMessage` ?) dans les frames WS.
    Une fois trouvé : `coefficient_reel` + `dernier_brisage` + runes réelles se remplissent
    **tout seuls**, et ça **valide la formule** (runes prédites vs obtenues au coeff donné).
  - **INDICE (HAR 27/06)** : le brisage passe par l'échange « craft ». Message reçu pendant
    un brisage = `ExchangeCraftInformationObjectMessage` (fuite via la télémétrie `lastReceivedMessage`).
    ⚠️ Un HAR DevTools **ne contient pas les frames WS** → utiliser `capture_phone.py --dump-raw`
    (dump JSONL de toutes les frames dans `data/raw/ws_raw_<jour>.jsonl`) pendant un brisage,
    puis identifier le message porteur du coefficient + des runes.
  - Le coeff varie 1 %–4000 %, tend vers le plancher à chaque brisage → fraîcheur de la date = fiabilité.
- [ ] **Brancher les prix runes HDV live** sur le brisage : `build_rune_gids.py` (PC, utilise les noms runes exacts) → `rune_gids.json`, puis `brisage.py --rune-gids` → revenu au prix réel du marché
- [ ] **Valuation par palier de runes** : vendre en Pa/Ra si `prix_Pa > 3×prix_simple` (données `tiers` déjà dans `runes.json` ; manque les prix par palier)
- ✅ **Formule de brisage des ARMES — RÉSOLU (stacking)** : les apparentes ×3–10
  sur Marteau du Boufcoul (niv41), Cerberus (niv16), Bâton Feuillu (niv14), Pelle à
  Thart' (niv24) étaient dues au **stacking du Concasseur** : les items avec exactement
  les mêmes stats se regroupent sous une icône avec un compteur de pile (×2, ×3…).
  Les runes affichées = formule × taille de pile. Formule validée sur TOUS les items.
- ✅ **Brisage : coût de CRAFT branché** (`--craft`) : coût = Σ(ingrédient × prix
  moyen) depuis la colonne `Recette` + avgprice des ingrédients (nom→GID via
  catalogues). C'est le BON coût d'acquisition — l'avgprice de l'item fini est
  périmé/faux pour le bas niveau (Bâton de Boisaille avg=10 mais craft=75). Diag :
  `--explain "<nom>"`. Reste : recette à un seul niveau (sous-craft non récursif).
- [ ] Résolution GID→nom d'item (charger les données i18n/d2o) pour des CSV lisibles

### Infrastructure (PC / téléphone)

- [ ] **Capture passive (S8)** : installer Magisk sur le S22, vérifier banque (Shamiko/PIF), activer WebView debugging + ADB sans fil, setup WireGuard maison
- [ ] Tester `capture_phone.py` end-to-end sur le vrai téléphone (premier item HDV capturé)
- [ ] Fix PowerShell profile pour `dtv analyze` shortcut (stale in-memory copy)
- [ ] Ajouter ADB platform-tools au PATH Windows de façon permanente

---

## 📝 Historique des sessions

### Session 8 (pivot stratégique : capture PASSIVE via CDP)
- **Constat** : après analyse de détection, le risque dominant est le **comportement**,
  pas le fingerprint. Un bot actif sur compte jetable ne tiendrait que 1-2 semaines.
- **Décision** : collecter via le **vrai client officiel** sur le téléphone rooté de Flo,
  écouté par un **mini PC** via **CDP** (DevTools), comme les captures HAR mais automatisé.
  → aucune empreinte réseau, comportement 100% humain, **pas de mitmproxy** (lecture
  applicative, pas réseau).
- **Faisabilité root validée** : S22 (SM-S901B) sous BeyondROM 5.2, **Knox déjà `0x1`**,
  appli bancaire fonctionnelle malgré l'état non-stock → Magisk + Shamiko + DenyList +
  PlayIntegrityFix sans risque supplémentaire. TWRP présent → flash Magisk trivial.
- **Architecture réseau** : seul le canal ADB/CDP passe par **WireGuard maison** ; le
  **trafic de jeu sort en 4G résidentielle directe** → pas d'IP VPN vue par Ankama
  (lève le conflit apparent avec la règle « jamais WireGuard », qui visait l'exit datacenter).
- **Code livré + testé** (frames synthétiques) :
  - `cdp_client.py` (`CDPClient`) : découverte de la cible, stream `Network.webSocketFrame*`,
    filtre opcode texte, mapping requestId→URL, reconnexion auto. Correctif : `max_size`
    n'existe pas dans `websocket-client` (retiré).
  - `passive_capture.py` (`PassiveCollector`) : corrélation FIFO clic→prix, réutilise
    `_aggregate_offers`, snapshot prix moyens par connexion, append CSV durable par jour.
  - `capture_phone.py` : runner avec `adb forward` auto (parse `/proc/net/unix`).
- **Tests** : 2 items HDV + 1 snapshot agrégés correctement ; enveloppe CDP filtrée OK
  (binaire/contrôle/ack ignorés). Format CSV identique à la voie bot.

### Session 7 (premier test live complet auth + login — ✅ SUCCÈS)
- **Setup live sur le PC de Flo** (Windows, IP résidentielle, AVD émulateur).
- **Correction majeure du flux d'auth** (l'ancien `CreateApiKey {login,password}` échouait) :
  - `/Api/CreateApiKey` → HTTP 422 « Guest account only » (réservé aux comptes invités)
  - `/Account/Login` → HTTP 404 « Unknown method » (n'existe pas en HAAPI v5)
  - Diagnostic via **DevTools sur l'émulateur** (`adb forward` + WebView debuggable, comme S4)
  - Vrai flux découvert : **OAuth2 PKCE** (`auth.ankama.com/token`) pour le bootstrap, puis
    **`RefreshApiKey` → `CreateToken`** pour chaque run. `haapi.py` réécrit en conséquence
    (`.env` : `DTV_APIKEY` + `DTV_REFRESH_TOKEN` au lieu de login/password, rotation auto via `set_key`).
- **Analyse méticuleuse de la capture har_3** (6,9 Mo, 451 entrées, 186 frames WS) :
  - `RefreshApiKey` : body `text/plain`, `game_id=18&refresh_token=…&long_life_token=1`
  - Réponse 13 champs : `key, account_id, …, refresh_token, expiration_date`
  - `CreateToken` → `{token:<uuid 36 chars>}` (48 octets), game_token jetable
  - **Aucune empreinte d'appareil dans tout le protocole** (scan exhaustif : zéro `deviceId`,
    `android_id`, `imei`, `safetynet`, `attestation`…) → Python reproduit le client à 100 %.
    Le seul signal « device/lieu » est l'**IP**. Réponse définitive à la question fingerprint.
  - `ObjectAveragePricesMessage` confirmé : `ids` (4908) + `avgPrices` (4908) parallèles
  - Séquence init jeu re-validée byte-for-byte (ClientKey 21 ch, SequenceNumber, GameContextCreate)
  - STICKER réel = base64 (`OUJ/6p9sxiOLdT/`), **même valeur sur les 2 WS** ; `_primuscb` = base64url
- **Corrections de code (poussées) :**
  - `haapi.py` : flux RefreshApiKey ; UA émulateur ; extraction de champs défensive (alias + erreur claire)
  - `connection.py` : `buildVersion` 1.72.11 → **1.72.12** ; STICKER session-stable + charset base64
  - `primus_client.py` : UA émulateur + `Accept-Language` ; **gestion frames string JSON**
  - `test_auth.py` / `test_login.py` / `collect.py` : env vars apikey/refresh_token + rotation auto
- **Tests live réussis :**
  - ✅ `test_auth` : RefreshApiKey + CreateToken OK ; **3 refresh consécutifs → même apikey**
    (long_life_token ne tourne pas → token réutilisable, résout la TODO `auto_reconnect`)
  - ✅ `test_login` : login flow **complet jusqu'à « game ready »** (perso Ramunda id 2310145, Talok 533)
  - **Bug trouvé + corrigé en live** : `"primus::server::open"` arrive en string JSON (absent des
    HAR car absorbé par le WebView) → crash `'str' object has no attribute 'get'` → géré.
  - ✅ **Le WebSocket Python (JA3 non-Chrome) connecte sans souci aux 2 serveurs** → le risque
    fingerprint WebSocket signalé depuis S3 est levé en pratique.
- **Prochaine étape : `collect --avg-prices-only` (première vraie collecte de données).**

### Session 6 (analyse approfondie 2 nouvelles captures + MAJ protocole)
- Analyse méticuleuse de **2 HAR** (har_1 07:50, har_2 08:41) : login + HDV + achat + gameplay/tuto
- Handshake game-server entièrement cartographié (44 trames d'init détaillées)
- **Découvertes protocole majeures :**
  - `SequenceNumberRequestMessage` → `SequenceNumberMessage{number:N++}` (anti-cheat, **on l'avait raté**)
  - `ClientKeyMessage{key:21 chars}` + `pingSession{nonce}` (parité client)
  - Version protocole **1595**, ping Primus **exactement 30s**
  - `buyerDescriptor` : 128 types + tax 3% + maxItemPerAccount 75 + unsoldDelay 672h
- **Comparaison des 2 snapshots `ObjectAveragePrices`** : 4906 items identiques, **115 prix changés
  en 51 min** → confirme que le prix moyen est dynamique (volume + récence), pas figé 24h
- **Code mis à jour :** SequenceNumber/ClientKey/pingSession dans `connection.py`,
  `economics` + `collect_resources()` dans `hdv.py`, nouveau `avg_prices.py`,
  `collect.py` (snapshot avg + flags `--avg-prices-only`/`--no-avg-prices`)
- **Nouveau doc `PROTOCOL.md`** : référence wire-level complète (3 captures)
- Recherche web : fonctionnement du prix moyen (devblog Ankama : achats marché + marchands,
  ~24h officiel mais en pratique plus dynamique, par serveur, formule non publiée)
- **Passe de validation (croisée sur 3 sessions) :**
  - ClientKey (21 chars), pingSession (9 chiffres), SequenceNumber (start 1, +1/conn) **validés**
  - **Bug d'empreinte trouvé + corrigé** : on envoyait `data:{}` partout ; le vrai client
    OMET `data` sur les messages sans argument → `send_message` corrigé (11/12 msgs match
    exact, LeaveDialog `null` vs omis = négligeable)
  - Invariants auth/anti-cheat cartographiés (`PROTOCOL.md` §9) : token/salt/key/STICKER/ticket
    = variables ; compte/serveur/versions/IP interne = constants ; `TrustStatus=true` partout
  - `SequenceNumberRequest` déclenché par actions de jeu, pas par le HDV en lecture
- **Passe robustesse (maintenance / MAJ / ban) :**
  - Détection maintenance : `ServersListMessage.status != 3` / `isSelectable` avant sélection
  - Détection MAJ : `ProtocolRequired.requiredVersion != 1595` + `IdentificationFailedForBadVersion`
  - Détection ban : `IdentificationFailedBanned` ; gestion file d'attente `QueueStatusMessage`
  - **Bug reconnexion corrigé** : le ticket est à usage unique → reconnexion = re-login complet ;
    défaut `auto_reconnect=False` (abandon propre, le scheduler relance)
  - `classify_error()` → codes de sortie collect.py (0 OK / 2 retry / 3 stop-humain / 1 inconnu)
  - **Nouveau doc `OPERATIONS.md`** (calendrier maintenance mardi ~8h-10h30 Paris, procédures)

### Session 5 (dictionnaire + types ressources)
- `/data/dictionary` non fetchable hors jeu (404) ; dico chargé en mémoire seulement
- `script.js` pull depuis l'AVD (5,2 Mo) → supertypes trouvés (`RESOURCE:9`, etc.)
- **`window.gui.databases.ItemTypes`** (console DevTools) → 64 types ressources extraits
- Découverte `ObjectAveragePricesGetMessage`/`ObjectAveragePricesMessage` dans script.js
- `item_types.py` créé (RESOURCE_TYPE_IDS + CORE), `collect.py` par défaut sur les ressources

### Session 11 (brisage : coefficient serveur, paliers de runes, observations)
- **Coefficient de brisage** ajouté : `revenu_réel = base × coeff/100` (coeff serveur
  1 %–4000 %, tend vers 1 % à chaque brisage, inconnu d'avance). **Coeff Min** =
  `coût/base×100` = seuil de rentabilité = métrique de décision (vérifié sur Tableau_Brisage).
  CLI `--coeff`, tri par défaut = Coeff Min croissant (pari le plus sûr).
- **Paliers de runes** encodés depuis les **noms exacts en jeu** (donnés par Flo) :
  9 stats à 3 paliers (simple/Pa/Ra), 21 à 2 (simple/Pa), 10 simple-only, 2 géant-only
  (Rune Ga Pa, Rune Ga Pme). `runes.json` enrichi (`nom_rune`, `tiers`, `giant_only`,
  `concassable`). `build_rune_gids.py` matche désormais sur le nom exact. Valuation
  par palier = future (manque prix par palier).
- **Observations** : `coefficient_reel` + `dernier_brisage` par item dans
  `brisage_observations.csv` (séparé du catalogue). CLI `--observations` : colonnes +
  coeff réel par item. Rempli à la main ; **auto-collecte serveur = TODO importante**.

### Session 10 (moteur de brisage + scraper consommables + fix effets dupliqués)

#### Moteur de brisage porté de RuneMaster → DTV (`docs/BRISAGE.md`)
- **RuneMaster décortiqué** : système manuel en 2 parties — (1) pipeline de prix
  (`fusion_releves_ressources.py` + relevés quotidiens manuels) que **DTV remplace**
  par la capture HDV live ; (2) moteur de brisage (`Tableau_Brisage` + formule +
  `poids_runes` + `effets_moyens_par_rune`).
- **Formule de brisage rétro-ingénierée** depuis `objets_runes_formule_modele.xlsx`
  (formule Excel lue cellule par cellule, pas devinée), **vérifiée au centième sur
  9 points** :
  ```
  par effet (rune R, valeur V, niveau N, poids P) :
    R ∈ {vi,ii,pod}: qty=(N/100)·V·P+1 ; sinon: qty=((N/100)·V·P+1)/P
  ```
  Le « +1 » = rune Ra de base ; division par P = pool de poids → compte de runes ;
  vi/ii/pod (poids <1) sans division.
- **Mapping effet→rune** (`dtv/data/runes.json`, 42 runes) dérivé en **croisant**
  `effets_moyens_par_rune.xlsx` avec le catalogue scrapé (vote majoritaire sur les
  valeurs) + convention Dofus pour les collisions (quatuor élémentaire).
- **L'upgrade clé** : RuneMaster exigeait la saisie manuelle des effets ET des prix.
  DTV prend les **effets du scraping** + les **prix du HDV live** → rentabilité de
  brisage sur **tout le catalogue (2825 items)**, zéro saisie.
- **Modules** : `dtv/collector/brisage.py` (moteur stdlib pur), `dtv/scripts/brisage.py`
  (CLI classement), `build_rune_gids.py` (code rune→GID pour prix live), `test_brisage.py`.
- Validé sur 2825 équipements : top brisage = boots/amulettes niv 200 (runes PA/PM
  les plus chères). Chemin coût/bénéfice/rentabilité testé.

#### Fix : effets dupliqués sur dofus-touch.com
- dofus-touch.com sert **2 panels « Effets »/« Caractéristiques » identiques** →
  les scrapers écrivaient chaque bloc 2× (**2773/2825 équipements**, idem conso).
  La condition (« PA < 12 ») fuitait aussi dans les Effets.
- **Corrigé** dans `DofusScrapper.py` + `scrape_consommables` (dédup `dict.fromkeys`
  + retrait des conditions des effets). Le moteur de brisage **déduplique aussi**
  les lignes identiques → robuste même sur un catalogue non nettoyé.
- **`clean_scraper_outputs.py`** : nettoie les fichiers DÉJÀ produits sans re-scraper
  (généralise aux 3 catalogues + toutes colonnes multi-valeurs, idempotent).
- Dédup défensive ajoutée à `scrap_ressources_full` + consommables (Recette/Drops/used-in).

#### Scraper consommables réécrit (`scrape_consommables_dofus_touch.py`)
- Architecture Phase1/Phase2 validée (comme ressources). Corrige les bugs de l'ancien :
  Niveau depuis listing (`td.item-level`), Type sans préfixe, GID depuis slug, checkpoint.
- Colonnes : Effets, Conditions, Recette, Utilise_dans, Drops_monstres (+ GID monstre + taux %).
- Structure confirmée via `debug_consommable.py` (drops dans `ak-aside`, used-in =
  « Est utilisé pour les recettes »). Le faible taux de drops/used-in sur la page 1
  était normal (consommables niv 200 = craftés, non droppés).

#### Capture passive émulateur + bug prix moyens = 1
- Le client officiel envoie `ObjectAveragePricesGetMessage` tout seul après login →
  `capture_phone.py` le capte passivement (trafic 100 % légitime). Procédure émulateur
  Android Studio ajoutée au docstring (`docs/POWERSHELL.md`).
- **Hypothèse bug « tous les prix moyens à 1 »** : l'approche active envoyait la requête
  trop tôt (avant d'être pleinement in-world). Diagnostic : CSV trié par GID, les vieux
  items sont à 1 kama légitimement (vérifier `>1` et `max`). La voie passive (client
  officiel) donne le bon timing.

### Session 9 (DofusToolsFlo intégration + scrapers réécrits)

#### IndexedDB `enDataCache` — stores confirmés
Accessible via ADB → CDP port forwarding (`webview_devtools_remote_<pid>`, **pas** `chrome_devtools_remote`).
`Runtime.evaluate` avec `awaitPromise=True` pour lire les IDBStores asynchrones.

| Store | Count | Contenu |
|---|---|---|
| `Items` | 840+ (grandit lazy pendant le jeu) | `nameId`, `typeId`, prix PNJ, … |
| `ItemTypes` | 236 | ID → nom du type (Épée, Cape, Ressource végétale…) |
| `Recipes` | 21+ | `resultId`, `ingredientIds`, `quantities` |
| `BidHouseCategories` | 23 | |
| `ItemSets` | nombreux | panoplies |
| `Jobs` | nombreux | métiers |
| `UniqueDrops` | données de drops | |
| `AbuseReasons` | count=0 | Raisons de signalement joueur — **pas un compteur anti-triche** |

`AbuseReasons` (count=0) = store de raisons de signalement ("comportement abusif") → vide parce que non utilisé côté client. Rien à voir avec les détections anti-triche.

**`dump_item_names.py`** (`dtv/scripts/`) — sweep des stores `Items` + `ItemTypes`, produit :
- `data/item_names.json` : `{gid → {nameId, typeId}}`
- `data/item_types_by_gid.json` : `{gid → typeId}`
- `data/item_type_names.json` : `{typeId → nom_type}`

#### Vérification GIDs — quelle source utiliser ?

| Source | IDs | Vérification |
|---|---|---|
| `dofus-touch.com` URLs | **GIDs réels** ✅ | Recette IndexedDB `[312,285]` = Fer+Farine bise sur le site |
| `api.dofusdb.fr` | **GIDs réels** ✅ | Même espace d'IDs, retourne FR+EN dans le même appel |
| `dofusbook.net` | **IDs internes** ❌ | "Bottes de Bowisse" = 25 sur dofusbook, 127 en jeu |

Extraction GID depuis slug URL : `re.search(r'/encyclopedie/[\w-]+/(\d+)-', url).group(1)`

**Conséquence** : les fichiers `equipements_dofus_touch_complets.xlsx` et `armes_dofus_touch.xlsx`
générés par l'ancienne version de `DofusScrapper.py` (source dofusbook.net) ont des IDs FAUX.
→ Les remplacer par le run de la nouvelle version (source dofus-touch.com).

`api.dofusdb.fr` bloqué depuis le cloud (proxy 403) — utiliser uniquement depuis le PC de Flo.

#### DofusToolsFlo = DTV v0 (système manuel)

Dossier `DofusToolsFlo/` dans le repo = version manuelle construite ~1 an avant DTV.

**DofScraper** (`DofusScrapper/`) :
- Scripte le même travail que `capture_phone.py` (relevés HDV) mais de façon statique (Excel manuel)
- Scrapers HTML pour resources, consommables, équipements, armes, recettes
- `scrap_ressources_full.py` (nouveau) + `DofusScrapper.py` (réécrit) = versions complètes avec GIDs

**RuneMaster** (`RuneMaster/`) :
- Suivi de prix par catégorie (`Releves/Suivis_par_categorie/`) → même schéma que DTV CSV
  (Nom | Type | Niveau | Prix x1 | x10 | x100 | x1000 | Prix Moyen | Prix Min | Prix Max | Date | Heure)
- `DataCrossing/fusion_releves_ressources.py` : aggrège N relevés quotidiens (historique + courant)
- `Tableau_Brisage_Dofus_Resume.xlsx` : moteur de calcul de brisage (56 colonnes)
- `poids_runes.xlsx` : 43 runes avec leurs poids (ag=1, cc=10, chs=3, daf=5…)
- `effets_moyens_par_rune.xlsx` : rendement moyen par rune et par item → calcul break-even

#### Scrapers — stratégie par source

| Donnée | Source recommandée | Script |
|---|---|---|
| Ressources (GID, nom FR/EN, recette, drops) | `dofus-touch.com` HTML | `scrap_ressources_full.py` |
| Équipements + armes (GID, effets, recette) | `dofus-touch.com` HTML | `DofusScrapper.py` (réécrit) |
| Consommables | `dofus-touch.com` HTML | `scrape_consommables_dofus_touch.py` |
| Noms EN depuis API | `api.dofusdb.fr` | `scrap_ingredients_dofusdb_api_mt_final.py` (PC uniquement) |
| Noms EN depuis jeu | IndexedDB `enDataCache` | `dump_item_names.py` |
| Prix live HDV | Protocole jeu WS | `capture_phone.py` / `collect.py` |

#### Sécurité — valeurs à ne JAMAIS committer

Les valeurs suivantes doivent rester dans `.env` uniquement, **jamais** dans le repo :
- `localStorage.HAAPI_KEY`
- `localStorage.HAAPI_REFRESH_TOKEN`
- `localStorage.HAAPI_ACCOUNTID`
- `localStorage.UNIQUE_NICKNAME`

#### Résultats des scrapers (session 9 — runs complets)

| Fichier | Items | Notes |
|---|---|---|
| `ressources_dofus_touch_full.json/.xlsx` | **1861** | 526 craftables, 1224 utilisés en recettes, 933 avec drops monstres |
| `equipements_dofus_touch_full.json/.xlsx` | **2825** | 2772 avec effets, 2260 craftables, 1062 en panoplies |

#### Items 404 permanents — à vérifier en jeu

`retry_failed.py` a confirmé 9 items définitivement absents du site dofus-touch.com mais présents dans le listing.
Leurs données listing (GID + Nom_FR + Niveau + Lien) sont **préservées** dans les JSON/Excel.
Les champs détail (Effets, Recette, etc.) sont vides.

**⚠️ TODO : vérifier ces items directement en jeu pour savoir s'ils existent encore.**

| # | GID | Nom_FR | Catégorie |
|---|---|---|---|
| 1 | 14002 | *(à vérifier)* | équipements |
| 2 | 8123 | *(à vérifier)* | équipements |
| 3 | 8126 | *(à vérifier)* | équipements |
| 4 | 15617 | *(à vérifier)* | équipements |
| 5 | 11747 | *(à vérifier)* | équipements |
| 6 | 11633 | *(à vérifier)* | équipements |
| 7 | 8097 | *(à vérifier)* | équipements |
| 8 | 6661 | *(à vérifier)* | équipements |
| 9 | 2000 | *(à vérifier)* | ressources |

Si l'item existe en jeu : récupérer ses stats via l'encyclopédie in-game et compléter manuellement.
Si supprimé : garder la ligne mais exclure du tableau farming (colonne `actif=false` à ajouter si besoin).

#### Nouveaux scripts (session 9)

| Script | Emplacement | Rôle |
|---|---|---|
| `extract_gids.py` | `DofScraper/DofusScrapper/DofusScrapper/` | Extrait GIDs depuis slugs URL des Excel existants |
| `scrap_ressources_full.py` | id. | Scrape complet ressources (GID, FR/EN, recette, drops monstres) |
| `DofusScrapper.py` | id. | Réécrit pour équipements+armes depuis dofus-touch.com (GIDs corrects) |
| `retry_failed.py` | id. | Backfill des items en erreur (réseau transitoire vs 404 définitif) |

---

### Session 8 (IndexedDB discovery + DofusToolsFlo pull)
- Dump IndexedDB `enDataCache` via CDP : stores `Items`, `ItemTypes`, `Recipes`, `BidHouseCategories`
- `AbuseReasons` (count=0) = signalement joueur, pas anti-triche
- `dump_item_names.py` réécrit pour sweep CDP + sauvegarde 3 fichiers JSON
- `item_names.py` collector enrichi (`load_gid_types()`, `load_type_names()`)
- `analyze.py` mis à jour pour utiliser les labels `ItemTypes` live (priorité sur la map PC statique)
- Analyse de DofusToolsFlo : scrapers dofusbook.net ont des IDs faux ❌ ; scrapers dofus-touch.com ont des GIDs corrects ✅
- Confirmation croisée GID via recette IndexedDB ([312,285] = Fer+Farine bise)
- `DofusToolsFlo` intégré dans la branche de travail via `git checkout origin/main -- DofusToolsFlo/`

### Session 1 (exploration)
- Analyse de LaBot, pydofus2, otomat
- Découverte architecture réseau (2 canaux)
- Découverte Primus/JSON (pas binaire DofusProtocol)
- Auth HAAPI documentée (GAME_ID=18)

### Session 2 (setup + code)
- Extraction de `script.js` depuis AVD via adb
- Confirmation protocole JSON Primus depuis script.js
- Code de base écrit et pushé sur Ti-flo/Dtv
- Analyse ban du compte #1 (WireGuard + PCAPdroid + mitmproxy simultanément)

### Session 4 (premier test live + capture protocole complète)
- Niveau HDV confirmé : **10** (accessible dès niveau 10, peu importe la map)
- AVD relancé, DNS fixé (`setprop net.dns1 8.8.8.8`)
- Throwaway account créé (Ramundoh#8708, accountId 188926644), tuto complété
- **WebView debuggable !** Capture via `chrome://inspect` + port forwarding
  (`adb forward tcp:9222 localabstract:webview_devtools_remote_<pid>`)
  → AUCUNE modif de script.js nécessaire (patch_scriptjs.py reste en réserve)
- HAR capturé : login flow complet + HDV (ouverture, consultation, achat, fermeture)
- **Protocole entièrement confirmé et code réécrit en conséquence :**
  - Login : `connecting` (sans token) → `login` (username=accountId + token + salt + key echo)
  - `SelectedServerDataMessage._access` = host game server (pas `address`)
  - HDV en 2 étapes (ExchangeBidHouseTypeMessage → ExchangeBidHouseListMessage)
  - quantities = [1,10,100,1000]
- Bugs corrigés : `wait_for_game()` faux succès, send lock WebSocket, SELinux restorecon
- Prochaine étape : tester le code réécrit contre le serveur réel

### Session 3 (analyse + corrections protocole)
- Analyse statique de `script.js` → protocole HDV entièrement corrigé
  - `NpcGenericActionRequestMessage` (pas `ExchangePlayerRequestMessage`) pour ouvrir l'HDV
  - `ExchangeBidHouseTypeMessage` (pas `ExchangeTypeItemsExchangerDescriptionForUserMessage`) pour demander les prix
  - Champs réponse : `objectUID`, `prices:[p1,p10,p100]`, `effects`, `tutorialPrice`
  - `objectGID` absent de la réponse serveur (déduit par le client)
  - L'HDV est accessible depuis n'importe où (pas besoin d'être près d'un PNJ)
  - Quantités dynamiques depuis `buyerDescriptor.quantities` (x1000 possible)
- curl_cffi + chrome_android pour fingerprint TLS HAAPI
- Reconnexion avec circuit breaker (4 cas : CLIENT/SERVER/PING_TIMEOUT/TCP_DROP)
- Timing utilities (human_delay, backoff_delay avec jitter)
- KNOWLEDGE.md créé et maintenu
