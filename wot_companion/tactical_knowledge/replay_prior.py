"""Replay Prior (§ étape 8) : condense les routes en priors DENSES et exploitables.

Constat : les routes complètes (séquences de 6 secteurs) sont trop fragmentées
pour servir de prior (usage médian ~0.6 %). Le signal utile et dense est :

  - OUVERTURE : à (carte, spawn, classe, phase), vers quel PREMIER secteur les
    bons joueurs partent — « où aller depuis le spawn ».
  - TRANSITION : depuis un secteur donné, quel secteur SUIVANT ils privilégient.

On agrège les `RouteCluster` en ces deux tables, pondérées par l'échantillon et
la performance, normalisées en probabilités. Fallback de classe : une requête
sur une classe absente retombe sur l'agrégat AGNOSTIQUE (toutes classes).

Fair Play : dérivé de connaissance historique agrégée. Le prior INFORME le
scoring, il ne DÉCIDE jamais (§ « replay_prior ne doit jamais devenir la
décision finale »). Local, pur, testable.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .models import VehicleClass

PRIOR_FORMAT_VERSION = 1


@dataclass
class SectorProb:
    sector: str
    prob: float            # part (pondérée échantillon) des performers
    performance: float     # perf moyenne associée à ce choix
    sample: int


def _vc(value) -> Optional[VehicleClass]:
    if value is None:
        return None
    if isinstance(value, VehicleClass):
        return value
    try:
        return VehicleClass(str(value).lower())
    except ValueError:
        return None


def _vckey(vc: Optional[VehicleClass]) -> str:
    return vc.value if vc is not None else "*"


@dataclass
class _Acc:
    weight: float = 0.0        # somme des échantillons
    perf: float = 0.0          # somme perf pondérée


def _rank(tally: Dict[str, _Acc]) -> List[SectorProb]:
    total = sum(a.weight for a in tally.values()) or 1.0
    out = [SectorProb(sector=s, prob=a.weight / total,
                      performance=(a.perf / a.weight) if a.weight else 0.0,
                      sample=int(a.weight))
           for s, a in tally.items()]
    out.sort(key=lambda p: (p.prob, p.performance), reverse=True)
    return out


class ReplayPrior:
    """Priors d'ouverture et de transition, requêtables avec fallback de classe."""

    def __init__(self, openings: Dict[str, List[SectorProb]],
                 transitions: Dict[str, List[SectorProb]]) -> None:
        self._openings = openings          # clé "map|spawn|vc|phase"
        self._transitions = transitions    # clé "map|from|vc"

    # --- Requêtes -----------------------------------------------------------
    def opening(self, map_id: str, spawn: str, vehicle_class=None,
                phase: str = "early") -> List[SectorProb]:
        vc = _vc(vehicle_class)
        for key in ("%s|%s|%s|%s" % (map_id, spawn, _vckey(vc), phase),
                    "%s|%s|*|%s" % (map_id, spawn, phase)):
            if key in self._openings:
                return self._openings[key]
        return []

    def next_sector(self, map_id: str, from_sector: str,
                    vehicle_class=None) -> List[SectorProb]:
        vc = _vc(vehicle_class)
        for key in ("%s|%s|%s" % (map_id, from_sector, _vckey(vc)),
                    "%s|%s|*" % (map_id, from_sector)):
            if key in self._transitions:
                return self._transitions[key]
        return []

    # --- Persistance --------------------------------------------------------
    def as_dict(self) -> dict:
        def dump(table):
            return {k: [[p.sector, round(p.prob, 4), round(p.performance, 4), p.sample]
                        for p in v] for k, v in table.items()}
        return {"format": PRIOR_FORMAT_VERSION,
                "openings": dump(self._openings),
                "transitions": dump(self._transitions)}

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.as_dict(), ensure_ascii=False,
                                         indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "ReplayPrior":
        d = json.loads(Path(path).read_text(encoding="utf-8"))

        def parse(table):
            return {k: [SectorProb(s, float(p), float(pf), int(n))
                        for s, p, pf, n in v] for k, v in table.items()}
        return cls(parse(d.get("openings", {})), parse(d.get("transitions", {})))


def build_priors(routes) -> ReplayPrior:
    """Construit les priors depuis une liste de RouteCluster."""
    open_acc: Dict[str, Dict[str, _Acc]] = defaultdict(lambda: defaultdict(_Acc))
    trans_acc: Dict[str, Dict[str, _Acc]] = defaultdict(lambda: defaultdict(_Acc))

    for r in routes:
        if not r.sectors:
            continue
        w = float(max(r.sample_size, 1))
        perf = r.performance * w
        vc = _vckey(_vc(r.vehicle_class))
        # Ouverture = première DESTINATION, pas le secteur de spawn : toute
        # trajectoire démarre au spawn (sectors[0]), donc l'info utile « où aller »
        # est le premier secteur atteint ensuite (sectors[1] si présent).
        first = r.sectors[1] if len(r.sectors) >= 2 else r.sectors[0]
        # Ouverture : premier secteur (clé par classe ET agnostique).
        for k in ("%s|%s|%s|%s" % (r.map_id, r.spawn, vc, r.phase),
                  "%s|%s|*|%s" % (r.map_id, r.spawn, r.phase)):
            a = open_acc[k][first]
            a.weight += w
            a.perf += perf
        # Transitions : chaque paire consécutive.
        for src, dst in zip(r.sectors, r.sectors[1:]):
            for k in ("%s|%s|%s" % (r.map_id, src, vc),
                      "%s|%s|*" % (r.map_id, src)):
                a = trans_acc[k][dst]
                a.weight += w
                a.perf += perf

    openings = {k: _rank(t) for k, t in open_acc.items()}
    transitions = {k: _rank(t) for k, t in trans_acc.items()}
    return ReplayPrior(openings, transitions)
