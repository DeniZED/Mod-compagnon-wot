"""Outil : construit la Tactical Knowledge Base depuis un dossier de replays.

Hors-ligne, local, automatique. Chaîne complète : lit chaque .wotreplay, retient
les MEILLEURS joueurs de chaque partie (pas le joueur moyen), décode leurs
trajectoires, agrège en zones efficaces (PositionCluster) et écrit un JSON
portable — la « best des bases » que le compagnon interrogera à chaud.

Usage :
    python -m wot_companion.tools.build_tk replays/ -o tk_base.json
    python -m wot_companion.tools.build_tk r1.wotreplay r2.wotreplay --winners-only
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from ..replays.parse import ReplayParseError, parse_replay_full
from ..tactical_knowledge.aggregate import build_position_clusters
from ..tactical_knowledge.store import save_clusters


def _iter_replays(paths: List[str]):
    for p in paths:
        path = Path(p)
        if path.is_dir():
            yield from sorted(path.rglob("*.wotreplay"))
        elif path.suffix == ".wotreplay":
            yield path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Construit la base tactique (replays -> JSON)")
    ap.add_argument("paths", nargs="+", help="Fichiers .wotreplay ou dossiers.")
    ap.add_argument("-o", "--out", default="tk_base.json", help="Fichier JSON de sortie.")
    ap.add_argument("--cell-size", type=float, default=40.0)
    ap.add_argument("--performers", type=int, default=5,
                    help="Nb de meilleurs chars retenus par partie.")
    ap.add_argument("--winners-only", action="store_true",
                    help="N'apprendre que de l'équipe gagnante.")
    ap.add_argument("--min-samples", type=int, default=3)
    args = ap.parse_args(argv)

    datasets = []
    n_ok = n_skip = 0
    for path in _iter_replays(args.paths):
        try:
            ds = parse_replay_full(str(path))
        except ReplayParseError as exc:
            print("! %s : %s" % (path.name, exc))
            n_skip += 1
            continue
        if not ds.vehicles or not ds.trajectories:
            print("~ %s : pas de résultats/trajectoires, ignoré" % path.name)
            n_skip += 1
            continue
        datasets.append(ds)
        n_ok += 1
        print("+ %s : %s (%s) %d chars, %d trajectoires"
              % (path.name, ds.summary.map_label or ds.summary.map_id,
                 ds.summary.result, len(ds.vehicles), len(ds.trajectories)))

    if not datasets:
        print("Aucun replay exploitable.")
        return 1

    clusters = build_position_clusters(
        datasets, cell_size=args.cell_size, performers_per_battle=args.performers,
        winners_only=args.winners_only, min_samples=args.min_samples)
    save_clusters(args.out, clusters)

    maps = sorted({c.map_id for c in clusters})
    print("\n%d replays agrégés (%d ignorés) -> %d zones sur %d carte(s)"
          % (n_ok, n_skip, len(clusters), len(maps)))
    print("Base écrite : %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
