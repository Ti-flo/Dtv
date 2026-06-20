# DTV — Référence du protocole Dofus Touch (wire-level)

> Référence technique complète du protocole, confirmée frame par frame sur
> **3 captures HAR réelles** (DevTools WebView, sessions 4–6, juin 2026).
> Chaque séquence ci-dessous a été observée en live, pas déduite de `script.js`.
>
> Captures analysées :
> - `0e24427b` — login + HDV (session 4)
> - `har_1` (`6c60608e`) — login + HDV + achat (session 6, 07:50 UTC)
> - `har_2` (`20a12e4a`) — login + gameplay/tuto + level-up (session 6, 08:41 UTC)

---

## 1. Transport

- **Primus** (framework WebSocket) sur `wss://…/primus?STICKER=<id>&_primuscb=<cb>`
- Messages **JSON** (pas de binaire DofusProtocol)
- **Version protocole : 1595** (`ProtocolRequired.requiredVersion`, identique login + game)
- Build client : `appVersion=3.11.0`, `buildVersion=1.72.11`

### Format des trames

| Sens | Format |
|---|---|
| Client → serveur (standard) | `{"call":"sendMessage","data":{"type":"<Name>","data":{…}}}` |
| Client → serveur (calls spéciaux) | `{"call":"<name>","data":<payload>}` |
| Serveur → client | `{"_messageType":"<Name>", …champs}` |

**Calls spéciaux** (hors `sendMessage`) observés :
`connecting`, `login`, `disconnecting`, `pingSession`, `moneyGoultinesAmountRequest`,
`arenaPlayerRank`, `bakSoftToHardCurrentRateRequest`, `bakHardToSoftCurrentRateRequest`,
`restoreMysteryBox`.

### Heartbeat Primus (niveau transport)

```
← "primus::ping::1781941855035"     (string brute, pas du JSON)
→ "primus::pong::1781941855035"     (renvoyer le même timestamp)
```

- **Intervalle serveur : exactement 30,0 s** (mesuré sur les 2 captures)
- 2 pings ratés (~65 s sans ping) → considérer la connexion morte
- `"primus::server::close"` = fermeture serveur (kick/maintenance) → ne PAS reconnecter

---

## 2. Serveur de login — séquence complète

Toutes les trames, dans l'ordre, identiques entre les 3 captures :

```
→ connecting   {language:"en", server:"login", client:"android",
                appVersion:"3.11.0", buildVersion:"1.72.11"}          ← AUCUN token
← ProtocolRequired   {requiredVersion:1595, currentVersion:1595}
← HelloConnectMessage   {salt:"<32 chars>", key:[<~340 bytes signés>]}
→ login   {username:"188926644", token:"<UUID>",
           salt:"<echo>", key:[<echo>]}                              ← username = accountId
← CredentialsAcknowledgementMessage
← IdentificationSuccessMessage   {login, nickname, accountId, …}
← ServersListMessage   {servers:[…]}
→ sendMessage:ServerSelectionMessage   {serverId:533}
← SelectedServerDataMessage   {serverId, address, port, ticket, _access}
→ disconnecting   "SWITCHING_TO_GAME"
← "primus::server::close"
```

### Détails confirmés

- **`token`** = UUID régénéré à chaque auth (`aa1aabfb-fad2-48a2-902d-07f4bf220e9b`,
  puis `dd9d46e0-a3cd-4fb0-8667-7830c7cfdadb`). C'est le `game_token` de HAAPI.
- **`username` = `accountId`** (entier `188926644`), pas l'email.
- **`salt` / `key`** du `HelloConnectMessage` sont **réémis tels quels** dans `login`.
- **`IdentificationSuccessMessage.login`** change à chaque session
  (`244588170536342810` → `…418256`) — id de session, à ne pas stocker.
