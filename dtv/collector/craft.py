"""
Plan d'achat optimal pour le craft : combien d'items fabriquer, et à quel tier
(x1/x10/x100/x1000) acheter chaque ingrédient pour minimiser le coût unitaire.

────────────────────────────────────────────────────────────────────────────
PROBLÈME

Quand on fabrique un item pour le briser (ou le revendre), le coût des
ingrédients dépend de la QUANTITÉ achetée. L'HDV vend par lots : x1, x10, x100,
x1000. Plus le lot est gros, moins c'est cher à l'unité (en général). Mais on
ne veut pas acheter 1000 unités d'un ingrédient si on n'en utilise que 3 — c'est
du capital immobilisé.

Le bon tier dépend du BESOIN TOTAL = quantité_recette × nombre_de_crafts. Et le
nombre de crafts dépend du coût : un craft pas cher → on en fait des centaines
(donc on achète en gros) ; un craft cher → on en fait quelques-uns (achat petit).

────────────────────────────────────────────────────────────────────────────
ÉCHELLE NOMBRE DE CRAFTS (validée avec Flo, en kamas de coût unitaire)

     coût ≤ 2 000        → 1000 crafts   (items très bon marché, volume massif)
     2 000 < coût ≤ 10k  →  200 crafts
     10k   < coût ≤ 100k →   20 crafts
     100k  < coût ≤ 300k →   10 crafts
     coût  > 300 000     →    1 craft    (au-delà : item à VENDRE en HDV
                                          directement, pas à briser en masse)

stdlib pure (pas d'I/O) → testable et réutilisable par le CLI et le futur report.
"""
import math
from typing import Optional

# Tiers d'achat de l'HDV (tailles de lot). Confirmé sur les captures : la
# quantité de lot vient de sellerDescriptor.quantities = [1, 10, 100, 1000].
QUANTITY_TIERS = (1, 10, 100, 1000)

# Échelle (borne_haute_incluse, nombre_de_crafts). Au-delà de la dernière borne
# → NCRAFT_BEYOND (item à revendre tel quel plutôt qu'à fabriquer en masse).
NCRAFT_SCALE = (
    (2_000, 1000),
    (10_000, 100),
    (100_000, 20),
    (300_000, 10),
)
NCRAFT_BEYOND = 1


def estimate_n_crafts(cost_per_craft: Optional[float]) -> int:
    """Nombre de crafts qu'on fera, selon le coût unitaire de fabrication."""
    if cost_per_craft is None:
        return 1
    for upper, n in NCRAFT_SCALE:
        if cost_per_craft <= upper:
            return n
    return NCRAFT_BEYOND


def _best_unit_price(tier_prices: dict) -> Optional[float]:
    """Meilleur prix À L'UNITÉ tous tiers confondus (lot/taille), 0 ignoré."""
    units = [p / t for t, p in tier_prices.items() if p and p > 0]
    return min(units) if units else None


MAX_PURCHASES = 30  # seuil de praticabilité : au-delà c'est trop de clics HDV


def best_tier(tier_prices: dict, total_needed: int,
              max_purchases: int = MAX_PURCHASES) -> Optional[tuple]:
    """
    Choisit le tier d'achat optimal en deux temps :
      1. Praticabilité d'abord : seuls les tiers qui donnent ≤ max_purchases
         transactions sont candidats (ceil(total_needed / tier) ≤ max_purchases).
      2. Parmi ces candidats, on prend le meilleur prix à l'unité.

    Si aucun tier n'atteint le seuil de praticabilité, on prend le plus grand
    tier disponible (minimum de transactions même si > max_purchases).
    Si le besoin est inférieur au plus petit lot disponible, on prend ce lot.

    tier_prices : {1: prix_lot_x1, 10: prix_lot_x10, 100: …, 1000: …}
        Prix du LOT entier. 0/None = pas de stock.
    total_needed : qty_recette × n_crafts.
    """
    avail = {t: p for t, p in tier_prices.items() if p and p > 0}
    if not avail:
        return None

    # Tiers ≤ total_needed (ne pas acheter plus que le besoin en un seul lot).
    usable = {t: p for t, p in avail.items() if t <= total_needed}
    if not usable:
        # Besoin plus petit que le plus petit lot → on achète ce lot (1 transaction).
        t = min(avail)
        return (t, avail[t] / t)

    # Praticables : ≤ max_purchases transactions.
    practical = {t: p for t, p in usable.items()
                 if math.ceil(total_needed / t) <= max_purchases}
    if practical:
        t = min(practical, key=lambda t: practical[t] / t)
        return (t, practical[t] / t)

    # Aucun tier assez grand → on prend le plus grand disponible (minimise les achats).
    t = max(usable)
    return (t, usable[t] / t)


def craft_plan(recipe_items: list, ingredient_tier_prices: dict,
               n_crafts: Optional[int] = None) -> Optional[dict]:
    """
    Plan d'achat complet pour fabriquer un item.

    Args:
        recipe_items : [(qty, nom), …] — la recette (qty d'ingrédient par craft).
        ingredient_tier_prices : {nom: {1:.., 10:.., 100:.., 1000:..}} prix de lot.
        n_crafts : forcé si fourni ; sinon estimé depuis le coût naïf.

    Algorithme (une passe d'auto-cohérence) :
        1. coût naïf = Σ qty × meilleur_prix_unitaire (sert juste à estimer n_crafts)
        2. n_crafts = estimate_n_crafts(coût naïf)   (sauf si forcé)
        3. pour chaque ingrédient : besoin = qty × n_crafts → tier optimal → prix
        4. coût/craft = Σ qty × prix_unitaire du tier choisi

    Retourne None si recette vide, sinon un dict :
        n_crafts, cost_per_craft, cost_total, complete, missing, detail
        detail : [{qty, nom, tier, unit_price, line_cost, total_needed}, …]
    """
    if not recipe_items:
        return None

    # 1. coût naïf (meilleur prix unitaire absolu) pour calibrer n_crafts.
    naive = 0.0
    missing = []
    for qty, nom in recipe_items:
        tp = ingredient_tier_prices.get(nom)
        bu = _best_unit_price(tp) if tp else None
        if bu is None:
            missing.append(nom)
        else:
            naive += qty * bu

    # 2. nombre de crafts.
    if n_crafts is None:
        n_crafts = estimate_n_crafts(naive if not missing else None)

    # 3-4. tier optimal par ingrédient + coût par craft.
    detail = []
    cost_per_craft = 0.0
    for qty, nom in recipe_items:
        tp = ingredient_tier_prices.get(nom)
        total_needed = qty * n_crafts
        bt = best_tier(tp, total_needed) if tp else None
        avail = {t: p for t, p in (tp or {}).items() if p and p > 0}
        if bt is None:
            detail.append({"qty": qty, "nom": nom, "tier": None, "unit_price": None,
                           "line_cost": None, "total_needed": total_needed,
                           "n_purchases": None, "available_tiers": avail})
        else:
            tier, up = bt
            line = qty * up
            cost_per_craft += line
            n_purchases = math.ceil(total_needed / tier)
            detail.append({"qty": qty, "nom": nom, "tier": tier, "unit_price": up,
                           "line_cost": line, "total_needed": total_needed,
                           "n_purchases": n_purchases, "available_tiers": avail})

    return {
        "n_crafts": n_crafts,
        "cost_per_craft": cost_per_craft,
        "cost_total": cost_per_craft * n_crafts,
        "complete": not missing,
        "missing": missing,
        "detail": detail,
    }
