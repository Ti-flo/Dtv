# DTV — Base de connaissances technique

> Fichier de référence à compléter au fil des sessions.
> Toutes les découvertes confirmées par captures réseau, analyse de code ou tests.
>
> 📖 **Référence wire-level complète du protocole : [`PROTOCOL.md`](PROTOCOL.md)**
> (séquences exactes confirmées sur 3 captures HAR, catalogue des messages, formats).
> Ce fichier-ci reste la vue d'ensemble (architecture, sécurité, état du projet).

---

## 🏗️ Architecture réseau de Dofus Touch

### Canaux de communication (confirmé PCAPdroid + mitmproxy)

| Domaine | IP | Proto | Rôle |
|---|---|---|---|
| `haapi.ankama.com` | 3.174.255.11 | HTTPS | Auth (login/password → api_key → game_token) |
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

### Flux d'authentification complet — ✅ CONFIRMÉ PAR CAPTURE LIVE (session 4, HAR DevTools)

```
1. POST haapi.ankama.com/json/Ankama/v5/Api/CreateApiKey
   Body: {login, password, long_life_token: false, game: 18}
   → Retourne: {key: "...", account_id: ...}

2. GET haapi.ankama.com/json/Ankama/v5/Account/CreateToken?game=18   ← "Account" PAS "Game"
   Header: apikey: <key>
   → Retourne: {token: "..."}  ← game_token au format UUID (ex: 75692171-4b20-4b07-91e1-d773ec66a4cf)
   ⚠️ La capture live montre "Account/CreateToken", pas "Game/CreateToken". À tester.

3. WebSocket wss://dt-proxy-production-login.ankama-games.com/primus?STICKER=<id>&_primuscb=<cb>
   ✅ Chemin = /primus CONFIRMÉ
   STICKER = id de session généré côté client par Primus (même valeur pour les 2 WS).
            Sticky-session du load balancer. À tester si omettable.

   → send "connecting": {language:"en", server:"login", client:"android",
                         appVersion:"3.11.0", buildVersion:"1.72.11"}   ← PAS de token ici !
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
                         appVersion:"3.11.0", buildVersion:"1.72.11"}
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

### Headers Android requis (confirmé capture.har)

```
User-Agent: Mozilla/5.0 (Linux; Android 9; SM-S908E Build/TP1A.220624.014; wv)
            AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/129.0.6668.70
            Safari/537.36 DofusTouch Client 3.11.0
sec-ch-ua: "Android WebView";v="129", "Not=A?Brand";v="8", "Chromium";v="129"
sec-ch-ua-mobile: ?0
sec-ch-ua-platform: "Android"
x-requested-with: com.ankama.dofustouch
```

---

## 🛡️ Système de détection Ankama

### Niveau réseau (côté serveur)

**1. IP reputation — risque le plus élevé**
- IPs datacenter, VPN, proxy → ban quasi-immédiat
- Ankama bloque activement les plages IP des fournisseurs VPN connus
- **Règle absolue : IP résidentielle uniquement en production**
- Un compte a déjà été banni à cause de WireGuard (VPN datacenter) actif pendant les tests

**2. TLS fingerprinting (JA3/JA4)**
- Ankama utilise probablement Cloudflare (confirmé sur `haapi.ankama.com`) qui fait du JA3 fingerprinting natif
- Un client Python standard (`requests`/`websocket-client`) a un JA3 hash complètement différent d'un Android WebView Chrome 129
- **Solution : `curl_cffi` avec `impersonate="chrome_android"` pour HAAPI**
- Le WebSocket Primus reste un vecteur de fingerprinting (à surveiller)

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

---

## ⚠️ Règles de sécurité opérationnelles

```
JAMAIS le vrai compte Flo
JAMAIS un VPN datacenter (WireGuard, NordVPN, ExpressVPN...)
JAMAIS mitmproxy actif pendant une session de collecte réelle
Max 4 comptes par IP/serveur
IP résidentielle uniquement en production
Compte Gmail jetable créé depuis l'IP de production (pas depuis VPN)
Ankama bloque Protonmail à l'inscription
```

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
| `dtv/collector/haapi.py` | ✅ Réécrit S4 | `authenticate()` → (account_id, token), endpoint Account/CreateToken |
| `dtv/collector/primus_client.py` | ✅ Prêt | DisconnectReason, heartbeat watchdog (30s ping), send lock |
| `dtv/collector/connection.py` | ✅ MAJ S6 | Login flow live + **SequenceNumber, ClientKey, pingSession** |
| `dtv/collector/hdv.py` | ✅ MAJ S6 | Flow HDV 2 étapes + `collect_resources()` + `economics` |
| `dtv/collector/avg_prices.py` | ✅ Nouveau S6 | **Snapshot prix moyens (~4900 items / message)** |
| `dtv/collector/item_types.py` | ✅ Nouveau S5 | 64 types ressources (superTypeId=9) + 41 core |
| `dtv/collector/timing.py` | ✅ Prêt | human_delay, jitter, backoff_delay |
| `dtv/scripts/test_auth.py` | ✅ Prêt | Test HAAPI isolé |
| `dtv/scripts/test_connect.py` | ✅ Prêt | Test WebSocket connectivité |
| `dtv/scripts/test_login.py` | ✅ Prêt | Test login flow complet |
| `dtv/scripts/collect.py` | ✅ MAJ S6 | Pipeline : avg-prices + HDV ressources (défaut: core) |

### Prochaine étape immédiate : premier test live

```
# 1. Installer les dépendances
pip install -r requirements.txt