- **`SelectedServerDataMessage`** :
  - `address` = **IP interne AWS** `172.29.2.186` → **inutilisable**, ne pas router dessus
  - `port` = `5555`
  - `ticket` = jeton à usage unique pour le serveur de jeu (change à chaque session)
  - **`_access`** = `https://dt-proxy-production-canada.ankama-games.com` = **le vrai host** du game server
- Un `primus::ping/pong` peut s'intercaler n'importe où (vu dans har_1 pendant la sélection).

### Liste des serveurs (compte test, région canada)

| id | nom | status | sélectionnable | persos |
|---|---|---|---|---|
| 530 | Tiliwan | 3 | oui | 0 |
| 531 | Kelerog | 3 | oui | 0 |
| 532 | Blair | 3 | oui | 0 |
| **533** | **Talok** | 3 | oui | **1** ← compte test |
| 411 | Tournament | 3 | oui | 0 |

`DTV_SERVER_ID=533` (Talok). Le proxy régional (`_access`) est *canada* — ne jamais
coder le host en dur, toujours lire `_access`.

---

## 3. Serveur de jeu — handshake complet

Séquence confirmée (numéros = ordre des trames dans har_1) :

```
 0 → connecting   {language:"en", server:{address:"172.29.2.186", port:5555, id:533},
                   client:"android", appVersion:"3.11.0", buildVersion:"1.72.11"}
 1 ← ProtocolRequired   {requiredVersion:1595}
 2 ← HelloGameMessage   {}
 3 → sendMessage:AuthenticationTicketMessage   {ticket:"<ticket de SelectedServerData>", lang:"en"}
 4 ← BasicAckMessage   {seq:0, lastPacketId:110}
 8 ← AuthenticationTicketAcceptedMessage          ← auth OK
…  ← (flot d'init : ServerSettings, ServerBonus, AccountCapabilities, …)
15 → pingSession   236963397                       ← call spécial (nonce ~9 chiffres)
17 → sendMessage:CharactersListRequestMessage   {}
22 ← CharactersListMessage   {characters:[{id:2310145, level:15, name:"Ramunda", breed:8, …}]}
23 → sendMessage:CharacterSelectionMessage   {id:2310145}
29 ← CharacterSelectedSuccessMessage   {infos:{…}}
…  → (housekeeping optionnel : QuestListRequest, FriendsGetList, IgnoredGetList, …)
40 → sendMessage:ClientKeyMessage   {key:"PDuuqm1KTSNERoaRQVEp2"}   ← clé aléatoire 21 chars
41 → sendMessage:GameContextCreateRequestMessage   {}
59 ← SequenceNumberRequestMessage   {}
60 → sendMessage:SequenceNumberMessage   {number:1}    ← compteur incrémental
…  ← GameContextCreateMessage, CurrentMapMessage {mapId}, MapComplementaryInformationsDataMessage, …
```

### Étapes REQUISES (serveur-enforced)

1. `connecting` → `ProtocolRequired` + `HelloGameMessage`
2. `AuthenticationTicketMessage{ticket}` → `AuthenticationTicketAcceptedMessage`
3. `CharactersListRequestMessage` → `CharactersListMessage`
4. `CharacterSelectionMessage{id}` → `CharacterSelectedSuccessMessage`
5. `GameContextCreateRequestMessage` → `GameContextCreateMessage` (+ map data)
6. **Répondre à `SequenceNumberRequestMessage`** par `SequenceNumberMessage{number:++}`

### Étapes de parité client (recommandées anti-fingerprint, non bloquantes)

- `pingSession <nonce>` après l'acceptation du ticket
- `ClientKeyMessage{key:<21 alphanum aléatoires>}` juste avant `GameContextCreateRequestMessage`
  (clés live : `PDuuqm1KTSNERoaRQVEp2`, `2w8S8tox7sPIHcJ9fqoH6` — une par connexion)

### Anti-cheat : SequenceNumber

