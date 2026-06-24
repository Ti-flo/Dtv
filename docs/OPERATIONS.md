# DTV — Exploitation : maintenance, mises à jour, bans

> Comment le bot réagit aux indisponibilités serveur et aux MAJ du jeu, et ce
> que le scheduler (à venir) doit faire dans chaque cas.

---

## 1. Codes de sortie de `collect.py`

`collect.py` se termine avec un code que le scheduler peut interpréter :

| Code | Catégorie | Signification | Action scheduler |
|---|---|---|---|
| `0` | — | Run OK (données collectées) | rien, run suivant à l'heure prévue |
| `2` | `retry_later` | Maintenance / réseau / file / drop / ticket périmé | **réessayer** dans X min (ou créneau suivant) |
| `3` | `stop_human` | **Ban** ou **client obsolète** (MAJ jeu) | **STOP** — intervention humaine requise |
| `1` | `unknown` | Échec générique (auth HAAPI, timeout, config) | réessayer 1-2× puis alerter |

Le mapping exact est dans `connection.classify_error()`.

---

## 2. Maintenance hebdomadaire

**Dofus Touch : généralement le mardi matin, ~8h–10h30 (heure de Paris)**, parfois
plus long. Le serveur est injoignable pendant l'opération (redémarrage + sauvegarde
BDD + parfois MAJ). Il y a aussi des **sauvegardes quotidiennes** (brèves coupures).

### Détection par le bot
- À la sélection serveur, on lit `ServersListMessage` : si le serveur cible a
  `status != 3` ou `isSelectable == false` → **maintenance** → erreur
  `server_unavailable` → code `2`.
- Si on est déconnecté en cours par le serveur (`primus::server::close`) au début
  de la fenêtre → `server_close` → code `2`.
- Au retour de maintenance, afflux de connexions → `QueueStatusMessage` (file
  d'attente) : le bot **attend** (le serveur fait avancer la position).

### Ce que le scheduler doit faire
- **Idéalement : ne pas planifier de run dans la fenêtre mardi 7h30–11h** (Paris).
  Décaler les créneaux de ce jour-là.
- Sinon, le run sortira en code `2` et sera simplement re-tenté plus tard. Pas de
  hammering : on abandonne proprement, on ne boucle pas sur un serveur down.

---

## 3. Mises à jour du jeu (changement de version)

Quand Ankama met à jour Dofus Touch, **`appVersion` / `buildVersion` / version de
protocole changent**. Nos valeurs sont codées en dur (`connection.py`) :
`APP_VERSION="3.11.0"`, `BUILD_VERSION="1.72.12"`, `PROTOCOL_VERSION=1595`.

### Détection par le bot (deux niveaux)
1. **Indice précoce** : `ProtocolRequired.requiredVersion != 1595` → log `⚠️ PROTOCOL
   VERSION CHANGED` + flag `_protocol_outdated`. Le run continue mais va probablement
   être rejeté.
2. **Signal définitif** : `IdentificationFailedForBadVersionMessage` → erreur
   `outdated_client_needs_update` → code `3` (STOP).

### Ce qu'il faut faire (manuel, non automatisable)
Une MAJ peut changer le **format des messages** → nos parseurs peuvent casser et,
pire, produire des **données fausses silencieusement**. Procédure :
1. Mettre le bot en pause (le code `3` doit couper le scheduler).
2. Récupérer le nouveau `script.js` depuis l'APK/AVD à jour.
3. Re-capturer un HAR (login + HDV) avec la nouvelle version.
4. Comparer aux séquences de `PROTOCOL.md` ; mettre à jour `APP_VERSION`,
   `BUILD_VERSION`, `PROTOCOL_VERSION` et tout message dont le format a bougé.
5. Re-valider (cf. passe de validation S6) avant de relancer.

> ⚠️ Ne jamais ignorer un code `3` « outdated » : des prix mal parsés sont pires
> que pas de prix.

---

## 4. Ban de compte

`IdentificationFailedBannedMessage` → erreur `account_banned` → code `3` (STOP).

- Le bot **ne réessaie jamais** un compte banni (ni reconnexion, ni run suivant).
- Action : retirer le compte de la rotation, en créer un nouveau (Gmail jetable
  depuis l'IP de prod, cf. règles `KNOWLEDGE.md`), investiguer la cause probable
  (IP ? volume ? timing ?) avant de continuer avec les autres comptes.
- **Signaux faibles à surveiller AVANT le ban** (cf. `PROTOCOL.md` §9) :
  `TrustStatus.trusted == false`, ou un `SequenceNumberRequest` inattendu pendant
  la collecte HDV. Si on les voit, lever le pied sur ce compte.

---

## 5. Déconnexion en cours de run

Le ticket de jeu (`SelectedServerDataMessage.ticket`) est **à usage unique** : on ne
peut pas rouvrir le socket de jeu seul. Donc :

- **Défaut (`auto_reconnect=False`)** : tout drop imprévu en cours de run
  **abandonne proprement**, sauvegarde les données déjà collectées (le snapshot de
  prix moyens est pris tôt, donc souvent déjà sauvé), et sort en code `2`. Le
  scheduler relance le pipeline complet plus tard.
- **`auto_reconnect=True`** (sessions longues, pas la collecte) : reconnexion =
  **re-login complet** (nouveau ticket), protégé par un circuit breaker (3 drops /
  5 min). Réutilise le `game_token` HAAPI ; s'il est périmé, abandon propre.

---

## 6. Résumé décisionnel

```
Erreur / situation                        → code → action
──────────────────────────────────────────────────────────
Serveur status!=3 / non sélectionnable    →  2  → maintenance, retry plus tard
primus::server::close                      →  2  → kick/maintenance, retry
ping_timeout / tcp_drop / game_dropped     →  2  → réseau, retry
ticket_refused                             →  2  → token périmé, retry (nouveau token)
QueueStatusMessage position>0              →  —  → attendre (pas une erreur)
ProtocolRequired version != 1595           → log → indice MAJ
IdentificationFailedForBadVersion          →  3  → MAJ jeu : STOP + re-capture
IdentificationFailedBanned                 →  3  → ban : STOP + nouveau compte
no_characters                              →  3  → config compte/serveur : STOP
auth HAAPI échoue                          →  1  → générique, retry 1-2× puis alerte
```

Sources maintenance : [Maintenances Dofus Touch](https://www.dofus-touch.com/fr/mmorpg/actualites/news/1182420-maintenance-mises-jour-sauvegarde-serveurs),
[Support Ankama](https://support.ankama.com/hc/en-us/articles/203588618-What-is-maintenance).
