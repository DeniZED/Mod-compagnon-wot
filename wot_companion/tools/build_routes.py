"""Outil : extrait les ITINÉRAIRES (RouteCluster) depuis un dossier de replays.

Complète `build_tk` (zones) par les TRAJETS des bons joueurs : séquences de
secteurs (Tactical Map Model). Hors-ligne, local, en flux (mémoire bornée).

Les bornes d'arène par carte proviennent de la base de zones existante
(`tk_base.json`, emprise des zones) : indispensable pour résoudre les secteurs.
Seules les cartes ANNOTÉES (tactical_map/data/) produisent des routes.

Usage :
    python -m wot_companion.tools.build_routes replays/ --tk tk_base.json -o routes.json
    python -m wot_companion.tools.build_routes replays/ --winners-only --limit 2000
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from ..tactical_knowledge.classify import load_classifier
from ..tactical_knowledge.route_mining import build_route_clusters, save_routes
from ..tactical_knowledge.store import TacticalKnowledgeBase
from ..tactical_map import SectorResolver
from .build_tk import _iter_datasets, _iter_replay_paths, _Stats


def _bounds_from_tk(tk_path: str, resolver: SectorResolver) -> dict:
    """Bornes (minX,minZ,maxX,maxZ) par carte annotée, depuis l'emprise des zones."""
    kb = TacticalKnowledgeBase.load(tk_path)
    bounds = {}
    for map_id in resolver.graphs:              # uniquement les cartes annotées
        ext = kb.map_extent(map_id)             # (xmin,xmax,zmin,zmax) ou None
        if ext is not None:
            bounds[map_id] = (ext[0], ext[2], ext[1], ext[3])
    return bounds


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Extrait les itinéraires (replays -> JSON)")
    ap.add_argument("paths", nargs="+", help="Fichiers .wotreplay ou dossiers.")
    ap.add_argument("--tk", default="tk_base.json",
                    help="Base de zones existante (fournit les bornes d'arène).")
    ap.add_argument("--sectors", default=None,
                    help="Fichier de secteurs auto (build_sectors) : couvre toutes "
                         "les cartes, pas seulement les pilotes annotés à la main.")
    ap.add_argument("-o", "--out", default="routes.json", help="JSON de sortie.")
    ap.add_argument("--performers", type=int, default=5)
    ap.add_argument("--winners-only", action="store_true")
    ap.add_argument("--min-vehicles", type=int, default=3,
                    help="Routes validées par < N chars distincts écartées.")
    ap.add_argument("--vehicle-classes", default=None,
                    help="JSON tag->classe : routes PAR CLASSE (lights != lourds).")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--progress-every", type=int, default=200)
    args = ap.parse_args(argv)

    resolver = SectorResolver.from_dir()
    if args.sectors:
        resolver.merge_combined(args.sectors)   # ajoute les cartes auto-générées
    if not resolver.graphs:
        print("Aucune carte annotée (tactical_map/data/) — rien à extraire.")
        return 1
    if not Path(args.tk).exists():
        print("Base de zones introuvable : %s (nécessaire pour les bornes)." % args.tk)
        return 1
    bounds = _bounds_from_tk(args.tk, resolver)
    print("Cartes annotées avec bornes : %s" % (sorted(bounds) or "aucune"))
    if not bounds:
        print("Aucune borne disponible pour les cartes annotées.")
        return 1

    stats = _Stats()
    t0 = time.time()
    datasets = _iter_datasets(_iter_replay_paths(args.paths), stats, args.limit,
                              args.progress_every)
    try:
        routes = build_route_clusters(
            datasets, resolver, classifier=load_classifier(args.vehicle_classes).class_of,
            performers_per_battle=args.performers, winners_only=args.winners_only,
            min_vehicles=args.min_vehicles, bounds_by_map=bounds)
    except KeyboardInterrupt:
        print("\nInterrompu — rien n'a été écrit.")
        return 1

    if not routes:
        print("Aucune route produite (cartes annotées absentes des replays ?).")
        return 1

    save_routes(args.out, routes)
    maps = sorted({r.map_id for r in routes})
    el = time.time() - t0
    print("\n%d replays exploités (%d ignorés, %d erreurs) en %.0fs"
          % (stats.ok, stats.skip, stats.err, el))
    print("-> %d routes sur %d carte(s) : %s" % (len(routes), len(maps), maps))
    print("Routes écrites : %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
