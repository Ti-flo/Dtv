# DTV — Base de connaissances technique

> Fichier de référence à compléter au fil des sessions.
> Toutes les découvertes confirmées par captures réseau, analyse de code ou tests.

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

### Flux d'authentification complet

```
1. POST haapi.ankama.com/json/Ankama/v5/Api/CreateApiKey
   Body: {login, password, long_life_token: false, game: 18}
   → Retourne: {key: "...", account_id: ...}

2. GET haapi.ankama.com/json/Ankama/v5/Game/CreateToken?game=18
   Header: apikey: <key>
   → Retourne: {token: "..."}  ← c'est le game_token

3. WebSocket wss://dt-proxy-production-login.ankama-games.com/???
   Primus protocol, JSON messages
   → send "connecting" → reçoit HelloConnectMessage
   → send "login" avec token + salt + key
   → reçoit ServersListMessage
   → send ServerSelectionMessage {serverId: N}
   → reçoit SelectedServerDataMessage (avec URL du game server)

4. WebSocket wss://<game-server>/???
   → reçoit HelloGameMessage
   → send AuthenticationTicketMessage {ticket, lang}
   → reçoit AuthenticationTicketAcceptedMessage
   → send CharactersListRequestMessage
   → reçoit CharactersListMessage
   → send CharacterSelectionMessage {id}
   → reçoit GameContextCreateMessage ← SESSION PRÊTE
```

**TODO :** Confirmer le chemin exact du WebSocket Primus (probablement `/primus`).
Pour le trouver : `GET https://dt-proxy-production-login.ankama-games.com/build/primus.js`

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

### HDV — architecture (confirmé par analyse statique de script.js)

