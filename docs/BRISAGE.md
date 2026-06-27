# Brisage — moteur de rentabilité (porté de RuneMaster)

> Calcule, pour chaque item, la valeur des runes obtenues en le brisant, et la
> rentabilité (valeur runes − prix d'achat). Porté du système manuel RuneMaster
> vers DTV, automatisé sur tout le catalogue scrapé + prix HDV live.

---

## Principe du brisage en Dofus Touch

Briser un item le transforme en **runes** selon ses **effets**. Chaque effet
(ex « 351 à 400 Vitalité ») produit une rune (`vi`) en quantité dépendant de :
- la **valeur moyenne** de l'effet (375.5 pour « 351 à 400 »)
- le **niveau** de l'item
- le **poids** de la rune (les runes lourdes — PA, Tacle — sont rares/chères)

Rentabilité = `Σ(quantité_rune × prix_rune) − prix_achat_item`.

---

## Formule (vérifiée, taux de focalisation 100 %)

Rétro-ingénierée depuis `RuneMaster/Objets/objets_runes_formule_modele.xlsx`
(formule Excel lue cellule par cellule), **vérifiée au centième sur 9 points**
(in, vi, pm, sa, ta, pu, ch, pod) :

```
par ligne d'effet (rune R, valeur moyenne V, niveau Niv, poids P) :

  si R ∈ {vi, ii, pod}:   qty = (Niv/100) · V · P + 1
  sinon:                  qty = ((Niv/100) · V · P + 1) / P
```

- Le **« +1 »** = rune Ra de base toujours obtenue.
- La **division par P** convertit le pool de poids en nombre de runes de ce type.
- **vi (Vitalité), ii (Initiative), pod (Pods)** ont un poids < 1 et donnent de
  très grandes valeurs → traitées sans division (sinon comptes gonflés).

Exemples vérifiés :
| rune | V | niveau | poids | runes |
|---|---|---|---|---|
| in | 8 | 2 | 1 | 1.16 |
| vi | 5 | 2 | 0.2 | 1.02 (spécial) |
| pm | 1 | 50 | 90 | 0.5111 |
| sa | 40.5 | 200 | 1 | 82.0 |
| ta | 16 | 150 | 4 | 24.25 |
| pu | 63 | 200 | 2 | 126.5 |

---

## Coefficient de brisage (taux serveur)

La formule ci-dessus donne le rendement **à coefficient 100 %** (la « base »). Sur
le serveur, chaque item a un **coefficient de brisage dynamique** (de **1 % à
4000 %**) qui **tend vers 1 %** à mesure que l'item est brisé. **On ne connaît le
coefficient qu'APRÈS avoir brisé l'item.**

```
revenu_réel = revenu_base × (coeff / 100)
```

Vérifié sur `Tableau_Brisage` : Anneau Bouftou base=13005, à Coeff 120 % →
Revenu 15606 = 13005 × 1.2 ✓.

### Coeff Min = la métrique de décision
Comme le coefficient réel est inconnu d'avance, on calcule le **coefficient
minimal pour être rentable** (revenu_base = coût) :

```
coeff_min = coût / revenu_base × 100
```

→ « il faut au moins coeff_min % de coefficient pour rentrer dans mes frais ».
**Plus coeff_min est bas, plus l'item est un pari sûr.** (Vérifié : Anneau Bouftou
coeff_min=215.3 = 28000/13005×100 ✓.) C'est le tri par défaut du CLI quand le coût
est connu.

---

## Paliers de runes (simple → Pa → Ra)

Les runes se **concassent** en paliers supérieurs (noms exacts en jeu confirmés
par Flo) :
```
3 runes simples  →  1 rune Pa (×3)     |     3 runes Pa  →  1 rune Ra (×9 simples)
```

Le nombre de paliers **dépend de la stat** (champ `tiers` dans `runes.json`,
avec le nom exact en jeu et `mult_base` en unités de rune simple) :

