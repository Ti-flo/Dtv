"""
HDV analysis dashboard — tableau de bord des données collectées.

Loads all hdv_passive_*.csv and avgprices_*.csv from data/raw/, joins with
item type names, and presents price summaries, trends, and filters.

Usage:
    python -m dtv.scripts.analyze                   # full dashboard
    python -m dtv.scripts.analyze --type Ore        # filter by type name (partial, case-insensitive)
    python -m dtv.scripts.analyze --type-id 39      # filter by numeric type ID
    python -m dtv.scripts.analyze --gid 12345       # price history for one item GID
    python -m dtv.scripts.analyze --from 2026-06-01 # date range
    python -m dtv.scripts.analyze --to 2026-06-24
    python -m dtv.scripts.analyze --account main    # filter by account
    python -m dtv.scripts.analyze --top 30          # top N items (default 20)
    python -m dtv.scripts.analyze --html out.html   # export self-contained HTML report
    python -m dtv.scripts.analyze --csv out.csv     # export merged/enriched CSV
    python -m dtv.scripts.analyze --avg             # compare HDV prices vs avg snapshot

Item names (GID → "Blé", "Frêne" …):
    Run ONCE while the game is open:
        python -m dtv.scripts.dump_item_names
    This saves data/item_names.json and names appear in all tables automatically.
"""
import argparse
import csv
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent.parent
DATA_DIR = ROOT / "data" / "raw"

sys.path.insert(0, str(ROOT))

from dtv.collector.item_types import RESOURCE_TYPES
from dtv.collector.item_names import load_item_names

# All known item types (equipment + resources). Extend as new types are discovered.
ALL_ITEM_TYPES: dict[int, str] = {
    # Equipment
    1: "Amulette", 2: "Anneau", 9: "Sac à dos", 10: "Chapeau",
    11: "Cape", 13: "Ceinture", 16: "Bottes", 17: "Bâton",
    18: "Baguette", 19: "Épée", 21: "Pelle", 22: "Marteau",
    23: "Lance", 24: "Arc", 25: "Dague", 27: "Bouclier",
    44: "Familier", 45: "Monture", 56: "Dragodinde", 69: "Harnais",
    83: "Équipement de Bouftou", 85: "Trophée",
    # Consumables / misc
    5: "Potion", 6: "Parchemin de sort", 7: "Parchemin de caractéristique",
    8: "Document", 12: "Objet de quête",
    **RESOURCE_TYPES,
}


# ------------------------------------------------------------------ #
# Data loading                                                        #
# ------------------------------------------------------------------ #

def _parse_ts(s: str) -> "datetime | None":
    """Parse ISO timestamp; return None on failure."""
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:26], fmt)
        except ValueError:
            pass
    return None


def load_hdv_data(data_dir: Path = DATA_DIR) -> list[dict]:
    """Load and merge all hdv_passive_*.csv files."""
    rows = []
    files = sorted(data_dir.glob("hdv_passive_*.csv"))
    if not files:
        return rows
    for path in files:
        try:
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row["_source_file"] = path.name
                    rows.append(row)
        except Exception as e:
            log.warning("Could not read %s: %s", path.name, e)
    return rows


def load_avg_data(data_dir: Path = DATA_DIR) -> dict[int, list[dict]]:
    """Load all avgprices_*.csv; return {gid → [{"timestamp", "avg_price_x1"}, ...]}."""
    result: dict[int, list[dict]] = defaultdict(list)
    for path in sorted(data_dir.glob("avgprices_*.csv")):
        try:
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        gid = int(row.get("item_gid", 0))
                        price = int(float(row.get("avg_price_x1", 0)))
                        ts = row.get("timestamp", "")
                        result[gid].append({"timestamp": ts, "avg_price_x1": price})
                    except (ValueError, TypeError):
                        pass
        except Exception as e:
            log.warning("Could not read %s: %s", path.name, e)
    return dict(result)


