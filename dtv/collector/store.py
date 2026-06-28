"""
Entrepôt SQLite de DTV — l'épine dorsale « séries temporelles ».

Les captures produisent des CSV bruts dans data/raw/ (un fichier avgprices par
login, un hdv_passive par jour, brisage_observations qui s'accumule). Pour
comparer les prix DANS LE TEMPS sans relire tous les CSV à chaque fois, on les
ingère dans une base SQLite (data/dtv.db). Les CSV restent la source de vérité ;
l'ingestion est IDEMPOTENTE (réimporter un fichier ne crée pas de doublon).

Tables :
  avg_prices   — un snapshot de marché complet par login (≈4900 items)
  hdv_offers   — une ligne par item ouvert dans l'HDV (prix plancher réel)
  brisage_obs  — une observation de brisage (coeff réel + runes obtenues)

stdlib pure (sqlite3, csv).
"""
import csv
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .. import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS avg_prices (
    snapshot TEXT NOT NULL,        -- id du snapshot (= timestamp du fichier)
    ts       TEXT NOT NULL,        -- horodatage ISO
    gid      INTEGER NOT NULL,
    nom      TEXT,
    price    INTEGER,              -- prix moyen unitaire (x1) en kamas
    account  TEXT,
    PRIMARY KEY (snapshot, gid)
);
CREATE INDEX IF NOT EXISTS idx_avg_gid ON avg_prices(gid);
CREATE INDEX IF NOT EXISTS idx_avg_ts  ON avg_prices(ts);

CREATE TABLE IF NOT EXISTS hdv_offers (
    ts        TEXT NOT NULL,
    gid       INTEGER NOT NULL,
    nom       TEXT,
    hdv_type  INTEGER,
    prix_x1   INTEGER,
    prix_x10  INTEGER,
    prix_x100 INTEGER,
    prix_x1000 INTEGER,
    nb_offres INTEGER,
    account   TEXT,
    PRIMARY KEY (ts, gid)
);
CREATE INDEX IF NOT EXISTS idx_hdv_gid ON hdv_offers(gid);

CREATE TABLE IF NOT EXISTS brisage_obs (
    ts               TEXT NOT NULL,
    gid              INTEGER NOT NULL,
    nom              TEXT,
    coefficient_reel REAL,
    dernier_brisage  TEXT,
    runes_obtenues   TEXT,
    account          TEXT,
    PRIMARY KEY (ts, gid)
);
CREATE INDEX IF NOT EXISTS idx_bris_gid ON brisage_obs(gid);

-- Trace des fichiers déjà ingérés (info ; l'idempotence vient des clés primaires).
CREATE TABLE IF NOT EXISTS ingested_files (
    path     TEXT PRIMARY KEY,
    kind     TEXT,
    rows     INTEGER,
    ingested_at TEXT
);
"""


def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Ouvre (et initialise) la base. Retourne une connexion avec row factory."""
    path = Path(db_path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _to_int(v) -> Optional[int]:
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


# ── Ingestion ───────────────────────────────────────────────────────────────
def ingest_avgprices(conn: sqlite3.Connection, path: Path) -> int:
    """Ingère un fichier avgprices_*.csv (gère l'ancien format sans colonne nom)."""
    n = 0
    snapshot = path.stem.replace("avgprices_", "")
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            gid = _to_int(row.get("item_gid"))
            if gid is None:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO avg_prices(snapshot, ts, gid, nom, price, account) "
                "VALUES (?,?,?,?,?,?)",
                (snapshot, row.get("timestamp", ""), gid, row.get("nom", ""),
                 _to_int(row.get("avg_price_x1")), row.get("compte_collecteur", "")),
            )
            n += 1
    return n


def ingest_hdv(conn: sqlite3.Connection, path: Path) -> int:
    """Ingère un fichier hdv_passive_*.csv."""
    n = 0
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            gid = _to_int(row.get("item_gid"))
            ts = row.get("timestamp", "")
            if gid is None or not ts:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO hdv_offers"
                "(ts, gid, nom, hdv_type, prix_x1, prix_x10, prix_x100, prix_x1000, nb_offres, account) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (ts, gid, row.get("nom", ""), _to_int(row.get("hdv_type")),
                 _to_int(row.get("prix_x1")), _to_int(row.get("prix_x10")),
                 _to_int(row.get("prix_x100")), _to_int(row.get("prix_x1000")),
                 _to_int(row.get("nb_offres")), row.get("compte_collecteur", "")),
            )
            n += 1
    return n


