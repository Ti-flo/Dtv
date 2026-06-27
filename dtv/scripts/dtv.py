"""
DTV — commande unique (DofusTradingView).

Une seule surface pour TOUT faire : capturer, ingérer, voir les prix, les
tendances, la rentabilité de brisage/craft. Sous-commandes :

  dtv doctor                 état de la config (adb, catalogues) + de la base
  dtv capture [--account X]  lance la capture passive (auto adb + socket)
  dtv ingest                 ingère les CSV data/raw/ dans la base SQLite
  dtv prices <nom>           dernier prix moyen des items qui matchent <nom>
  dtv history <nom|gid>      historique du prix moyen dans le temps
  dtv movers [--top N]       plus fortes variations entre les 2 derniers snapshots
  dtv brisage [...]          classement rentabilité de brisage (passe les args)
  dtv craft <nom>            détail du coût de craft d'un item

Tout chemin (adb, catalogues, base) est résolu par dtv/config.py — zéro saisie.
Exemples :
  python -m dtv.scripts.dtv doctor
  python -m dtv.scripts.dtv capture --account jetable
  python -m dtv.scripts.dtv ingest && python -m dtv.scripts.dtv movers
  python -m dtv.scripts.dtv history "Frêne"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dtv import config
from dtv.collector import store


# ── Helpers d'affichage (sans unicode exotique → sûr en console Windows cp1252) ─
def _fmt(n) -> str:
    return f"{n:,}".replace(",", " ") if isinstance(n, (int, float)) else str(n)


def _resolve_gid(conn, token: str):
    """Un token est soit un GID numérique, soit un nom à chercher."""
    if token.isdigit():
        return int(token)
    rows = store.search(conn, token, limit=1)
    return rows[0]["gid"] if rows else None


# ── Sous-commandes ──────────────────────────────────────────────────────────
def cmd_doctor(args):
    cfg = config.summary()
    print("== Config DTV ==")
    for k, v in cfg.items():
        if isinstance(v, dict):
            print(f"  {k}:")
            for kk, vv in v.items():
                print(f"      {kk}: {vv}")
        else:
            print(f"  {k}: {v}")
    if not cfg["adb_available"]:
        print("  [!] adb introuvable -> définir DTV_ADB ou l'ajouter au PATH")
    print("\n== Base SQLite ==")
    if not Path(config.DB_PATH).exists():
        print("  (vide — lance `dtv ingest` après une capture)")
        return
    conn = store.connect()
    st = store.stats(conn)
    for k, v in st.items():
        print(f"  {k}: {v}")


def cmd_ingest(args):
    conn = store.connect()
    s = store.ingest_all(conn)
    print("Ingestion terminée :")
    for kind, (files, rows) in s.items():
        print(f"  {kind:10s} {files} fichier(s), {rows} ligne(s)")
    st = store.stats(conn)
    print(f"\nBase : {st['avg_snapshots']} snapshots, {st['avg_items']} items, "
          f"{st['brisage_rows']} brisages — du {st['first_ts']} au {st['last_ts']}")


def cmd_prices(args):
    conn = store.connect()
    rows = store.search(conn, args.query, limit=args.top)
    if not rows:
        print(f"Aucun item ne matche « {args.query} » (as-tu lancé `dtv ingest` ?)")
        return
    print(f"  {'GID':>7s}  {'Prix moyen':>12s}  Nom")
    print("  " + "-" * 50)
    for r in rows:
        print(f"  {r['gid']:>7d}  {_fmt(r['price']):>12s}  {r['nom']}")


def cmd_history(args):
    conn = store.connect()
    gid = _resolve_gid(conn, args.item)
    if gid is None:
        print(f"Item introuvable : « {args.item} »")
        return
    hist = store.price_history(conn, gid)
    if not hist:
        print(f"Pas d'historique pour le GID {gid}")
        return
    nom = next((h["nom"] for h in reversed(hist) if h["nom"]), "")
    print(f"{nom} (GID {gid}) — {len(hist)} relevés")
    print(f"  {'Date':19s}  {'Prix':>12s}  Var")
    print("  " + "-" * 44)
    prev = None
    for h in hist:
        var = ""
        if prev not in (None, 0) and h["price"] is not None:
            pct = (h["price"] - prev) / prev * 100.0
            var = f"{pct:+.1f}%"
        print(f"  {(h['ts'] or '')[:19]:19s}  {_fmt(h['price']):>12s}  {var}")
        if h["price"] is not None:
            prev = h["price"]
    prices = [h["price"] for h in hist if h["price"] is not None]
    if prices:
        print(f"  min {_fmt(min(prices))} | max {_fmt(max(prices))} | "
              f"dernier {_fmt(prices[-1])}")


def cmd_movers(args):
    conn = store.connect()
    ms = store.movers(conn, limit=args.top, min_price=args.min_price)
    if not ms:
        print("Pas assez de snapshots (il en faut 2). Lance plus de captures + `dtv ingest`.")
        return
    print(f"  Plus fortes variations (2 derniers snapshots, prix >= {args.min_price})")
    print(f"  {'Var':>8s}  {'Ancien':>10s}  {'Nouveau':>10s}  Nom")
    print("  " + "-" * 52)
    for m in ms:
        print(f"  {m['pct']:>+7.1f}%  {_fmt(m['old']):>10s}  {_fmt(m['new']):>10s}  {m['nom']}")


def _delegate(main_fn, argv):
    """Appelle le main() d'un script existant avec un argv reconstruit."""
    old = sys.argv
    sys.argv = argv
    try:
        main_fn()
    finally:
        sys.argv = old