- Le **serveur** envoie `SequenceNumberRequestMessage` (vide) quand il veut.
- Le client répond `SequenceNumberMessage{number:N}` avec **N incrémental par connexion**
  (`1`, puis `2`… — har_2 : trame 60 → number 1, trame 511 → number 2).
- Le compteur **repart à 0/1 à chaque (re)connexion**.
- ⚠️ Ne PAS ignorer : une session qui ne répond jamais paraît anormale.

### Keepalives applicatifs (≠ ping Primus)

| Message | Sens | Rôle | Action requise |
|---|---|---|---|
| `BasicAckMessage` `{seq, lastPacketId}` | ← | accusé serveur des paquets client | aucune (informatif) |
| `BasicNoOperationMessage` | ← | no-op serveur (souvent juste après un Ack) | aucune |
| `BasicPingMessage` `{quiet:true}` | → | mesure de latence (client) | optionnel |
| `BasicPongMessage` `{quiet:true}` | ← | réponse au BasicPing | — |
| `BasicTimeMessage` `{timestamp, timezoneOffset}` | ← | horloge serveur | aucune |
| `BasicLatencyStatsRequestMessage` | ← | demande de stats latence | optionnel (`BasicLatencyStatsMessage`) |

`BasicAckMessage.seq` s'incrémente (0,1,2,…) ; `lastPacketId` est le compteur de
paquets serveur. Purement informatif côté client.

---

## 4. Prix moyens — `ObjectAveragePrices` ⭐

**Snapshot marché complet en un seul message.** Le client le demande pendant l'init.

```
→ sendMessage:ObjectAveragePricesGetMessage   {}          ← aucun paramètre
← ObjectAveragePricesMessage   {ids:[…], avgPrices:[…]}    ← 2 tableaux parallèles
```

### Format

```json
{
  "_messageType": "ObjectAveragePricesMessage",
  "ids":       [1977, 7624, 7733, 15371, …],   // GID d'item
  "avgPrices": [1,    1,    1,    1,     …]     // prix moyen unitaire (x1) en kamas
}
```

### Caractéristiques confirmées (2 snapshots comparés)

- **4906 items** exactement, dans les 2 captures (couvre tout le marché du serveur).
- **Prix unitaire x1** (GID 468 : avg=28 vs meilleure offre HDV x1=14 — cohérent).
- **Par serveur**, mis à jour **au fil des ventes** (volume + récence) — PAS figé 24 h :
  **115 GID ont changé de prix** entre har_1 (07:50) et har_2 (08:41), soit 51 min.
  Deltas faibles (±1 à ±80 généralement) = ventes incrémentales qui bougent la moyenne.
- Un item **sans vente récente garde une valeur figée** jusqu'à sa prochaine vente.
- C'est exactement la requête du client officiel → **trafic 100 % légitime**.

### Avg price vs HDV

| | ObjectAveragePrices | Flow HDV (2 étapes) |
|---|---|---|
| Couverture | ~4900 items, 1 message | par type/objet, N requêtes |
| Nature | moyenne ventes récentes | offres actuelles (floor) |
| Quantité | x1 seulement | x1/x10/x100/x1000 |
| Coût réseau | minuscule | élevé |
| Usage | tendance / baseline | prix d'achat réel |

Module : `dtv/collector/avg_prices.py` (`AveragePricesCollector`).

---

## 5. HDV — flow en deux étapes

```
→ sendMessage:NpcGenericActionRequestMessage   {npcId:0, npcActionId:6, npcMapId:<mapId>}
← ExchangeStartedBidBuyerMessage   {buyerDescriptor:{…}}

  pour chaque type T de buyerDescriptor.types :
→ sendMessage:ExchangeBidHouseTypeMessage   {type:T}
← ExchangeTypesExchangerDescriptionForUserMessage   {typeDescription:[GID,…]}   ← SANS "Items"

    pour chaque GID de typeDescription :
→ sendMessage:ExchangeBidHouseListMessage   {id:GID}
← ExchangeTypesItemsExchangerDescriptionForUserMessage   {itemTypeDescriptions:[…]}   ← AVEC "Items"

→ sendMessage:LeaveDialogRequestMessage   (data: null)
← ExchangeLeaveMessage   {dialogType:11, success:false}
```