**L'HDV dans Dofus Touch est accessible depuis n'importe où** (bouton dans l'interface),
pas besoin d'être près d'un PNJ physique. Niveau min confirmé : **10** (confirmé en jeu session 4).

#### Messages HDV (confirmés script.js)

| Message | Sens | Rôle |
|---|---|---|
| `NpcGenericActionRequestMessage` | → | **Ouvrir HDV** (`npcId:0, npcActionId:6, npcMapId:<mapId>`) |
| `ExchangeStartedBidBuyerMessage` | ← | HDV ouvert (mode achat) — contient `buyerDescriptor` |
| `ExchangeStartedBidSellerMessage` | ← | HDV ouvert (mode vente) |
| `ExchangeBidHouseTypeMessage` | → | **Demander les offres d'un type d'item** (`{type: <gid>}`) |
| `ExchangeTypesItemsExchangerDescriptionForUserMessage` | ← | Réponse avec toutes les offres |
| `LeaveDialogRequestMessage` | → | Fermer HDV |
| `ExchangeLeaveMessage` | ← | HDV fermé |

**Paramètres de `NpcGenericActionRequestMessage` pour l'HDV :**
```json
{ "npcId": 0, "npcActionId": 6, "npcMapId": <mapId_actuel_du_joueur> }
```
- `npcActionId: 6` = mode achat (lecture des prix)
- `npcActionId: 5` = mode vente/modification
- `npcMapId` = `CurrentMapMessage.mapId` — la map actuelle du joueur
- Référence : `openBidHouse()` dans script.js

**Comparaison : banque ouvre avec `npcMapId: -1`** → à tester si -1 fonctionne pour l'HDV aussi.

#### Format de `ExchangeTypesItemsExchangerDescriptionForUserMessage` (confirmé script.js)

```json
{
  "_messageType": "ExchangeTypesItemsExchangerDescriptionForUserMessage",
  "itemTypeDescriptions": [
    {
      "objectUID":    12345,
      "prices":       [100, 950, 9000],
      "effects":      [{"_type": "ObjectEffectInteger", "actionId": 110, "value": 100}],
      "tutorialPrice": false
    }
  ]
}
```

**Points clés :**
- `objectUID` = identifiant unique de cette offre (pas du type d'item)
- `prices[0]` = prix total pour 1 unité, `prices[1]` = pour 10, `prices[2]` = pour 100
- `prices` indexé sur `buyerDescriptor.quantities` (= `[1, 10, 100]` standard Dofus)
- `objectGID` n'est **pas** dans la réponse serveur — le client le déduit du type demandé
- Exemple tutoriel : `prices: [90, 0, 0]` → confirme que 0 = pas d'offre à cette quantité
- Source : `_addItemListChunk()` + `_separateItemBulks()` dans script.js

#### `buyerDescriptor` dans `ExchangeStartedBidBuyerMessage`
- `buyerDescriptor.types` = liste des types d'items disponibles dans l'HDV du serveur
- `buyerDescriptor.quantities` = tiers de quantité (standard `[1, 10, 100]`)

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
| `dtv/collector/haapi.py` | ✅ Prêt | curl_cffi + chrome_android impersonation |
| `dtv/collector/primus_client.py` | ✅ Prêt | DisconnectReason, heartbeat watchdog, circuit breaker |
| `dtv/collector/connection.py` | ✅ Prêt | Login flow complet, reconnexion auto, map_id tracking |
| `dtv/collector/hdv.py` | ✅ Prêt | Messages corrigés depuis script.js, prix dynamiques |
| `dtv/collector/timing.py` | ✅ Prêt | human_delay, jitter, backoff_delay |
| `dtv/scripts/test_auth.py` | ✅ Prêt | Test HAAPI isolé |
| `dtv/scripts/test_connect.py` | ✅ Prêt | Test WebSocket connectivité |
| `dtv/scripts/test_login.py` | ✅ Prêt | Test login flow complet |
| `dtv/scripts/collect.py` | ✅ Prêt | Pipeline collecte production |

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

### Ce qu'on apprendra au premier test live

- Le vrai chemin Primus (`/primus` est supposé — peut être `/` ou autre)
- Les IDs de serveurs Dofus Touch (dans `ServersListMessage`)
- Si `npcMapId: -1` fonctionne pour ouvrir l'HDV ou si le vrai mapId est requis
- Les vrais tiers de quantités (`buyerDescriptor.quantities` → `[1,10,100]` ou `[1,10,100,1000]`)
- La structure exacte de `SelectedServerDataMessage`

### Ce qui reste à investiguer (non bloquant pour le premier test)

- Fingerprint TLS du WebSocket : `websocket-client` a un JA3 différent d'Android. Migrer vers `curl_cffi.requests.ws_connect` si des bans surviennent sans autre cause.
- Logstash/Firebase télémétrie : absence non simulée. Risque faible à court terme.
- Frida sur AVD : Ankama Shield détecte frida-server. Pistes : renommer le binaire, le mettre hors de `/data/local/tmp/`, ou hooker la WebSocket au niveau JS (plus discret sur Cordova).

---

## 📋 TODO / Inconnues à résoudre

- [ ] Confirmer le chemin exact du WebSocket Primus (`/primus` ?)
  → `test_connect.py` le révélera au premier run
- [ ] Trouver les IDs de serveurs Dofus Touch
  → `ServersListMessage` loggé automatiquement dans `test_login.py`
- [ ] Confirmer `npcMapId` pour l'ouverture HDV (-1 suffit ?)
  → `test_login.py` + collecte manuelle
- [ ] Confirmer le format de `SelectedServerDataMessage` (URL complète ou host/port ?)
  → `test_login.py` logge le message brut
- [ ] Vérifier les tiers de quantités réels (`[1,10,100]` ou `[1,10,100,1000]`)
  → `ExchangeStartedBidBuyerMessage.buyerDescriptor.quantities` loggé à l'ouverture HDV
- [ ] Tester si l'absence de Logstash/Firebase est détectée sur plusieurs jours
- [ ] Fingerprint TLS WebSocket — tester curl_cffi ws_connect si bans inexpliqués

---

## 📝 Historique des sessions

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

### Session 4 (premier test live + outils capture)
- Niveau HDV confirmé : **10** (accessible dès niveau 10, peu importe la map)
- AVD relancé, DNS fixé (`setprop net.dns1 8.8.8.8`)
- Throwaway account créé, tuto complété, HDV accessible
- Outils de capture créés : `ws_intercept.js`, `patch_scriptjs.py`, `ws_capture_server.py`
- Bugs corrigés : `wait_for_game()` faux succès, send lock WebSocket, SELinux restorecon
- Prochaine étape : sonder WebView debuggable, puis patch script.js si nécessaire

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