| Paliers | Stats | Ex. noms en jeu |
|---|---|---|
| **3** (simple/Pa/Ra) | 9 stats primaires : Vi, Sa, Fo, Ine, Cha, Age, Pui, Pod, Ini | Rune Fo, Rune Pa Fo, Rune Ra Fo |
| **2** (simple/Pa) | Tac, Fui, So, Prospe, Do élém + Do Pou/Cri, Ré fixes + Ré Pou/Cri, Ret/Ré Pa/Pme | Rune Tac, Rune Pa Tac |
| **1** (simple) | Do, Cri, Po, Invo, % Ré Per (Air/Eau/Feu/Terre/Neutre), Chasse | Rune Do, Rune Cri |
| **géant only** | PA (`pa`), PM (`pm`) | Rune Ga Pa, Rune Ga Pme |

La formule donne la quantité en **rune simple**. Vendre en palier supérieur peut
rapporter plus **si** `prix_Pa > 3 × prix_simple` — **optimisation de vente, étape
future** (nécessite les prix par palier). Le modèle actuel value chaque rune à un
prix unique (comme RuneMaster).

⚠️ **`giant_only`** (`pa`, `pm`) : n'existent qu'en Ga, **pas de concassage**. La
quantité de la formule est déjà en Ga, le prix est celui du Ga.

---

## Observations (coefficient réel + dernier brisage)

Le **coefficient réel** d'un item ne se connaît qu'**en jeu, après l'avoir brisé**.
On le relève dans `brisage_observations.csv` (séparé du catalogue, qui se régénère
par scraping) :

```
GID,coefficient_reel,dernier_brisage
2424,280,2026-06-27
```

Passé via `--observations`, le CLI :
- affiche les colonnes **Coeff Réel** + **Dernier Brisage** ;
- **utilise le coeff réel par item** (au lieu de `--coeff`) pour Revenu/Bénéfice ;
- la **date** dit si le coeff est encore fiable (le coeff dérive à chaque brisage).

> 🔜 **À terme, relevé automatiquement depuis le serveur** (comme les prix) — voir
> la TODO « auto-collecte coeff » dans KNOWLEDGE.md. Pour l'instant rempli à la main.

---

## Données de référence — `dtv/data/runes.json`

42 runes. Pour chaque code : `nom` (effet canonique), `display` (nom RuneMaster),
`poids`, `special` (bool), `prix_exemple` (snapshot manuel RuneMaster).

Plus `effet_vers_code` : mapping **nom d'effet → code rune**, dérivé en croisant
`effets_moyens_par_rune.xlsx` avec le catalogue scrapé `equipements_dofus_touch_full`
(vote majoritaire sur les valeurs), corrigé avec la convention Dofus pour les
collisions (quatuor Force/Int/Agi/Chance, résistances).

Codes notables : `vi`=Vitalité, `sa`=Sagesse, `fo`=Force, `in`=Intelligence,
`ch`=Chance, `ag`=Agilité, `pu`=Puissance, `pp`=Prospection, `ii`=Initiative,
`pa`=PA (Ga PA), `pm`=PM (Ga PM), `po`=Portée, `ta`=Tacle, `fu`=Fuite,
`cc`=% Coups Critiques, `dmg`=Dommages, `so`=Soins, `ic`=Invocations.
Dommages élém : `daf`/`def`/`dff`/`dtf` (Air/Eau/Feu/Terre, Neutre→dtf),
`dc`=Do Critiques, `dp`=Do Poussée. Résistances % : `rap`/`rep`/`rfp`/`rtp`/`rnp`,
fixes : `ra`/`re`/`rf`/`rt`/`rn`, `rc`=Ré Cri, `rp`=Ré Pou.

---

## Modules

| Fichier | Rôle |
|---|---|
| `dtv/data/runes.json` | 42 runes + mapping effet→code |
| `dtv/collector/brisage.py` | moteur (parse effets, formule, rentabilité) — stdlib pur |
| `dtv/scripts/brisage.py` | CLI : croise catalogue + prix → classement |
| `dtv/scripts/build_rune_gids.py` | mappe code rune → GID (pour prix HDV live) |
| `dtv/scripts/test_brisage.py` | non-régression (formule, parsing, dédup, rentabilité) |