def enrich(rows: list[dict]) -> list[dict]:
    """Add type_name, item_name, numeric fields. Returns new list."""
    names = load_item_names()
    out = []
    for r in rows:
        r = dict(r)
        # Resolve type name
        try:
            tid = int(float(r.get("hdv_type") or 0))
        except (ValueError, TypeError):
            tid = 0
        r["hdv_type_id"] = tid
        r["type_name"] = ALL_ITEM_TYPES.get(tid, f"type_{tid}" if tid else "unknown")

        # Numeric prices
        for col in ("prix_x1", "prix_x10", "prix_x100", "prix_x1000"):
            try:
                r[col] = int(float(r[col])) if r.get(col) else 0
            except (ValueError, TypeError):
                r[col] = 0

        try:
            r["item_gid"] = int(float(r.get("item_gid") or 0))
        except (ValueError, TypeError):
            r["item_gid"] = 0
        r["item_name"] = names.get(r["item_gid"], "")

        try:
            r["nb_offres"] = int(float(r.get("nb_offres") or 0))
        except (ValueError, TypeError):
            r["nb_offres"] = 0

        r["_ts"] = _parse_ts(r.get("timestamp", ""))
        out.append(r)
    return out


# ------------------------------------------------------------------ #
# Filters                                                             #
# ------------------------------------------------------------------ #

def apply_filters(
    rows: list[dict],
    type_name: "str | None" = None,
    type_id: "int | None" = None,
    gid: "int | None" = None,
    account: "str | None" = None,
    from_date: "datetime | None" = None,
    to_date: "datetime | None" = None,
) -> list[dict]:
    out = []
    for r in rows:
        if type_name and type_name.lower() not in r["type_name"].lower():
            continue
        if type_id is not None and r["hdv_type_id"] != type_id:
            continue
        if gid is not None and r["item_gid"] != gid:
            continue
        if account and r.get("compte_collecteur", "") != account:
            continue
        ts = r["_ts"]
        if from_date and ts and ts < from_date:
            continue
        if to_date and ts and ts > to_date:
            continue
        out.append(r)
    return out


# ------------------------------------------------------------------ #
# Aggregation                                                         #
# ------------------------------------------------------------------ #

def _safe_avg(values: list[int]) -> float:
    vals = [v for v in values if v > 0]
    return sum(vals) / len(vals) if vals else 0.0


def _price_trend(history: list[int]) -> str:
    """Simple trend indicator from oldest to newest non-zero observation."""
    vals = [v for v in history if v > 0]
    if len(vals) < 2:
        return "  —  "
    diff = vals[-1] - vals[0]
    pct = diff / vals[0] * 100
    if pct > 5:
        return f"↑{pct:+.0f}%"
    if pct < -5:
        return f"↓{pct:+.0f}%"
    return f"→{pct:+.0f}%"


def aggregate_by_type(rows: list[dict]) -> list[dict]:
    """One row per type: count, avg/min/max prix_x1, nb unique GIDs."""
    by_type: dict[int, dict] = {}
    for r in rows:
        tid = r["hdv_type_id"]
        if tid not in by_type:
            by_type[tid] = {
                "hdv_type_id": tid,
                "type_name": r["type_name"],
                "count": 0,
                "gids": set(),
                "prices_x1": [],
            }
        g = by_type[tid]
        g["count"] += 1
        g["gids"].add(r["item_gid"])
        if r["prix_x1"] > 0:
            g["prices_x1"].append(r["prix_x1"])

    result = []
    for g in by_type.values():
        px = g["prices_x1"]
        result.append({
            "type_name": g["type_name"],
            "hdv_type_id": g["hdv_type_id"],
            "nb_observations": g["count"],
            "nb_items": len(g["gids"]),
            "prix_x1_min": min(px) if px else 0,
            "prix_x1_avg": round(_safe_avg(px)),
            "prix_x1_max": max(px) if px else 0,
        })
    return sorted(result, key=lambda x: x["nb_observations"], reverse=True)


