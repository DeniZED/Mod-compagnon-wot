"""Outil : génère des SECTEURS pour toutes les cartes depuis la base de zones.

Annoter 72 cartes à la main est irréaliste. Cet outil DÉRIVE une grille de
secteurs par carte à partir de `tk_base.json` (zones agrégées des replays), pour
que le Tactical Map Model — et donc le route mining et l'enrichissement de
situation — couvre TOUTES les cartes jouées, pas seulement les 2 pilotes.

Les cartes annotées à la main (tactical_map/data/) restent prioritaires.

Usage :
    python -m wot_companion.tools.build_sectors --tk tk_base.json -o sectors.json
    python -m wot_companion.tools.build_sectors --tk tk_base.json --cols 6 --rows 6
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from ..tactical_knowledge.store import TacticalKnowledgeBase
from ..tactical_map.autobuild import build_graph_from_clusters, save_graphs
from ..tactical_map import SectorResolver


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Génère des secteurs auto (zones -> grille)")
    ap.add_argument("--tk", default="tk_base.json", help="Base de zones (entrée).")
    ap.add_argument("-o", "--out", default="sectors.json", help="JSON combiné (sortie).")
    ap.add_argument("--cols", type=int, default=5)
    ap.add_argument("--rows", type=int, default=5)
    ap.add_argument("--min-samples", type=int, default=5,
                    help="Support minimal (somme des échantillons) par cellule.")
    args = ap.parse_args(argv)

    if not Path(args.tk).exists():
        print("Base de zones introuvable : %s" % args.tk)
        return 1
    kb = TacticalKnowledgeBase.load(args.tk)
    if not kb.clusters:
        print("Base de zones vide.")
        return 1

    # Regroupe les zones par carte (l'index _by_map est déjà construit).
    by_map = defaultdict(list)
    for c in kb.clusters:
        by_map[c.map_id].append(c)

    # Cartes déjà annotées à la main -> on ne les auto-génère pas (priorité manuelle).
    manual = set(SectorResolver.from_dir().graphs)

    graphs = {}
    skipped_manual = 0
    for map_id, clusters in by_map.items():
        if map_id in manual:
            skipped_manual += 1
            continue
        ext = kb.map_extent(map_id)            # (xmin,xmax,zmin,zmax)
        if ext is None:
            continue
        bounds = (ext[0], ext[2], ext[1], ext[3])   # -> (minX,minZ,maxX,maxZ)
        g = build_graph_from_clusters(
            map_id, clusters, bounds, cols=args.cols, rows=args.rows,
            min_samples=args.min_samples)
        if g is not None:
            graphs[map_id] = g

    if not graphs:
        print("Aucun secteur auto généré.")
        return 1

    save_graphs(args.out, graphs)
    total = sum(len(g.sectors) for g in graphs.values())
    size_mb = Path(args.out).stat().st_size / 1e6
    print("%d cartes auto-annotées (%d ignorées car manuelles), %d secteurs — %.2f Mo"
          % (len(graphs), skipped_manual, total, size_mb))
    print("Secteurs écrits : %s" % args.out)
    print("À utiliser : build_routes --sectors %s, et côté live (branchement à venir)."
          % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
