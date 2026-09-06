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
    performance: float     # perf moyenne (proxy dégâts) associée à ce choix
    sample: int
    survival: float = 0.0  # taux de survie moyen des performers ayant ce choix
    winrate: Optional[float] = None   # taux de victoire (si capturé au build)


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
    surv: float = 0.0          # somme survie pondérée
    win: float = 0.0           # somme winrate pondérée (sur la part connue)
    win_w: float = 0.0         # poids ayant un winrate connu


def _rank(tally: Dict[str, _Acc]) -> List[SectorProb]:
    total = sum(a.weight for a in tally.values()) or 1.0
    out = [SectorProb(sector=s, prob=a.weight / total,
                      performance=(a.perf / a.weight) if a.weight else 0.0,
                      sample=int(a.weight),
                      survival=(a.surv / a.weight) if a.weight else 0.0,
                      winrate=(a.win / a.win_w) if a.win_w else None)
           for s, a in tally.items()]
    out.sort(key=lambda p: (p.prob, p.performance), reverse=True)
    return out


class ReplayPrior:
    """Priors d'ouverture et de transition, requêtables avec fallback de classe."""

    def __init__(self, openings: Dict[str, List[SectorProb]],
                 transitions: Dict[str, List[SectorProb]], utility=None) -> None:
        self._openings = openings          # clé "map|spawn|vc|phase"
        self._transitions = transitions    # clé "map|from|vc"
        # Utilité apprise (§8) : si fournie, opening()/next_sector() renvoient les
        # options RÉ-ORDONNÉES par avantage relatif (à la référence du groupe) et
        # filtrées par la garde de fiabilité. Sinon : ordre historique (popularité).
        self.utility = utility

    # --- Requêtes -----------------------------------------------------------
    def opening(self, map_id: str, spawn: str, vehicle_class=None,
                phase: str = "early") -> List[SectorProb]:
        vc = _vc(vehicle_class)
        for key in ("%s|%s|%s|%s" % (map_id, spawn, _vckey(vc), phase),
                    "%s|%s|*|%s" % (map_id, spawn, phase)):
            if key in self._openings:
                return self._by_utility(self._openings[key])
        return []

    def next_sector(self, map_id: str, from_sector: str,
                    vehicle_class=None) -> List[SectorProb]:
        vc = _vc(vehicle_class)
        for key in ("%s|%s|%s" % (map_id, from_sector, _vckey(vc)),
                    "%s|%s|*" % (map_id, from_sector)):
            if key in self._transitions:
                return self._by_utility(self._transitions[key])
        return []

    def _by_utility(self, options: List[SectorProb]) -> List[SectorProb]:
        """Ré-ordonne les options par utilité relative à la référence du groupe et
        écarte celles qui ne battent pas la moyenne (garde). Sans UtilityModel :
        renvoie l'ordre d'origine (popularité)."""
        if self.utility is None or not options:
            return options
        from .utility import compute_baseline
        base = compute_baseline(
            {"survival": o.survival, "damage": o.performance,
             "sample": o.sample, "winrate": o.winrate} for o in options)
        scored = []
        for o in options:
            sc = self.utility.score(
                survival=o.survival, damage=o.performance, sample=o.sample,
                baseline=base, winrate=o.winrate)
            if self.utility.passes(sc):
                scored.append((sc.value, o))
        if not scored:
            return []
        scored.sort(key=lambda t: t[0], reverse=True)
        return [o for _, o in scored]

    # --- Persistance --------------------------------------------------------
    def as_dict(self) -> dict:
        def dump(table):
            return {k: [[p.sector, round(p.prob, 4), round(p.performance, 4),
                         p.sample, round(p.survival, 4),
                         (round(p.winrate, 4) if p.winrate is not None else None)]
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

        def _row(row):
            # Rétro-compat : anciennes lignes à 4 champs (sans survie/winrate).
            s, p, pf, n = row[0], row[1], row[2], row[3]
            surv = float(row[4]) if len(row) > 4 and row[4] is not None else 0.0
            wr = float(row[5]) if len(row) > 5 and row[5] is not None else None
            return SectorProb(s, float(p), float(pf), int(n), surv, wr)

        def parse(table):
            return {k: [_row(row) for row in v] for k, v in table.items()}
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
        surv = r.survival * w
        wr = getattr(r, "win_rate", None)
        vc = _vckey(_vc(r.vehicle_class))

        def _add(a: _Acc) -> None:
            a.weight += w
            a.perf += perf
            a.surv += surv
            if wr is not None:
                a.win += wr * w
                a.win_w += w

        # Ouverture = première DESTINATION, pas le secteur de spawn : toute
        # trajectoire démarre au spawn (sectors[0]), donc l'info utile « où aller »
        # est le premier secteur atteint ensuite (sectors[1] si présent).
        first = r.sectors[1] if len(r.sectors) >= 2 else r.sectors[0]
        # Ouverture : premier secteur (clé par classe ET agnostique).
        for k in ("%s|%s|%s|%s" % (r.map_id, r.spawn, vc, r.phase),
                  "%s|%s|*|%s" % (r.map_id, r.spawn, r.phase)):
            _add(open_acc[k][first])
        # Transitions : chaque paire consécutive.
        for src, dst in zip(r.sectors, r.sectors[1:]):
            for k in ("%s|%s|%s" % (r.map_id, src, vc),
                      "%s|%s|*" % (r.map_id, src)):
                _add(trans_acc[k][dst])

    openings = {k: _rank(t) for k, t in open_acc.items()}
    transitions = {k: _rank(t) for k, t in trans_acc.items()}
    return ReplayPrior(openings, transitions)