def ingest_brisage(conn: sqlite3.Connection, path: Path) -> int:
    """Ingère brisage_observations.csv (auto-collecté)."""
    n = 0
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            gid = _to_int(row.get("GID"))
            ts = row.get("timestamp") or row.get("dernier_brisage") or ""
            if gid is None or not ts:
                continue
            try:
                coeff = float(row["coefficient_reel"]) if row.get("coefficient_reel") else None
            except ValueError:
                coeff = None
            conn.execute(
                "INSERT OR IGNORE INTO brisage_obs"
                "(ts, gid, nom, coefficient_reel, dernier_brisage, runes_obtenues, account) "
                "VALUES (?,?,?,?,?,?,?)",
                (ts, gid, row.get("nom", ""), coeff, row.get("dernier_brisage", ""),
                 row.get("runes_obtenues", ""), row.get("compte_collecteur", "")),
            )
            n += 1
    return n


def ingest_all(conn: sqlite3.Connection, raw_dir: Optional[Path] = None) -> dict:
    """
    Ingère tous les CSV connus de data/raw/. Idempotent (clés primaires).

    Retourne {kind: (fichiers, lignes)}.
    """
    raw = Path(raw_dir or config.RAW_DIR)
    stats = {"avgprices": [0, 0], "hdv": [0, 0], "brisage": [0, 0]}
    if not raw.exists():
        return stats

    jobs = [
        ("avgprices", sorted(raw.glob("avgprices_*.csv")), ingest_avgprices),
        ("hdv", sorted(raw.glob("hdv_passive_*.csv")), ingest_hdv),
        ("brisage", sorted(raw.glob("brisage_observations*.csv")), ingest_brisage),
    ]
    for kind, files, fn in jobs:
        for path in files:
            rows = fn(conn, path)
            conn.execute(
                "INSERT OR REPLACE INTO ingested_files(path, kind, rows, ingested_at) "
                "VALUES (?,?,?,datetime('now'))",
                (str(path), kind, rows),
            )
            stats[kind][0] += 1
            stats[kind][1] += rows
    conn.commit()
    return stats


