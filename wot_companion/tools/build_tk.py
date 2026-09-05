"""Outil : construit la Tactical Knowledge Base depuis un dossier de replays.

Hors-ligne, local, automatique. Chaîne complète : lit chaque .wotreplay, retient
les MEILLEURS joueurs de chaque partie (pas le joueur moyen), décode leurs
trajectoires, agrège en zones efficaces (PositionCluster) et écrit un JSON
portable — la « best des bases » que le compagnon interrogera à chaud.

Conçu pour PASSER À L'ÉCHELLE (dizaines de milliers de replays) : les parties
sont traitées en flux, une à la fois, sans jamais toutes les charger en mémoire.

Usage :
    python -m wot_companion.tools.build_tk replays/ -o tk_base.json
    python -m wot_companion.tools.build_tk replays/ --winners-only --limit 2000
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Iterator, List

from ..replays.parse import ReplayParseError, parse_replay_full
from ..tactical_knowledge.aggregate import build_position_clusters
from ..tactical_knowledge.classify import load_classifier
from ..tactical_knowledge.store import save_clusters


def _iter_replay_paths(paths: List[str]) -> Iterator[Path]:
    for p in paths:
        path = Path(p)
        if path.is_dir():
            yield from sorted(path.rglob("*.wotreplay"))
        elif path.suffix == ".wotreplay":
            yield path


class _Stats:
    def __init__(self) -> None:
        self.ok = self.skip = self.err = 0


def _iter_datasets(paths: Iterator[Path], stats: _Stats, limit: int | None,
                   progress_every: int):
    """Génère les ReplayDataset exploitables, en flux (mémoire bornée)."""
    t0 = time.time()
    seen = 0
    for path in paths:
        if limit is not None and seen >= limit:
            break
        seen += 1
        try:
            ds = parse_replay_full(str(path))
        except ReplayParseError:
            stats.skip += 1
            continue
        except Exception:
            stats.err += 1
            continue
        if not ds.vehicles or not ds.trajectories:
            stats.skip += 1       # replay sans résultats ou format non décodable
            continue
        stats.ok += 1
        yield ds
        if progress_every and seen % progress_every == 0:
            el = time.time() - t0
            rate = seen / el if el else 0
            print("  ... %d parcourus (%d exploitables) — %.0f/s"
                  % (seen, stats.ok, rate))


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
    ap.add_argument("--min-vehicles", type=int, default=1,
                    help="Zones validées par < N chars distincts écartées "
                         "(8+ recommandé à grande échelle pour un fichier léger).")
    ap.add_argument("--limit", type=int, default=None,
                    help="Ne traiter que les N premiers replays (test rapide).")
    ap.add_argument("--progress-every", type=int, default=200)
    ap.add_argument("--vehicle-classes", default=None,
                    help="JSON tag->classe (capture live du roster) : active le "
                         "clustering PAR CLASSE au lieu de tout-agnostique.")
    args = ap.parse_args(argv)
    classifier = load_classifier(args.vehicle_classes)

    stats = _Stats()
    t0 = time.time()
    print("Lecture des replays en flux (Ctrl-C pour arrêter proprement)...")
    datasets = _iter_datasets(
        _iter_replay_paths(args.paths), stats, args.limit, args.progress_every)

    # L'agrégateur consomme le flux sans le matérialiser : un seul replay vit
    # en mémoire à la fois, seuls les accumulateurs de cellules sont conservés.
    try:
        clusters = build_position_clusters(
            datasets, classifier=classifier.class_of, cell_size=args.cell_size,
            performers_per_battle=args.performers, winners_only=args.winners_only,
            min_samples=args.min_samples, min_vehicles=args.min_vehicles)
    except KeyboardInterrupt:
        print("\nInterrompu — rien n'a été écrit.")
        return 1

    if not clusters:
        print("Aucune zone produite (aucun replay exploitable ?).")
        return 1

    save_clusters(args.out, clusters)
    maps = sorted({c.map_id for c in clusters})
    el = time.time() - t0
    size_mb = Path(args.out).stat().st_size / 1e6
    print("\n%d replays exploités (%d ignorés, %d erreurs) en %.0fs"
          % (stats.ok, stats.skip, stats.err, el))
    print("-> %d zones sur %d carte(s) — fichier %.1f Mo" % (len(clusters), len(maps), size_mb))
    print("Base écrite : %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
