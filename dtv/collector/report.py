"""
Rapport HTML interactif de DTV — `dtv report`.

Génère UN SEUL fichier .html autonome (self-contained, ouvrable hors-ligne, zéro
serveur) à partir de la base SQLite (data/dtv.db). Les données sont embarquées en
JSON dans la page ; toute l'interactivité (onglets, tri, graphes) est en JS
vanilla — aucune dépendance externe, aucun CDN.

Architecture :
  build_report_data(conn)  -> dict  (le modèle de données, sérialisable JSON)
  render_html(data)        -> str   (la page complète, JSON embarqué)
  generate(conn, out_path) -> Path  (écrit le fichier, retourne le chemin)

Onglets (itératif, un par un) :
  (1) Prix dans le temps  — séries avg (prix moyen marché) + HDV par tier
                            (x1/x10/x100/x1000), min/max/moyen, graphe + tri. ✅
  (2) Ressources achetées — depuis transactions_observations.   (à venir)
  (3) Craft & Brisage     — réutilise craft.py + brisage.py.     (à venir)
  (4) Bonnes affaires     — prix actuel vs médiane historique.   (à venir)

stdlib pure (sqlite3, json).
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .. import config
from . import item_names, store


# ── Construction du modèle de données ────────────────────────────────────────
def _price_series(conn: sqlite3.Connection) -> list[dict]:
    """
    Une entrée par item présent dans la base, avec ses séries temporelles :

      {
        "gid": int, "nom": str,
        "avg": [[ts, price], ...],                       # prix moyen marché (x1)
        "hdv": [[ts, x1, x10, x100, x1000, nb], ...],    # prix plancher par tier
      }

    Les séries sont triées par horodatage croissant. `nom` = le nom non vide le
    plus récent rencontré (avg puis hdv).
    """
    items: dict[int, dict] = {}

    def _slot(gid: int) -> dict:
        return items.setdefault(gid, {"gid": gid, "nom": "", "type": "", "avg": [], "hdv": []})

    # Prix moyens (ObjectAveragePrices) — la baseline « tendance ».
    for r in conn.execute(
        "SELECT gid, nom, ts, price FROM avg_prices "
        "WHERE price IS NOT NULL ORDER BY gid, ts"
    ):
        slot = _slot(r["gid"])
        if r["nom"]:
            slot["nom"] = r["nom"]
        slot["avg"].append([r["ts"], r["price"]])

    # Prix plancher HDV par tier — le « floor » temps réel.
    for r in conn.execute(
        "SELECT gid, nom, ts, prix_x1, prix_x10, prix_x100, prix_x1000, nb_offres "
        "FROM hdv_offers ORDER BY gid, ts"
    ):
        slot = _slot(r["gid"])
        if r["nom"]:
            slot["nom"] = r["nom"]
        slot["hdv"].append([
            r["ts"], r["prix_x1"], r["prix_x10"], r["prix_x100"],
            r["prix_x1000"], r["nb_offres"],
        ])

    # Noms manquants → résolution via le catalogue GID→nom (data/item_names.json,
    # alimenté par `dump_item_names`). Dernier repli : « GID <n> ».
    names = item_names.load_item_names()
    gid_types = item_names.load_gid_types()      # gid → type_id
    type_names = item_names.load_type_names()    # type_id → libellé
    for slot in items.values():
        if not slot["nom"]:
            slot["nom"] = names.get(slot["gid"]) or f"GID {slot['gid']}"
        tid = gid_types.get(slot["gid"])
        if tid is not None:
            slot["type"] = type_names.get(tid) or ""

    return sorted(items.values(), key=lambda s: s["nom"].lower())


def build_report_data(conn: sqlite3.Connection) -> dict:
    """Assemble le dict complet (sérialisable JSON) consommé par la page."""
    st = store.stats(conn)
    snaps = conn.execute(
        "SELECT snapshot, MIN(ts) AS ts FROM avg_prices GROUP BY snapshot ORDER BY ts"
    ).fetchall()
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "db_path": str(config.DB_PATH),
        "stats": dict(st),
        "snapshots": [{"id": r["snapshot"], "ts": r["ts"]} for r in snaps],
        "items": _price_series(conn),
    }


# ── Rendu HTML ───────────────────────────────────────────────────────────────
def render_html(data: dict) -> str:
    """Page HTML complète, JSON embarqué. Autonome, hors-ligne, sans dépendance."""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # Empêche une fermeture prématurée de la balise <script> si une donnée
    # contenait "</script>".
    payload = payload.replace("</", "<\\/")
    return _HTML_TEMPLATE.replace("/*__DTV_DATA__*/", payload)


def generate(conn: sqlite3.Connection, out_path: Optional[Path] = None) -> Path:
    """Construit le rapport et l'écrit sur disque. Retourne le chemin écrit."""
    out = Path(out_path or (config.DATA_DIR / "report.html"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(build_report_data(conn)), encoding="utf-8")
    return out


# Le gabarit est dans un module séparé pour garder ce fichier lisible.
from ._report_template import HTML_TEMPLATE as _HTML_TEMPLATE  # noqa: E402