# ── Requêtes ────────────────────────────────────────────────────────────────
def search(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[sqlite3.Row]:
    """Cherche un item par nom (partiel, insensible casse) → gid, nom, dernier prix."""
    like = f"%{query}%"
    return conn.execute(
        """
        SELECT gid, nom, MAX(ts) AS ts, price
        FROM avg_prices
        WHERE nom LIKE ?
        GROUP BY gid
        ORDER BY price DESC
        LIMIT ?
        """,
        (like, limit),
    ).fetchall()


def price_history(conn: sqlite3.Connection, gid: int) -> list[sqlite3.Row]:
    """Historique du prix moyen d'un item, du plus ancien au plus récent."""
    return conn.execute(
        "SELECT snapshot, ts, price, nom FROM avg_prices WHERE gid=? ORDER BY ts",
        (gid,),
    ).fetchall()


def snapshots(conn: sqlite3.Connection) -> list[str]:
    """Liste des snapshots avgprices (du plus ancien au plus récent)."""
    rows = conn.execute(
        "SELECT snapshot, MIN(ts) AS ts FROM avg_prices GROUP BY snapshot ORDER BY ts"
    ).fetchall()
    return [r["snapshot"] for r in rows]


def movers(conn: sqlite3.Connection, limit: int = 20, min_price: int = 100) -> list[dict]:
    """
    Plus fortes variations de prix moyen entre les 2 derniers snapshots.

    Retourne une liste triée par |variation %| décroissante :
      {gid, nom, old, new, delta, pct}
    """
    snaps = snapshots(conn)
    if len(snaps) < 2:
        return []
    prev, last = snaps[-2], snaps[-1]
    rows = conn.execute(
        """
        SELECT a.gid AS gid, COALESCE(b.nom, a.nom) AS nom,
               a.price AS old, b.price AS new
        FROM avg_prices a
        JOIN avg_prices b ON a.gid = b.gid
        WHERE a.snapshot=? AND b.snapshot=? AND a.price>=? AND a.price>0
        """,
        (prev, last, min_price),
    ).fetchall()
    out = []
    for r in rows:
        old, new = r["old"], r["new"]
        if old is None or new is None or old == 0:
            continue
        delta = new - old
        if delta == 0:
            continue
        out.append({
            "gid": r["gid"], "nom": r["nom"], "old": old, "new": new,
            "delta": delta, "pct": delta / old * 100.0,
        })
    out.sort(key=lambda d: abs(d["pct"]), reverse=True)
    return out[:limit]


def tier_prices_for_gids(conn: sqlite3.Connection, gids: list,
                         days: int = 7) -> dict:
    """
    Prix de lot réels (x1/x10/x100/x1000) par GID, pour chiffrer les ingrédients.

    Logique :
      1. Pour chaque GID, on prend le DERNIER snapshot HDV (la visite la plus
         récente de l'item dans l'HDV). Un 0 = aucun vendeur à ce tier → None.
      2. Si ce dernier snapshot est plus vieux que `days` jours (donnée périmée),
         on ignore les prix HDV et on replie sur le dernier `avg_prices` (tier x1).
      3. GID sans aucun snapshot HDV → repli avgprices directement.

    Retourne {gid: {1: prix_lot_x1, 10: …, 100: …, 1000: …}} (tier absent = None).
    """
    out: dict[int, dict] = {}
    gids = [g for g in {int(g) for g in gids if g is not None}]
    if not gids:
        return out

    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    ph = ",".join("?" * len(gids))

    # Dernier snapshot HDV par GID (sous-requête MAX(ts)).
    rows = conn.execute(
        f"""
        SELECT h.gid,
               h.ts,
               NULLIF(h.prix_x1, 0)    AS x1,
               NULLIF(h.prix_x10, 0)   AS x10,
               NULLIF(h.prix_x100, 0)  AS x100,
               NULLIF(h.prix_x1000, 0) AS x1000
        FROM hdv_offers h
        WHERE h.gid IN ({ph})
          AND h.ts = (SELECT MAX(ts) FROM hdv_offers h2 WHERE h2.gid = h.gid)
        """,
        tuple(gids),
    ).fetchall()

    for r in rows:
        if r["ts"] < cutoff:
            continue  # snapshot trop vieux → repli avgprices ci-dessous
        tiers = {1: r["x1"], 10: r["x10"], 100: r["x100"], 1000: r["x1000"]}
        if any(tiers.values()):
            out[r["gid"]] = tiers

    # Repli avgprices pour les GID sans snapshot HDV récent (absent ou périmé).
    missing = [g for g in gids if g not in out]
    if missing:
        ph2 = ",".join("?" * len(missing))
        arows = conn.execute(
            f"""
            SELECT gid, price FROM avg_prices ap
            WHERE gid IN ({ph2})
              AND ts = (SELECT MAX(ts) FROM avg_prices a2 WHERE a2.gid = ap.gid)
            """,
            tuple(missing),
        ).fetchall()
        for r in arows:
            if r["price"]:
                out[r["gid"]] = {1: r["price"], 10: None, 100: None, 1000: None}
    return out


def stats(conn: sqlite3.Connection) -> dict:
    """Compteurs globaux de la base (pour `dtv doctor` / `dtv status`)."""
    def one(q):
        return conn.execute(q).fetchone()[0]
    return {
        "avg_snapshots": one("SELECT COUNT(DISTINCT snapshot) FROM avg_prices"),
        "avg_rows": one("SELECT COUNT(*) FROM avg_prices"),
        "avg_items": one("SELECT COUNT(DISTINCT gid) FROM avg_prices"),
        "hdv_rows": one("SELECT COUNT(*) FROM hdv_offers"),
        "brisage_rows": one("SELECT COUNT(*) FROM brisage_obs"),
        "first_ts": one("SELECT MIN(ts) FROM avg_prices"),
        "last_ts": one("SELECT MAX(ts) FROM avg_prices"),
    }