# 2. Tester l'auth HAAPI (compte jetable, IP résidentielle, PAS de VPN)
set DTV_LOGIN=compte_jetable@gmail.com
set DTV_PASSWORD=motdepasse
python -m dtv.scripts.test_auth

# 3. Si auth OK → tester la connexion WebSocket
python -m dtv.scripts.test_connect

# 4. Si WebSocket OK → tester le login complet
set DTV_SERVER_ID=<id_serveur>   # découvert à l'étape 3 via ServersListMessage
python -m dtv.scripts.test_login

# 5. Si login OK → tester la collecte HDV
python -m dtv.scripts.collect
```

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

### Ce qui reste à investiguer

- Le paramètre `STICKER` est-il requis ? (généré côté client — tester sans)
- Endpoint token : `Account/CreateToken` **confirmé live** (3 captures) ; `Game/CreateToken` abandonné
- Fingerprint TLS du WebSocket : `websocket-client` a un JA3 différent d'Android. Migrer vers `curl_cffi.requests.ws_connect` si bans inexpliqués.
- Logstash télémétrie : confirmée active (config.json `mediatorUrl`). Absence non simulée par notre client. Risque faible à court terme.
- Fréquence exacte de rafraîchissement du prix moyen (semble continu/au fil des ventes, pas 24h)

---

## 📋 TODO / Inconnues à résoudre

- [ ] **Tester le code MAJ (S6) contre le serveur réel** — login flow + SequenceNumber + avg-prices
- [ ] Mesurer la durée d'un run `--avg-prices-only` (1 message) vs collecte HDP ressources complète
- [ ] Tester si `STICKER` est omettable dans l'URL Primus
- [ ] Tester si l'absence de Logstash est détectée sur plusieurs jours
- [ ] Fingerprint TLS WebSocket — tester curl_cffi ws_connect si bans inexpliqués
- [ ] Watchlist / pruning : retirer les items dont le prix ne bouge jamais (après quelques jours de données)
- [ ] Scheduler multi-comptes : rotation horaires + rotation des types consultés (anti-pattern)
- [ ] Calcul de rentabilité « brisage » : croiser prix ressources (avg) avec recettes de craft

---

## 📝 Historique des sessions

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

### Session 5 (dictionnaire + types ressources)
- `/data/dictionary` non fetchable hors jeu (404) ; dico chargé en mémoire seulement
- `script.js` pull depuis l'AVD (5,2 Mo) → supertypes trouvés (`RESOURCE:9`, etc.)
- **`window.gui.databases.ItemTypes`** (console DevTools) → 64 types ressources extraits
- Découverte `ObjectAveragePricesGetMessage`/`ObjectAveragePricesMessage` dans script.js
- `item_types.py` créé (RESOURCE_TYPE_IDS + CORE), `collect.py` par défaut sur les ressources

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