def aggregate_by_gid(rows: list[dict], top_n: int = 20) -> list[dict]:
    """Top N most-observed items: price history, trend."""
    by_gid: dict[int, dict] = {}
    for r in rows:
        gid = r["item_gid"]
        if gid not in by_gid:
            by_gid[gid] = {
                "item_gid": gid,
                "type_name": r["type_name"],
                "hdv_type_id": r["hdv_type_id"],
                "observations": [],
            }
        by_gid[gid]["observations"].append(r)

    result = []
    for gid, g in by_gid.items():
        obs = sorted(g["observations"], key=lambda x: x["_ts"] or datetime.min)
        prices = [o["prix_x1"] for o in obs]
        last = next((p for p in reversed(prices) if p > 0), 0)

        # Last observed price for each quantity tier (most recent non-zero).
        def _last_tier(col):
            return next((o[col] for o in reversed(obs) if o.get(col, 0) > 0), 0)

        result.append({
            "item_gid": gid,
            "item_name": obs[0].get("item_name", "") if obs else "",
            "type_name": g["type_name"],
            "nb_observations": len(obs),
            "derniere_observation": obs[-1].get("timestamp", "")[:16] if obs else "",
            "dernier_prix_x1": last,
            "dernier_prix_x10": _last_tier("prix_x10"),
            "dernier_prix_x100": _last_tier("prix_x100"),
            "dernier_prix_x1000": _last_tier("prix_x1000"),
            "prix_x1_min": min((p for p in prices if p > 0), default=0),
            "prix_x1_avg": round(_safe_avg(prices)),
            "prix_x1_max": max((p for p in prices if p > 0), default=0),
            "tendance": _price_trend(prices),
            "_prices": prices,
        })
    return sorted(result, key=lambda x: x["nb_observations"], reverse=True)[:top_n]


def gid_history(rows: list[dict], gid: int) -> list[dict]:
    """Chronological price history for a single GID."""
    items = [r for r in rows if r["item_gid"] == gid]
    items.sort(key=lambda x: x["_ts"] or datetime.min)
    return items


def all_avg_prices(avg_data: dict, rows: list[dict]) -> list[dict]:
    """
    Every item from the login average-price snapshots (the whole market), with
    its latest average price. Type is resolved from HDV observations when the
    player happened to open that item; otherwise left blank (the snapshot itself
    carries no type — that needs GID→item resolution, still TODO).
    Sorted by price descending.
    """
    names = load_item_names()
    gid_type = {r["item_gid"]: r["type_name"] for r in rows if r["item_gid"]}
    gid_name = {r["item_gid"]: r.get("item_name", "") for r in rows if r["item_gid"]}
    out = []
    for gid, snaps in avg_data.items():
        if not snaps:
            continue
        latest = snaps[-1]
        out.append({
            "item_gid": gid,
            "item_name": gid_name.get(gid) or names.get(gid, ""),
            "type_name": gid_type.get(gid, ""),
            "avg_price_x1": latest["avg_price_x1"],
            "timestamp": (latest.get("timestamp") or "")[:16],
        })
    return sorted(out, key=lambda x: x["avg_price_x1"], reverse=True)


# ------------------------------------------------------------------ #
# Terminal output                                                     #
# ------------------------------------------------------------------ #

