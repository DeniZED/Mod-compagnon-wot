"""Outil : lit un ou plusieurs .wotreplay et affiche la verite terrain.

Hors-ligne, local. Sert a valider les donnees live (degats/assist) et, a terme,
a alimenter la Tactical Knowledge Base (Phase B).

Usage :
    python -m wot_companion.tools.replay_parse partie1.wotreplay [partie2.wotreplay ...]
    python -m wot_companion.tools.replay_parse --json parties/*.wotreplay
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from ..replays import parse_replay
from ..replays.parse import ReplayParseError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lecture de replays WoT (.wotreplay)")
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--json", action="store_true", help="Sortie JSON brute.")
    args = parser.parse_args(argv)

    summaries = []
    for path in args.paths:
        try:
            s = parse_replay(path)
        except ReplayParseError as exc:
            print("! %s : %s" % (path, exc))
            continue
        summaries.append(s)
        if args.json:
            continue
        surv = "survie" if s.survived else "mort" if s.survived is not None else "?"
        print("\n%s" % path.split("/")[-1])
        print("  %s (%s) — %s" % (s.map_label or s.map_id, s.vehicle, s.result or "?"))
        print("  degats=%d  assist=%d (radio %d / track %d)  kills=%d  spotted=%d  %s  vie=%ss"
              % (s.damage, s.assist_total, s.assist_radio, s.assist_track,
                 s.kills, s.spotted, surv, s.life_time_s))
        if s.binary_bytes:
            print("  flux positions : %d Ko (a decoder pour les trajectoires)"
                  % (s.binary_bytes // 1024))

    if args.json:
        print(json.dumps([asdict(s) for s in summaries], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