def cmd_capture(args):
    from dtv.scripts import capture_phone
    _delegate(capture_phone.main, ["capture_phone"] + args.rest)


def cmd_brisage(args):
    from dtv.scripts import brisage
    argv = ["brisage"]
    # Catalogue par défaut = équipements (résolu par config) si non fourni.
    if "--catalog" not in args.rest:
        cat = config.catalog("equipements")
        if cat:
            argv += ["--catalog", str(cat)]
    _delegate(brisage.main, argv + args.rest)


def cmd_craft(args):
    from dtv.scripts import brisage
    cat = config.catalog("equipements")
    argv = ["brisage", "--explain", args.item]
    if cat:
        argv += ["--catalog", str(cat)]
    argv += args.rest
    _delegate(brisage.main, argv)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dtv", description="DofusTradingView — commande unique")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="état config + base").set_defaults(func=cmd_doctor)
    sub.add_parser("ingest", help="ingère les CSV dans la base").set_defaults(func=cmd_ingest)

    sp = sub.add_parser("prices", help="dernier prix moyen par nom")
    sp.add_argument("query"); sp.add_argument("--top", type=int, default=20)
    sp.set_defaults(func=cmd_prices)

    sp = sub.add_parser("history", help="historique de prix d'un item")
    sp.add_argument("item", help="nom (partiel) ou GID")
    sp.set_defaults(func=cmd_history)

    sp = sub.add_parser("movers", help="plus fortes variations de prix")
    sp.add_argument("--top", type=int, default=20)
    sp.add_argument("--min-price", type=int, default=100)
    sp.set_defaults(func=cmd_movers)

    sp = sub.add_parser("capture", help="lance la capture passive (auto)")
    sp.add_argument("rest", nargs=argparse.REMAINDER, help="args passés à capture_phone")
    sp.set_defaults(func=cmd_capture)

    sp = sub.add_parser("brisage", help="classement rentabilité de brisage")
    sp.add_argument("rest", nargs=argparse.REMAINDER, help="args passés à brisage")
    sp.set_defaults(func=cmd_brisage)

    sp = sub.add_parser("craft", help="détail coût de craft d'un item")
    sp.add_argument("item", help="nom de l'item")
    sp.add_argument("rest", nargs=argparse.REMAINDER, help="args passés à brisage")
    sp.set_defaults(func=cmd_craft)

    return p


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
