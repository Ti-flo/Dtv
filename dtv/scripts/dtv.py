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
  dtv report [--open]        génère le rapport HTML interactif (autonome)

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


def cmd_report(args):
    import webbrowser
    from dtv.collector import report
    if not Path(config.DB_PATH).exists():
        print("Base vide — lance d'abord une capture puis `dtv ingest`.")
        return
    conn = store.connect()
    out = report.generate(conn, Path(args.out) if args.out else None)
    st = store.stats(conn)
    print(f"Rapport écrit : {out}")
    print(f"  {st['avg_items']} items, {st['avg_snapshots']} snapshots, "
          f"{st['hdv_rows']} relevés HDV")
    if args.open:
        webbrowser.open(out.resolve().as_uri())


def cmd_capture(args):
    from dtv.scripts import capture_phone
    argv = ["capture_phone", "--account", args.account, "--port", str(args.port)]
    if args.dump_raw:
        argv.append("--dump-raw")
    if args.no_adb:
        argv.append("--no-adb")
    if args.adb_serial:
        argv += ["--adb-serial", args.adb_serial]
    argv += (args.rest or [])
    _delegate(capture_phone.main, argv)


def _latest_avgprices() -> Path | None:
    """Le snapshot avgprices le plus récent de data/raw (pour les prix HDV/runes)."""
    files = sorted(Path(config.RAW_DIR).glob("avgprices_*.csv"))
    return files[-1] if files else None


def _brisage_autoargs(rest: list) -> list:
    """Complète les args brisage manquants depuis la config (avg-prices, rune-gids)."""
    argv = []
    if "--catalog" not in rest:
        cat = config.catalog("equipements")
        if cat:
            argv += ["--catalog", str(cat)]
    if "--avg-prices" not in rest:
        avg = _latest_avgprices()
        if avg:
            argv += ["--avg-prices", str(avg)]
    if "--rune-gids" not in rest and config.rune_gids_path().exists():
        argv += ["--rune-gids", str(config.rune_gids_path())]
    return argv


def cmd_brisage(args):
    from dtv.scripts import brisage
    _delegate(brisage.main, ["brisage"] + _brisage_autoargs(args.rest) + args.rest)


def cmd_craft(args):
    from dtv.scripts import brisage
    argv = ["brisage"] + _brisage_autoargs(args.rest) + ["--explain", args.item] + args.rest
    _delegate(brisage.main, argv)


def cmd_craftplan(args):
    from dtv.scripts import craft_plan
    argv = ["craft_plan", args.item]
    if args.n_crafts is not None:
        argv += ["--n-crafts", str(args.n_crafts)]
    if args.days is not None:
        argv += ["--days", str(args.days)]
    _delegate(craft_plan.main, argv)


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
    sp.add_argument("--account", default="main", help="nom du compte collecteur")
    sp.add_argument("--dump-raw", action="store_true", help="dump brut WS (debug)")
    sp.add_argument("--no-adb", action="store_true", help="pas d'auto-forward adb")
    sp.add_argument("--port", type=int, default=9222, help="port CDP (défaut 9222)")
    sp.add_argument("--adb-serial", help="serial adb si plusieurs devices")
    sp.add_argument("rest", nargs=argparse.REMAINDER, help="args supplémentaires")
    sp.set_defaults(func=cmd_capture)

    sp = sub.add_parser("report", help="génère le rapport HTML interactif (autonome)")
    sp.add_argument("--out", help="chemin du .html (défaut data/report.html)")
    sp.add_argument("--open", action="store_true", help="ouvre le rapport dans le navigateur")
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser("brisage", help="classement rentabilité de brisage")
    sp.add_argument("rest", nargs=argparse.REMAINDER, help="args passés à brisage")
    sp.set_defaults(func=cmd_brisage)

    sp = sub.add_parser("craft", help="détail coût de craft d'un item")
    sp.add_argument("item", help="nom de l'item")
    sp.add_argument("rest", nargs=argparse.REMAINDER, help="args passés à brisage")
    sp.set_defaults(func=cmd_craft)

    sp = sub.add_parser("craftplan", help="plan de craft optimisé (tiers d'achat + n_crafts)")
    sp.add_argument("item", help="nom de l'item à fabriquer")
    sp.add_argument("--n-crafts", type=int, default=None,
                    help="forcer le nombre de crafts (sinon estimé)")
    sp.add_argument("--days", type=int, default=None,
                    help="fenêtre prix HDV réels en jours (def 7)")
    sp.set_defaults(func=cmd_craftplan)

    return p


def main():
    # Passthrough subcommands bypass argparse entirely: everything after the
    # subcommand name is forwarded verbatim to the delegate (brisage.main, etc.).
    # parse_known_args() can't be used because it splits "--top 50" into two
    # separate tokens landing in different buckets (unknown vs REMAINDER).
    if len(sys.argv) >= 2 and sys.argv[1] in ("brisage", "craft"):
        cmd, rest = sys.argv[1], sys.argv[2:]
        if cmd == "brisage":
            class _A:
                pass
            a = _A(); a.rest = rest
            cmd_brisage(a)
        else:  # craft
            if not rest or rest[0].startswith("-"):
                build_parser().parse_args([cmd, "--help"])
            else:
                class _A:
                    pass
                a = _A(); a.item = rest[0]; a.rest = rest[1:]
                cmd_craft(a)
        return
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