### Robustesse du parsing (`brisage.parse_effects`)
- **Ranges** « 351 à 400 X » → moyenne ; valeur simple « 1 PA »
- **% vs fixe** : « % Résistance Eau » → `rep`, « Résistance Eau » → `re`
- **Négatifs / nuls** ignorés (pas de rune)
- **Conditions** (« PA < 12 ») ignorées (pas de nombre en tête)
- **Lignes d'attaque d'arme** « (dommages Air) » ignorées
- **Déduplication** des lignes identiques → pas de double comptage même sur un
  catalogue non nettoyé (2 panels « Effets » de dofus-touch.com)

---

## Utilisation

```powershell
# Classement par revenu de brisage (prix exemple, tourne tout de suite)
python -m dtv.scripts.brisage --catalog equipements_dofus_touch_full.xlsx

# Avec prix HDV live : coût des items + prix des runes (via GID)
python -m dtv.scripts.build_rune_gids --catalog ressources_dofus_touch_full.xlsx
python -m dtv.scripts.brisage --catalog equipements_dofus_touch_full.xlsx \
    --avg-prices data/raw/avgprices_20260626.csv --rune-gids dtv/data/rune_gids.json \
    --top 100 --out top_brisage.xlsx

# Bénéfice à un coefficient supposé (ex 250 %), trié par bénéfice
python -m dtv.scripts.brisage --catalog equipements_dofus_touch_full.xlsx \
    --avg-prices data/raw/avgprices_20260626.csv --rune-gids dtv/data/rune_gids.json \
    --coeff 250 --sort benefice

# Avec les coeffs réels observés en jeu (par item)
python -m dtv.scripts.brisage --catalog equipements_dofus_touch_full.xlsx \
    --avg-prices data/raw/avgprices_20260626.csv --rune-gids dtv/data/rune_gids.json \
    --observations brisage_observations.csv
```

Sortie : `GID | Nom | Type | Niveau | Revenu_coeff100 | Revenu_brisage | Cout_HDV |
Coeff_Min | Coeff_Reel | Dernier_Brisage | Benefice | Rentabilite | Runes`.
Tri par défaut (coût connu) = **Coeff Min croissant** (pari le plus sûr) ;
`--sort benefice|revenu` au choix. `--coeff` fixe le coefficient supposé pour les
colonnes Revenu/Bénéfice (def 100 %).

---

## Pourquoi c'est l'upgrade de RuneMaster

RuneMaster (manuel) exigeait :
- la **saisie manuelle** des effets de chaque item (`effets_moyens_par_rune.xlsx`)
- des **relevés de prix quotidiens** à la main

DTV automatise **les deux** :
- les **effets** viennent du catalogue scrapé (`equipements_dofus_touch_full`)
- les **prix** viennent du **HDV live** (snapshot `avgprices_*.csv` — items ET runes)

→ rentabilité de brisage recalculée sur **tout le catalogue** (2825 équipements)
à chaque snapshot de prix, **zéro saisie**.

### Limites / pistes
- `prix_exemple` = snapshot RuneMaster figé → à remplacer par le HDV live (objet du
  `build_rune_gids` + `--rune-gids`).
- **Coefficient** : géré via `--coeff` + `Coeff_Min` (break-even). Le coeff réel
  reste inconnu d'avance ; piste = relever le coeff observé en jeu par item pour
  affiner (le serveur le fait varier 1 %–4000 %).
- **Paliers de runes** : valuation par palier (vendre en Pa/Ga si plus rentable)
  pas encore faite — nécessite les prix Ra/Pa/Ga par stat. `giant_only` déjà marqué.
- Le coût « craft » (fabriquer puis briser) n'est pas encore croisé — possible via
  la colonne `Recette` + prix des ingrédients (prochaine étape).
