"""Outil : condense routes.json en priors DENSES (ouverture + transition).

Les routes complètes sont trop fragmentées pour un prior direct. Cet outil en
extrait les tables exploitables en jeu :
  - ouverture : où partir depuis le spawn (par carte/spawn/classe/phase) ;
  - transition : où aller depuis un secteur donné.

Usage :
    python -m wot_companion.tools.build_priors routes.json -o priors.json
"""
from __future__ import annotations

import argparse
from pathlib import Path

from ..tactical_knowledge.replay_prior import build_priors
from ..tactical_knowledge.route_mining import load_routes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Condense les routes en priors")
    ap.add_argument("routes", help="Fichier routes.json (build_routes).")
    ap.add_argument("-o", "--out", default="priors.json", help="JSON de sortie.")
    args = ap.parse_args(argv)

    if not Path(args.routes).exists():
        print("Fichier de routes introuvable : %s" % args.routes)
        return 1
    routes = load_routes(args.routes)
    if not routes:
        print("Aucune route dans %s" % args.routes)
        return 1

    prior = build_priors(routes)
    prior.save(args.out)
    d = prior.as_dict()
    size_mb = Path(args.out).stat().st_size / 1e6
    print("%d routes -> %d ouvertures, %d transitions — %.2f Mo"
          % (len(routes), len(d["openings"]), len(d["transitions"]), size_mb))
    print("Priors écrits : %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