_RESET = "\033[0m"
_BOLD = "\033[1m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_CYAN = "\033[36m"
_YELLOW = "\033[33m"
_DIM = "\033[2m"

# Windows cmd/PowerShell don't render ANSI unless explicitly enabled.
# Windows Terminal and VSCode terminal set WT_SESSION or TERM_PROGRAM.
_USE_COLOR = (
    sys.stdout.isatty()
    and not (sys.platform == "win32"
             and not (os.environ.get("WT_SESSION")
                      or os.environ.get("TERM_PROGRAM")
                      or os.environ.get("TERM")))
)


def _c(text: str, code: str) -> str:
    return f"{code}{text}{_RESET}" if _USE_COLOR else text


def _fmt_price(p: int) -> str:
    if p <= 0:
        return _c("—", _DIM)
    if p >= 1_000_000:
        return _c(f"{p/1_000_000:.1f}M", _CYAN)
    if p >= 1_000:
        return _c(f"{p/1_000:.1f}k", _YELLOW)
    return str(p)


def _trend_color(t: str) -> str:
    if t.startswith("↑"):
        return _c(t, _GREEN)
    if t.startswith("↓"):
        return _c(t, _RED)
    return _c(t, _DIM)


def _table(headers: list[str], rows: list[list[str]], col_widths: list[int] = None):
    """Print a simple aligned table."""
    if not rows:
        print("  (aucune donnée)")
        return
    if col_widths is None:
        col_widths = [max(len(headers[i]), max(len(_strip_ansi(str(r[i]))) for r in rows))
                      for i in range(len(headers))]

    sep = "  "
    # Strip ANSI only for width measurement; keep colors in output
    header_line = sep.join(
        _c(h.ljust(col_widths[i]), _BOLD) for i, h in enumerate(headers)
    )
    print(header_line)
    print("─" * (sum(col_widths) + len(sep) * (len(headers) - 1)))
    for row in rows:
        line = sep.join(
            str(row[i]).ljust(col_widths[i] + len(str(row[i])) - len(_strip_ansi(str(row[i]))))
            for i in range(len(row))
        )
        print(line)


def _strip_ansi(s: str) -> str:
    import re
    return re.sub(r"\033\[[0-9;]*m", "", s)


def print_summary(rows: list[dict], avg_data: dict):
    if not rows:
        print("\nAucune donnée collectée dans data/raw/. Jouez un peu !")
        return

    ts_values = [r["_ts"] for r in rows if r["_ts"]]
    date_min = min(ts_values).strftime("%Y-%m-%d %H:%M") if ts_values else "?"
    date_max = max(ts_values).strftime("%Y-%m-%d %H:%M") if ts_values else "?"
    unique_gids = len({r["item_gid"] for r in rows if r["item_gid"]})
    accounts = {r.get("compte_collecteur", "") for r in rows} - {""}

    print()
    print(_c("═══ TABLEAU DE BORD HDV ═══", _BOLD))
    print(f"  Période       : {date_min} → {date_max}")
    print(f"  Observations  : {len(rows):,}")
    print(f"  Items uniques : {unique_gids:,}")
    if avg_data:
        print(f"  Prix moyens   : {len(avg_data):,} items (snapshots)")
    if accounts:
        print(f"  Comptes       : {', '.join(sorted(accounts))}")
    print()


def print_by_type(rows: list[dict]):
    agg = aggregate_by_type(rows)
    if not agg:
        return
    print(_c("── Par type d'item ──", _BOLD))
    headers = ["Type", "ID", "Obs.", "Items", "Prix x1 min", "Prix x1 moy", "Prix x1 max"]
    table_rows = [
        [
            g["type_name"],
            str(g["hdv_type_id"]),
            str(g["nb_observations"]),
            str(g["nb_items"]),
            _fmt_price(g["prix_x1_min"]),
            _fmt_price(g["prix_x1_avg"]),
            _fmt_price(g["prix_x1_max"]),
        ]
        for g in agg
    ]
    _table(headers, table_rows)
    print()


def print_top_items(rows: list[dict], top_n: int = 20):
    items = aggregate_by_gid(rows, top_n)
    if not items:
        return
    print(_c(f"── Top {top_n} items les plus observés (derniers prix par palier) ──", _BOLD))
    headers = ["GID", "Nom", "Type", "Obs.", "x1", "x10", "x100", "x1000",
               "x1 moy", "Tendance", "Vu le"]
    table_rows = [
        [
            str(g["item_gid"]),
            (g.get("item_name") or "")[:28],
            g["type_name"],
            str(g["nb_observations"]),
            _fmt_price(g["dernier_prix_x1"]),
            _fmt_price(g["dernier_prix_x10"]),
            _fmt_price(g["dernier_prix_x100"]),
            _fmt_price(g["dernier_prix_x1000"]),
            _fmt_price(g["prix_x1_avg"]),
            _trend_color(g["tendance"]),
            g["derniere_observation"],
        ]
        for g in items
    ]
    _table(headers, table_rows)
    print()


def print_gid_history(rows: list[dict], gid: int, avg_data: dict):
    history = gid_history(rows, gid)
    if not history:
        print(f"Aucune donnée pour GID {gid}")
        return

    type_name = history[0]["type_name"] if history else "?"
    item_name = history[0].get("item_name", "") if history else ""
    name_part = f" · {item_name}" if item_name else ""
    print(_c(f"── Historique GID {gid}{name_part}  [{type_name}] ──", _BOLD))

    avg_snapshots = avg_data.get(gid, [])
    avg_by_date: dict[str, int] = {}
    for snap in avg_snapshots:
        d = snap["timestamp"][:10]
        avg_by_date[d] = snap["avg_price_x1"]

    headers = ["Timestamp", "x1", "x10", "x100", "x1000", "Offres", "Prix moy. (snapshot)", "Session"]
    table_rows = []
    for r in history:
        date_key = (r.get("timestamp") or "")[:10]
        avg_snap = avg_by_date.get(date_key, 0)
        table_rows.append([
            (r.get("timestamp") or "")[:19],
            _fmt_price(r["prix_x1"]),
            _fmt_price(r["prix_x10"]),
            _fmt_price(r["prix_x100"]),
            _fmt_price(r["prix_x1000"]),
            str(r["nb_offres"]),
            _fmt_price(avg_snap) if avg_snap else _c("—", _DIM),
            r.get("session", ""),
        ])
    _table(headers, table_rows)
    print()


def print_avg_comparison(rows: list[dict], avg_data: dict, top_n: int = 20):
    """Show items where HDV price differs significantly from the avg snapshot."""
    if not avg_data:
        print("Aucun snapshot de prix moyens disponible (se crée à la connexion).")
        return

    print(_c("── Comparaison prix HDV vs prix moyen (snapshot connexion) ──", _BOLD))

    # Last observed HDV price per GID
    last_hdv: dict[int, dict] = {}
    for r in sorted(rows, key=lambda x: x["_ts"] or datetime.min):
        if r["item_gid"] and r["prix_x1"] > 0:
            last_hdv[r["item_gid"]] = r

    comparison = []
    for gid, hdv_row in last_hdv.items():
        snaps = avg_data.get(gid, [])
        if not snaps:
            continue
        avg_p = snaps[-1]["avg_price_x1"]
        if avg_p <= 0:
            continue
        hdv_p = hdv_row["prix_x1"]
        if hdv_p <= 0:
            continue
        diff_pct = (hdv_p - avg_p) / avg_p * 100
        comparison.append({
            "item_gid": gid,
            "item_name": hdv_row.get("item_name", ""),
            "type_name": hdv_row["type_name"],
            "hdv_prix_x1": hdv_p,
            "avg_prix_x1": avg_p,
            "diff_pct": diff_pct,
        })

    comparison.sort(key=lambda x: abs(x["diff_pct"]), reverse=True)
    shown = comparison[:top_n]

    headers = ["GID", "Nom", "Type", "Prix HDV x1", "Prix moy. x1", "Écart"]
    table_rows = []
    for g in shown:
        diff = g["diff_pct"]
        diff_str = f"{diff:+.0f}%"
        # diff = (prix_hdv - prix_moyen) / prix_moyen :
        #   diff < 0 → HDV moins cher que la moyenne = bonne affaire (vert)
        #   diff > 0 → HDV plus cher que la moyenne (rouge)
        if diff < -10:
            diff_str = _c(diff_str, _GREEN)
        elif diff > 10:
            diff_str = _c(diff_str, _RED)
        table_rows.append([
            str(g["item_gid"]),
            (g.get("item_name") or "")[:28],
            g["type_name"],
            _fmt_price(g["hdv_prix_x1"]),
            _fmt_price(g["avg_prix_x1"]),
            diff_str,
        ])
    _table(headers, table_rows)
    print()


def print_all_avg(avg_data: dict, rows: list[dict], limit: int = 40):
    """Print the full market snapshot (all average prices), most expensive first."""
    items = all_avg_prices(avg_data, rows)
    if not items:
        print("Aucun snapshot de prix moyens disponible (se crée à la connexion).")
        return
    shown = items[:limit]
    print(_c(f"── Tous les prix moyens du marché ({len(items):,} items, top {len(shown)} par prix) ──", _BOLD))
    headers = ["GID", "Nom", "Type", "Prix moyen x1", "Snapshot"]
    table_rows = [
        [str(a["item_gid"]),
         (a.get("item_name") or "")[:28],
         a["type_name"] or _c("?", _DIM),
         _fmt_price(a["avg_price_x1"]),
         a["timestamp"]]
        for a in shown
    ]
    _table(headers, table_rows)
    if len(items) > limit:
        print(_c(f"  … {len(items) - limit:,} autres — exporte en HTML pour la liste complète filtrable.", _DIM))
    print()


# ------------------------------------------------------------------ #
# HTML export                                                         #
# ------------------------------------------------------------------ #

def export_html(rows: list[dict], avg_data: dict, output_path: Path):
    ts_values = [r["_ts"] for r in rows if r["_ts"]]
    date_min = min(ts_values).strftime("%Y-%m-%d %H:%M") if ts_values else "?"
    date_max = max(ts_values).strftime("%Y-%m-%d %H:%M") if ts_values else "?"
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    # By-type aggregation + top items (rendered inline below).
    agg = aggregate_by_type(rows)
    top = aggregate_by_gid(rows, top_n=50)

    # Avg comparison
    last_hdv: dict[int, dict] = {}
    for r in sorted(rows, key=lambda x: x["_ts"] or datetime.min):
        if r["item_gid"] and r["prix_x1"] > 0:
            last_hdv[r["item_gid"]] = r
    comparison = []
    for gid, hdv_row in last_hdv.items():
        snaps = avg_data.get(gid, [])
        if not snaps:
            continue
        avg_p = snaps[-1]["avg_price_x1"]
        if avg_p <= 0 or hdv_row["prix_x1"] <= 0:
            continue
        diff_pct = (hdv_row["prix_x1"] - avg_p) / avg_p * 100
        comparison.append({
            "item_gid": gid,
            "item_name": hdv_row.get("item_name", ""),
            "type_name": hdv_row["type_name"],
            "hdv_prix_x1": hdv_row["prix_x1"],
            "avg_prix_x1": avg_p,
            "diff_pct": round(diff_pct, 1),
        })
    comparison.sort(key=lambda x: abs(x["diff_pct"]), reverse=True)

    # Pre-build table bodies (no backslashes allowed inside f-string expressions < 3.12)
    unique_gids_count = len({r["item_gid"] for r in rows})

    type_rows_html = "".join(
        "<tr>"
        + f"<td>{g['type_name']}</td><td>{g['hdv_type_id']}</td>"
        + f"<td>{g['nb_observations']}</td><td>{g['nb_items']}</td>"
        + f"<td>{g['prix_x1_min']:,}</td><td>{round(g['prix_x1_avg']):,}</td>"
        + f"<td>{g['prix_x1_max']:,}</td>"
        + "</tr>"
        for g in agg
    )

    top_rows_html = "".join(
        "<tr>"
        + f"<td>{g['item_gid']}</td>"
        + f"<td>{g.get('item_name', '')}</td>"
        + f"<td>{g['type_name']}</td>"
        + f"<td>{g['nb_observations']}</td>"
        + f"<td>{g['dernier_prix_x1']:,}</td><td>{g['dernier_prix_x10']:,}</td>"
        + f"<td>{g['dernier_prix_x100']:,}</td><td>{g['dernier_prix_x1000']:,}</td>"
        + f"<td>{g['tendance']}</td><td>{g['derniere_observation']}</td>"
        + "</tr>"
        for g in top
    )

    # All average prices from the login snapshots — the full market, not just
    # the items the player opened. Resolve type from HDV observations when known.
    all_avg = all_avg_prices(avg_data, rows)
    allavg_rows_html = "".join(
        "<tr>"
        + f"<td>{a['item_gid']}</td>"
        + f"<td>{a.get('item_name', '')}</td>"
        + f"<td>{a['type_name']}</td>"
        + f"<td>{a['avg_price_x1']:,}</td><td>{a['timestamp']}</td>"
        + "</tr>"
        for a in all_avg
    ) or "<tr><td colspan=5>Aucun snapshot de prix moyens</td></tr>"

    def _diff_color(pct: float) -> str:
        if pct < -10:
            return "#5f5"
        if pct > 10:
            return "#f55"
        return "#aaa"

    if comparison:
        avg_rows_html = "".join(
            "<tr>"
            + f"<td>{g['item_gid']}</td>"
            + f"<td>{g.get('item_name', '')}</td>"
            + f"<td>{g['type_name']}</td>"
            + f"<td>{g['hdv_prix_x1']:,}</td><td>{g['avg_prix_x1']:,}</td>"
            + f'<td style="color:{_diff_color(g["diff_pct"])}">{g["diff_pct"]:+.1f}%</td>'
            + "</tr>"
            for g in comparison[:50]
        )
    else:
        avg_rows_html = "<tr><td colspan=6>Aucune donnée de comparaison</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DTV — Tableau de bord HDV</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 0; padding: 1rem 2rem;
          background: #0f1117; color: #e0e0e0; }}
  h1 {{ color: #7ec8e3; border-bottom: 1px solid #333; padding-bottom: .5rem; }}
  h2 {{ color: #a0c8e0; margin-top: 2rem; }}
  .meta {{ color: #888; font-size: .9rem; margin-bottom: 2rem; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: .5rem; font-size: .9rem; }}
  th {{ background: #1e2430; color: #7ec8e3; padding: 8px 12px;
        text-align: left; border-bottom: 2px solid #333; position: sticky; top: 0; }}
  td {{ padding: 6px 12px; border-bottom: 1px solid #1a1e2a; }}
  tr:hover td {{ background: #1a1f2a; }}
  tr:nth-child(even) td {{ background: #0d1018; }}
  input[type=text] {{ background: #1e2430; color: #e0e0e0; border: 1px solid #444;
                       border-radius: 4px; padding: 6px 10px; font-size: 1rem;
                       width: 300px; margin-bottom: .5rem; }}
  input[type=text]::placeholder {{ color: #666; }}
  section {{ margin-bottom: 3rem; }}
</style>
<script>
function filterTable(inputId, tableId) {{
  const q = document.getElementById(inputId).value.toLowerCase();
  const rows = document.querySelectorAll(`#${{tableId}} tbody tr`);
  rows.forEach(r => {{
    r.style.display = r.textContent.toLowerCase().includes(q) ? '' : 'none';
  }});
}}
</script>
</head>
<body>
<h1>Tableau de bord HDV — Dofus Touch</h1>
<div class="meta">
  Généré le {generated} &nbsp;|&nbsp;
  Période : {date_min} → {date_max} &nbsp;|&nbsp;
  {len(rows):,} observations &nbsp;|&nbsp;
  {unique_gids_count:,} items uniques
</div>

<section>
  <h2>Par type d'item</h2>
  <input type="text" id="f-type" placeholder="Filtrer par type..." oninput="filterTable('f-type','t-type')">
  <table id="t-type">
    <thead><tr>
      <th>Type</th><th>ID</th><th>Observations</th><th>Items uniques</th>
      <th>Prix x1 min</th><th>Prix x1 moy</th><th>Prix x1 max</th>
    </tr></thead>
    <tbody>{type_rows_html}</tbody>
  </table>
</section>

<section>
  <h2>Top 50 items les plus observés — derniers prix par palier</h2>
  <input type="text" id="f-top" placeholder="Filtrer (GID, nom, type, prix)..." oninput="filterTable('f-top','t-top')">
  <table id="t-top">
    <thead><tr>
      <th>GID</th><th>Nom</th><th>Type</th><th>Obs.</th>
      <th>Prix x1</th><th>Prix x10</th><th>Prix x100</th><th>Prix x1000</th>
      <th>Tendance</th><th>Dernière obs.</th>
    </tr></thead>
    <tbody>{top_rows_html}</tbody>
  </table>
</section>

<section>
  <h2>Comparaison prix HDV vs prix moyen (snapshot connexion)</h2>
  <input type="text" id="f-avg" placeholder="Filtrer (GID, nom, type)..." oninput="filterTable('f-avg','t-avg')">
  <table id="t-avg">
    <thead><tr>
      <th>GID</th><th>Nom</th><th>Type</th><th>Prix HDV x1</th><th>Prix moy. x1</th><th>Écart %</th>
    </tr></thead>
    <tbody>{avg_rows_html}</tbody>
  </table>
</section>

<section>
  <h2>Tous les prix moyens du marché ({len(all_avg):,} items — snapshot connexion)</h2>
  <input type="text" id="f-allavg" placeholder="Filtrer (GID, nom, type)..." oninput="filterTable('f-allavg','t-allavg')">
  <table id="t-allavg">
    <thead><tr>
      <th>GID</th><th>Nom</th><th>Type</th><th>Prix moyen x1</th><th>Snapshot</th>
    </tr></thead>
    <tbody>{allavg_rows_html}</tbody>
  </table>
</section>

</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
    print(f"Rapport HTML exporté → {output_path}")


# ------------------------------------------------------------------ #
# CSV export                                                          #
# ------------------------------------------------------------------ #

def export_csv(rows: list[dict], output_path: Path):
    if not rows:
        print("Aucune donnée à exporter.")
        return
    # Determine field names: standard + extras
    base_fields = ["timestamp", "session", "item_gid", "item_name", "hdv_type_id", "type_name",
                   "prix_x1", "prix_x10", "prix_x100", "prix_x1000",
                   "nb_offres", "all_prices_x1", "compte_collecteur"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=base_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV enrichi exporté → {output_path} ({len(rows):,} lignes)")


# ------------------------------------------------------------------ #
# Entry point                                                         #
# ------------------------------------------------------------------ #

def main():
    parser = argparse.ArgumentParser(
        description="Tableau de bord HDV — analyse des données collectées passives"
    )
    parser.add_argument("--type", metavar="NOM",
                        help="Filtrer par nom de type (ex: Ore, Wood) — partiel, insensible à la casse")
    parser.add_argument("--type-id", type=int, metavar="ID",
                        help="Filtrer par identifiant numérique de type")
    parser.add_argument("--gid", type=int, metavar="GID",
                        help="Afficher l'historique complet d'un seul item GID")
    parser.add_argument("--account", metavar="COMPTE",
                        help="Filtrer par compte collecteur")
    parser.add_argument("--from", dest="from_date", metavar="YYYY-MM-DD",
                        help="Observations à partir de cette date")
    parser.add_argument("--to", dest="to_date", metavar="YYYY-MM-DD",
                        help="Observations jusqu'à cette date")
    parser.add_argument("--top", type=int, default=20,
                        help="Nombre d'items à afficher dans le top (défaut: 20)")
    parser.add_argument("--avg", action="store_true",
                        help="Afficher la comparaison prix HDV vs snapshots de prix moyens")
    parser.add_argument("--avg-all", action="store_true",
                        help="Afficher TOUS les prix moyens du marché (snapshot connexion)")
    parser.add_argument("--html", metavar="FICHIER",
                        help="Exporter un rapport HTML self-contained")
    parser.add_argument("--csv", metavar="FICHIER",
                        help="Exporter les données enrichies en CSV")
    parser.add_argument("--data-dir", metavar="DOSSIER", default=str(DATA_DIR),
                        help=f"Dossier contenant les CSV (défaut: {DATA_DIR})")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    data_dir = Path(args.data_dir)
    raw_rows = load_hdv_data(data_dir)
    avg_data = load_avg_data(data_dir)

    if not raw_rows:
        print(f"\nAucune donnée dans {data_dir}/")
        print("Lancez d'abord : python -m dtv.scripts.capture_phone")
        sys.exit(0)

    rows = enrich(raw_rows)

    from_date = datetime.strptime(args.from_date, "%Y-%m-%d") if args.from_date else None
    to_date   = datetime.strptime(args.to_date,   "%Y-%m-%d") if args.to_date   else None

    filtered = apply_filters(
        rows,
        type_name=args.type,
        type_id=args.type_id,
        gid=args.gid,
        account=args.account,
        from_date=from_date,
        to_date=to_date,
    )

    if args.html:
        export_html(filtered, avg_data, Path(args.html))
        return

    if args.csv:
        export_csv(filtered, Path(args.csv))
        return

    print_summary(filtered, avg_data)

    if args.gid:
        print_gid_history(filtered, args.gid, avg_data)
        return

    if args.avg_all:
        # Whole-market view doesn't depend on the HDV row filters (the snapshot
        # covers every item), so pass the unfiltered rows for type resolution.
        print_all_avg(avg_data, rows, limit=max(args.top, 40))
        return

    print_by_type(filtered)
    print_top_items(filtered, args.top)

    if args.avg:
        print_avg_comparison(filtered, avg_data, args.top)


if __name__ == "__main__":
    main()
