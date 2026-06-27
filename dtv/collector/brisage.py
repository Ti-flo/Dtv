"""
Moteur de brisage (rune-breaking profitability) — porté de RuneMaster.

Le brisage en Dofus Touch : casser un item le transforme en runes selon ses
effets. Chaque effet (ex « 351 à 400 Vitalité ») produit une rune (vi) en
quantité dépendant de la valeur moyenne, du niveau de l'item et du poids de la
rune. La rentabilité = valeur des runes obtenues − prix d'achat de l'item.

────────────────────────────────────────────────────────────────────────────
FORMULE (vérifiée sur objets_runes_formule_modele.xlsx, taux focalisation 100%)

  par ligne d'effet (rune R, valeur moyenne V, niveau Niv, poids P) :
    si R ∈ {vi, ii, pod}:   qty = (Niv/100)·V·P + 1
    sinon:                  qty = ((Niv/100)·V·P + 1) / P

  Le « +1 » = rune Ra de base toujours obtenue. La division par P convertit le
  pool de poids en nombre de runes de ce type. Les runes vi/ii/pod ont un poids
  < 1 (Vitalité, Initiative, Pods donnent de très grandes valeurs) → pas de
  division sinon les comptes explosent.
────────────────────────────────────────────────────────────────────────────

Pourquoi c'est l'upgrade de RuneMaster :
  RuneMaster exigeait la saisie MANUELLE des effets de chaque item
  (effets_moyens_par_rune.xlsx) et des prix (relevés quotidiens). DTV génère les
  effets depuis le catalogue scrapé (equipements_dofus_touch_full) et les prix
  depuis le HDV live → rentabilité de brisage sur tout le catalogue, zéro saisie.

Données de référence : dtv/data/runes.json (42 runes, mapping effet→code).
Le moteur est en stdlib pure (pas de pandas) → testable et léger ; l'I/O Excel
est dans dtv/scripts/brisage.py.
"""
import json
import re
from pathlib import Path
from typing import Optional

# ── Chargement des données de référence ─────────────────────────────────────
_DATA_PATH = Path(__file__).parent.parent / "data" / "runes.json"


def _load_runes() -> dict:
    with open(_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


_REF = _load_runes()
RUNES: dict[str, dict] = _REF["runes"]            # code → {poids, special, prix_exemple, …}
EFFET_VERS_CODE: dict[str, str] = _REF["effet_vers_code"]  # nom d'effet → code rune


# ── Parsing des effets ──────────────────────────────────────────────────────
# « 351 à 400 Vitalité » | « 1 PA » | « -16 à 20 Dommages Critiques »
# | « 6 à 8 % Résistance Eau » | « 4 à 6% Coups Critiques »
_EFFECT_RE = re.compile(r"^\s*(-?\d+)\s*(?:à\s*(-?\d+)\s*)?(.+?)\s*$")


def _normalize_label(label: str) -> str:
    """Espaces collapsés ; on garde le « % » car il distingue résistance fixe
    (« Résistance Eau » → re) de résistance pourcentage (« % Résistance Eau » → rep)."""
    return re.sub(r"\s+", " ", label).strip()


def effect_to_rune(label: str) -> Optional[str]:
    """Nom d'effet → code rune, ou None si non brisable / inconnu."""
    label = _normalize_label(label)
    if not label or label.startswith("("):   # lignes d'attaque d'arme « (dommages Air) »
        return None
    if label in EFFET_VERS_CODE:
        return EFFET_VERS_CODE[label]
    # tolérance « % X » ↔ « X »
    if label.startswith("% ") and label[2:] in EFFET_VERS_CODE:
        return EFFET_VERS_CODE[label[2:]]
    alt = "% " + label
    if alt in EFFET_VERS_CODE:
        return EFFET_VERS_CODE[alt]
    return None


def parse_effects(effets: str) -> list[dict]:
    """
    Découpe une chaîne d'effets « A | B | C » en lignes structurées.

    Retourne une liste de dicts : {label, valeur, code, brisable}.
      - valeur = moyenne du range (ou la valeur unique)
      - code   = code rune (None si non mappé)
      - brisable = code connu ET valeur > 0

    Les lignes d'effet exactement identiques (même label + même valeur) sont
    dédupliquées : un vrai item ne répète jamais la même ligne, donc un doublon
    = artefact de scraping (2 panels « Effets » sur dofus-touch.com). Ça rend le
    brisage correct même sur un catalogue non nettoyé.
    """
    out = []
    seen = set()
    if not effets or not isinstance(effets, str):
        return out
    for raw in effets.split("|"):
        raw = raw.strip()
        if not raw:
            continue
        m = _EFFECT_RE.match(raw)
        if not m:
            continue
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) is not None else lo
        valeur = (lo + hi) / 2.0
        label = _normalize_label(m.group(3))
        key = (label, valeur)
        if key in seen:
            continue
        seen.add(key)
        code = effect_to_rune(label)
        out.append({
            "label": label,
            "valeur": valeur,
            "code": code,
            "brisable": bool(code) and valeur > 0,
        })
    return out


