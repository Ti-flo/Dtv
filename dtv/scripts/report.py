"""
Entrypoint `python -m dtv.scripts.report` — génère le rapport HTML interactif.

Fin wrapper autour de dtv.collector.report (le `dtv report` du CLI unique passe
par le même module). Voir dtv/collector/report.py pour le détail.

Usage :
  python -m dtv.scripts.report [--out chemin.html] [--open]
"""
import argparse
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dtv import config
from dtv.collector import report, store


def main():
    ap = argparse.ArgumentParser(prog="dtv-report",
                                 description="Rapport HTML interactif DTV (autonome)")
    ap.add_argument("--out", help="chemin du .html (défaut data/report.html)")
    ap.add_argument("--open", action="store_true", help="ouvre dans le navigateur")
    args = ap.parse_args()

    if not Path(config.DB_PATH).exists():
        print("Base vide — lance d'abord une capture puis `dtv ingest`.")
        return
    conn = store.connect()
    out = report.generate(conn, Path(args.out) if args.out else None)
    print(f"Rapport écrit : {out}")
    if args.open:
        webbrowser.open(out.resolve().as_uri())


if __name__ == "__main__":
    main()