### `npcMapId` = mapId courant

Confirmé : `CurrentMapMessage.mapId` == `MapComplementaryInformationsDataMessage.mapId`
== `npcMapId` envoyé == **`145489923`**. L'HDV est accessible de partout ; `npcMapId`
indique juste la position. `npcActionId:6` = mode achat.

### `buyerDescriptor` (économie HDV)

```json
{
  "_type": "SellerBuyerDescriptor",
  "quantities": [1, 10, 100, 1000],
  "types": [1, 2, 3, …],          // 128 types sur ce serveur
  "taxPercentage": 3,             // taxe de vente HDV (%) — pour calcul de rentabilité
  "maxItemLevel": 1000,
  "maxItemPerAccount": 75,        // nb max d'objets en vente par compte
  "unsoldDelay": 672              // délai avant retour des invendus (heures = 28 j)
}
```

⚠️ **128 types** (pas 126). `quantities` toujours `[1,10,100,1000]`.

### `ExchangeTypesItemsExchangerDescriptionForUserMessage` (les prix)

```json
{
  "itemTypeDescriptions": [
    {
      "_type": "BidExchangerObjectInfo",
      "objectUID": 1227843,
      "effects": [{"_type":"ObjectEffectInteger","actionId":110,"value":30}],
      "prices": [14, 280, 2978, 0]      // [x1, x10, x100, x1000] — 0 = pas d'offre
    }
  ]
}
```

- `objectUID` = id de l'offre (pas du type).
- `objectGID` **absent** : c'est l'`id` envoyé dans `ExchangeBidHouseListMessage`.
- Pour les **ressources**, toutes les instances sont identiques → on agrège le min.
- Pour les **équipements**, chaque instance a des `effects` différents (rolls). **Hors scope** :
  le projet ne collecte que les ressources (superTypeId=9).

### Achat (référence — non utilisé par le collecteur)

```
→ sendMessage:ExchangeBidHouseBuyMessage   {uid:1225130, qty:1, price:300}
← KamasUpdateMessage   {kamasTotal:345}
← ObjectAddedMessage   {object:{objectGID:536, …}}
← ExchangeBidHouseBuyResultMessage   {uid:1225130, bought:true}
```

On peut enchaîner plusieurs types **sans rouvrir l'HDV** : après l'achat, le client a
directement renvoyé `ExchangeBidHouseTypeMessage{type:11}`. Une session HDV = un dialogue,
N types interrogés.

---

## 6. Types d'objets — ressources (superTypeId = 9)

`window.gui.databases.ItemTypes` (console DevTools) → **64 types** de superType 9.
Mapping figé dans `dtv/collector/item_types.py`.

- `RESOURCE_TYPE_IDS` : les 64 types ressources
- `CORE_RESOURCE_TYPE_IDS` : 41 types « craft » courants (exclut saisonnier/event/niche)
- **61/64** sont effectivement dans le `buyerDescriptor` du serveur ;
  3 absents : `125 Souvenir`, `211 Awakening Material`, `241 Vouchers`.
  → `HdvCollector.collect_resources()` fait l'intersection automatiquement.

Supertypes (extrait de `script.js`) :
`AMULET:1, WEAPON:2, RING:3, BELT:4, BOOTS:5, USABLE_OBJECT:6, SHIELD:7,
CAPTURING_OBJECT:8, RESOURCE:9, HAT:10, CAPE:11, PET:12, …`

---

## 7. Catalogue des messages observés

### Init serveur de jeu (poussés par le serveur, aucune action requise)