# ── Formule de brisage ──────────────────────────────────────────────────────
def rune_yield(code: str, valeur: float, niveau: float) -> float:
    """Quantité de rune produite par une ligne d'effet (focalisation 100%)."""
    r = RUNES.get(code)
    if r is None or valeur <= 0:
        return 0.0
    p = r["poids"]
    base = (niveau / 100.0) * valeur * p + 1.0
    return base if r["special"] else base / p


def breakdown(effets: str, niveau: float) -> dict[str, float]:
    """{code rune → quantité totale} pour un item (somme sur ses lignes d'effet)."""
    acc: dict[str, float] = {}
    for line in parse_effects(effets):
        if not line["brisable"]:
            continue
        q = rune_yield(line["code"], line["valeur"], niveau)
        acc[line["code"]] = acc.get(line["code"], 0.0) + q
    return acc


# ── Rentabilité ─────────────────────────────────────────────────────────────
def rune_price(code: str, prices: Optional[dict[str, float]] = None) -> float:
    """Prix d'une rune : table fournie (HDV live) sinon prix_exemple RuneMaster."""
    if prices and code in prices and prices[code] is not None:
        return float(prices[code])
    ex = RUNES.get(code, {}).get("prix_exemple")
    return float(ex) if ex is not None else 0.0


def brisage_revenue(effets: str, niveau: float,
                    prices: Optional[dict[str, float]] = None,
                    coeff: float = 100.0) -> float:
    """
    Valeur en kamas des runes obtenues en brisant l'item.

    coeff = coefficient de brisage du serveur (en %). La formule de base est à
    100 % ; le revenu réel est proportionnel : revenu = base × coeff/100.
    """
    base = sum(q * rune_price(code, prices) for code, q in breakdown(effets, niveau).items())
    return base * coeff / 100.0


def profitability(effets: str, niveau: float, cout: Optional[float],
                  prices: Optional[dict[str, float]] = None,
                  coeff: float = 100.0) -> dict:
    """
    Bilan de brisage d'un item.

    Args:
        effets : chaîne d'effets du catalogue scrapé
        niveau : niveau de l'item
        cout   : prix d'achat HDV (ou coût de craft) ; None si inconnu
        prices : {code rune → prix} (HDV live) ; sinon prix exemple
        coeff  : coefficient de brisage du serveur en % (1 à 4000). On ne le
                 connaît qu'APRÈS avoir brisé l'item ; il tend vers 1 % à mesure
                 qu'un item est brisé. Par défaut 100 % (base de la formule).

    Le revenu réel = revenu_base × coeff/100. La métrique de décision est
    `coeff_min` = coefficient minimal pour être rentable (revenu_base = coût) :
    on ne connaît pas le coeff réel, mais on sait qu'il faut au moins coeff_min %.
    Plus `coeff_min` est bas, plus l'item est un pari sûr à briser.

    Retourne : revenu (au coeff donné), revenu_coeff100 (base), coeff, coeff_min,
    cout, benefice, rentabilite, detail runes.
    """
    detail = breakdown(effets, niveau)
    base = sum(q * rune_price(code, prices) for code, q in detail.items())
    revenu = base * coeff / 100.0
    benefice = (revenu - cout) if cout is not None else None
    rentabilite = (revenu / cout) if (cout not in (None, 0)) else None
    coeff_min = (cout / base * 100.0) if (cout is not None and base > 0) else None
    return {
        "revenu": round(revenu, 2),
        "revenu_coeff100": round(base, 2),
        "coeff": coeff,
        "coeff_min": round(coeff_min, 2) if coeff_min is not None else None,
        "cout": cout,
        "benefice": round(benefice, 2) if benefice is not None else None,
        "rentabilite": round(rentabilite, 4) if rentabilite is not None else None,
        "runes": {c: round(q, 3) for c, q in sorted(detail.items(), key=lambda kv: -kv[1])},
    }
