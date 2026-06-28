"""
Diagnostic rapide : affiche les prix HDV capturés pour un item (tous tiers).
Usage : python -m dtv.scripts.check_hdv Blé
        python -m dtv.scripts.check_hdv 4532        # par GID
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dtv import config
from dtv.collector import store


def main():
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    if not query:
        print("Usage: python -m dtv.scripts.check_hdv <nom ou GID>")
        sys.exit(1)

    conn = store.connect()

    if query.isdigit():
        gid = int(query)
    else:
        rows = conn.execute(
            "SELECT DISTINCT gid, nom FROM hdv_offers WHERE nom LIKE ? ORDER BY ts DESC LIMIT 5",
            (f"%{query}%",),
        ).fetchall()
        if not rows:
            rows = conn.execute(
                "SELECT DISTINCT gid, nom FROM avg_prices WHERE nom LIKE ? ORDER BY ts DESC LIMIT 5",
                (f"%{query}%",),
            ).fetchall()
        if not rows:
            print(f"Aucun item ne correspond a '{query}' dans la base.")
            sys.exit(1)
        if len(rows) > 1:
            print("Plusieurs correspondances :")
            for r in rows:
                print(f"  GID {r['gid']} - {r['nom']}")
            print("Relance avec le GID exact.")
            sys.exit(0)
        gid = rows[0]["gid"]
        print(f"Item : {rows[0]['nom']} (GID {gid})\n")

    hdv = conn.execute(
        "SELECT ts, prix_x1, prix_x10, prix_x100, prix_x1000, nb_offres "
        "FROM hdv_offers WHERE gid=? ORDER BY ts DESC LIMIT 10",
        (gid,),
    ).fetchall()

    if not hdv:
        print(f"Aucune offre HDV capturee pour GID {gid}.")
        print("Ouvre cet item dans l'HDV pendant une capture pour relever ses prix.")
    else:
        print(f"  {'Date':19s}  {'x1':>8s}  {'x10':>8s}  {'x100':>8s}  {'x1000':>8s}  Offres")
        print("  " + "-" * 65)
        for r in hdv:
            def f(v):
                return str(v) if v else "-"
            print(f"  {(r['ts'] or '')[:19]:19s}  {f(r['prix_x1']):>8s}  "
                  f"{f(r['prix_x10']):>8s}  {f(r['prix_x100']):>8s}  "
                  f"{f(r['prix_x1000']):>8s}  {r['nb_offres'] or 0}")

    avg = conn.execute(
        "SELECT ts, price FROM avg_prices WHERE gid=? ORDER BY ts DESC LIMIT 3",
        (gid,),
    ).fetchall()
    if avg:
        print(f"\n  Prix moyen serveur (avgprice) :")
        for r in avg:
            print(f"    {(r['ts'] or '')[:19]}  {r['price']} kamas")


if __name__ == "__main__":
    main()