`ServerSettingsMessage`, `ServerBonusMessage`, `ServerOptionalFeaturesMessage`,
`ServerSessionConstantsMessage`, `AccountCapabilitiesMessage`, `TrustStatusMessage`,
`HeroSubscriptionMessage`, `SubscriptionStatusMessage`, `QueueStatusMessage`,
`NotificationListMessage`, `ServerExperienceModificatorMessage`, `InventoryContentMessage`,
`InventoryWeightMessage`, `SetUpdateMessage`, `EmoteListMessage`, `SpellListMessage`,
`ShortcutBarContentMessage`, `PrismsListMessage`, `EnabledChannelsMessage`,
`TitlesAndOrnamentsListMessage`, `AchievementListMessage`, `QuestListMessage`,
`FriendsListMessage`, `IgnoredListMessage`, `AlmanachCalendarDateMessage`,
`MailStatusMessage`, `CharacterStatsListMessage`, `CharacterCapabilitiesMessage`,
`SetCharacterRestrictionsMessage`, `TowerOfAscensionCompositionMessage` (volumineux ~55 Ko),
`GameContextCreateMessage`, `CurrentMapMessage`, `MapComplementaryInformationsDataMessage`,
`FarmSelectionMessage`, `RealEstatePropertiesMessage`.

### Gameplay (har_2 : déplacement, dialogues PNJ, level-up)

`GameMapMovementRequestMessage`/`GameMapMovementMessage`/`GameMapMovementConfirmMessage`,
`ChangeMapMessage`, `TeleportRequestMessage`/`TeleportResultMessage`,
`NpcGenericActionRequestMessage`, `NpcDialogReplyMessage`/`NpcDialogQuestionMessage`/`NpcDialogCreationMessage`,
`InteractiveUseRequestMessage`/`InteractiveUsedMessage`,
`QuestStepInfoRequestMessage`/`QuestStepInfoMessage`, `QuestStartedMessage`,
`QuestObjectiveValidatedMessage`, `QuestValidatedMessage`,
`CharacterExperienceGainMessage`, `CharacterLevelChangedMessage`/`CharacterLevelUpInformationMessage`,
`StatsUpgradeRequestMessage`/`StatsUpgradeResultMessage`,
`SpellChangeRequestMessage`/`SpellChangeSuccessMessage`,
`AchievementRewardRequestMessage`/`AchievementRewardSuccessMessage`/`AchievementFinishedMessage`,
`ZaapListMessage`, `ChatServerMessage`.

---

## 8. Headers HTTP / WebSocket (capture)

```
User-Agent: Mozilla/5.0 (Linux; Android 12; sdk_gphone64_x86_64 Build/SE1A.220826.008; wv)
            AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/91.0.4472.114
            Mobile Safari/537.36 DofusTouch Client 3.11.0
x-requested-with: com.ankama.dofustouch
```

⚠️ Le HAR vient d'un **AVD** (`sdk_gphone64_x86_64`, Chrome **91**). Le WebView embarqué
est ancien (Chrome 91). En production on imite plutôt un vrai device. `curl_cffi`
(`impersonate="chrome_android"`) gère le fingerprint TLS côté HAAPI.

---

## 9. Endpoints HTTP utiles (hors WebSocket)

| URL | Contenu |
|---|---|
| `…/login.ankama-games.com/config.json?lang=fr` | config (avant auth) |
| `…/data/dictionary?lang=fr&v=1.72.11` | noms d'items (⚠️ 404 hors contexte jeu — chargé en mémoire) |
| `haapi.ankama.com/json/Ankama/v5/Account/CreateToken` | game_token (confirmé `Account`, pas `Game`) |
| `dofustouch.cdn.ankama.com/…` | assets (images, atlas) |

Le `/data/dictionary` ne se fetch pas en direct (404). Pour les noms, lire
`window.gui.databases.Items` / `ItemTypes` depuis la console DevTools en jeu.
