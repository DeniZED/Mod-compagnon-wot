"""Replay Route Mining (§9, Étape 7) : extraire les ITINÉRAIRES des bons joueurs.

Au-delà des zones (où ils se placent), on apprend les TRAJETS : à ce spawn, avec
ce type de char, quelle SÉQUENCE DE SECTEURS les meilleurs enchaînent. Chaîne :

    replays parsés -> meilleurs performers -> trajectoires -> résolution en
    secteurs (Tactical Map Model) -> séquences dédupliquées -> agrégation en
    RouteCluster (usage, performance, survie, confiance).

Fair Play : connaissance HISTORIQUE agrégée, jamais une position ennemie réelle.
Local, déterministe. On n'apprend que des forts impacts (règle « best of each
battle »), et uniquement sur les cartes annotées (les autres -> aucune route,
fallback naturel sur les zones).
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from ..core.maps import canonical_map_id
from ..replays.parse import ReplayDataset
from .aggregate import phase_at
from .classify import archetype_of, default_class_of
from .models import Archetype, RouteCluster, VehicleClass

XZ = Tuple[float, float]
ROUTE_FORMAT_VERSION = 1


def _bounds_by_map(datasets: Iterable[ReplayDataset], performers_per_battle: int,
                   winners_only: bool) -> Dict[str, Tuple[float, float, float, float]]:
    """Emprise (minX,minZ,maxX,maxZ) par carte, depuis les points des performers.

    Les replays ne portent pas les bornes d'arène ; on les approxime par la boîte
    englobante des trajectoires retenues. Suffisant pour normaliser en secteurs.
    """
    acc: Dict[str, List[float]] = {}
    for ds in datasets:
        map_id = canonical_map_id(ds.summary.map_id) or "unknown"
        for v in ds.best_performers(performers_per_battle, winners_only=winners_only):
            for (_t, x, z) in ds.trajectory_of(v.vehicle_id):
                b = acc.get(map_id)
                if b is None:
                    acc[map_id] = [x, z, x, z]
                else:
                    b[0] = min(b[0], x); b[1] = min(b[1], z)
                    b[2] = max(b[2], x); b[3] = max(b[3], z)
    return {m: (b[0], b[1], b[2], b[3]) for m, b in acc.items()}


@dataclass
class _RouteAcc:
    n_veh: int = 0
    perf: float = 0.0
    survived: int = 0
    # Somme des points par étape (pour un waypoint représentatif).
    step_sum: Dict[int, List[float]] = field(default_factory=dict)  # idx -> [sx,sz,n]


def _sector_sequence(resolver, map_id, bounds, trajectory):
    """Séquence (sector_id, (x,z)) dédupliquée le long d'une trajectoire."""
    seq: List[Tuple[str, XZ]] = []
    last_id = None
    for (_t, x, z) in trajectory:
        sec = resolver.resolve(map_id, (x, z), bounds)
        if sec is None:
            continue
        if sec.id != last_id:
            seq.append((sec.id, (x, z)))
            last_id = sec.id
    return seq


def build_route_clusters(
    datasets: Iterable[ReplayDataset],
    sector_resolver,
    *,
    classifier: Callable[[Optional[str]], Optional[VehicleClass]] = default_class_of,
    performers_per_battle: int = 5,
    winners_only: bool = False,
    min_steps: int = 2,
    min_vehicles: int = 2,
    full_sample_size: int = 20,
    max_steps: int = 6,
    bounds_by_map: Optional[Dict[str, Tuple[float, float, float, float]]] = None,
) -> List[RouteCluster]:
    """Construit les RouteCluster depuis des replays parsés + un SectorResolver.

    - `min_steps` : longueur mini d'une route (nb de secteurs distincts).
    - `min_vehicles` : nb de chars distincts validant une signature (anti-bruit).
    - `full_sample_size` : saturation de la confiance.
    - `max_steps` : on tronque les très longues séquences (bruit de fin de partie).
    - `bounds_by_map` : bornes d'arène par carte (recommandé pour une résolution
      fiable des secteurs). Fournies -> traitement EN FLUX (une passe, mémoire
      bornée), les cartes absentes sont ignorées. À défaut -> on matérialise les
      replays et on approxime par l'emprise des trajectoires (union), correct à
      grande échelle mais plus gourmand.
    """
    if bounds_by_map:
        bounds = dict(bounds_by_map)     # une seule passe, flux préservé
    else:
        datasets = list(datasets)        # deux passes -> matérialisation requise
        bounds = _bounds_by_map(datasets, performers_per_battle, winners_only)

    # Clé = (map, spawn, class, archetype, phase_start, tuple(sectors)).
    routes: Dict[tuple, _RouteAcc] = defaultdict(_RouteAcc)
    # Total de routes par (map, spawn, class) pour normaliser l'usage.
    totals: Dict[tuple, int] = defaultdict(int)

    for ds in datasets:
        map_id = canonical_map_id(ds.summary.map_id) or "unknown"
        b = bounds.get(map_id)
        if b is None or sector_resolver.graph(map_id) is None:
            continue                     # carte non annotée -> pas de route
        for v in ds.best_performers(performers_per_battle, winners_only=winners_only):
            traj = ds.trajectory_of(v.vehicle_id)
            if not traj:
                continue
            seq = _sector_sequence(sector_resolver, map_id, b, traj)
            if len(seq) < min_steps:
                continue
            seq = seq[:max_steps]
            vclass = classifier(v.vehicle_type)
            arch = archetype_of(v.vehicle_type)
            phase_start = phase_at(traj[0][0])
            sig = tuple(sid for sid, _ in seq)
            spawn = "team%s" % (v.team if v.team is not None else "?")
            gkey = (map_id, spawn, vclass)
            totals[gkey] += 1
            key = (map_id, spawn, vclass, arch, phase_start, sig)
            acc = routes[key]
            acc.n_veh += 1
            acc.perf += min(v.combat_score / 3000.0, 1.0)
            acc.survived += 1 if v.survived else 0
            for i, (_sid, (x, z)) in enumerate(seq):
                s = acc.step_sum.setdefault(i, [0.0, 0.0, 0])
                s[0] += x; s[1] += z; s[2] += 1

    clusters: List[RouteCluster] = []
    for key, acc in routes.items():
        (map_id, spawn, vclass, arch, phase_start, sig) = key
        if acc.n_veh < min_vehicles:
            continue
        gkey = (map_id, spawn, vclass)
        usage = acc.n_veh / float(totals[gkey] or 1)
        waypoints = [
            (round(acc.step_sum[i][0] / acc.step_sum[i][2], 1),
             round(acc.step_sum[i][1] / acc.step_sum[i][2], 1))
            for i in sorted(acc.step_sum) if acc.step_sum[i][2] > 0
        ]
        clusters.append(RouteCluster(
            map_id=map_id, spawn=spawn, archetype=arch,
            vehicle_class=vclass, phase=phase_start, sectors=list(sig),
            waypoints=waypoints, usage_rate=min(usage, 1.0),
            performance=acc.perf / acc.n_veh,
            survival=acc.survived / acc.n_veh, damage=acc.perf / acc.n_veh,
            assist=0.0, sample_size=acc.n_veh,
            confidence=min(acc.n_veh / float(full_sample_size), 1.0),
        ))
    clusters.sort(key=lambda r: (r.usage_rate, r.performance), reverse=True)
    return clusters


# --- Persistance (JSON portable, comme la base de zones) -------------------- #
def routes_to_dict(routes: Iterable[RouteCluster]) -> dict:
    return {"format": ROUTE_FORMAT_VERSION,
            "routes": [_route_to_json(r) for r in routes]}


def _route_to_json(r: RouteCluster) -> dict:
    return {
        "map_id": r.map_id, "spawn": r.spawn,
        "archetype": r.archetype.value if r.archetype else None,
        "vehicle_class": r.vehicle_class.value if r.vehicle_class else None,
        "phase": r.phase, "sectors": list(r.sectors),
        "waypoints": [list(w) for w in r.waypoints],
        "usage_rate": r.usage_rate, "performance": r.performance,
        "survival": r.survival, "sample_size": r.sample_size,
        "confidence": r.confidence,
    }


def _route_from_json(d: dict) -> RouteCluster:
    arch = d.get("archetype")
    vclass = d.get("vehicle_class")
    return RouteCluster(
        map_id=d["map_id"], spawn=d["spawn"],
        archetype=Archetype(arch) if arch else None,
        vehicle_class=VehicleClass(vclass) if vclass else None,
        phase=d.get("phase", "early"), sectors=list(d.get("sectors", [])),
        waypoints=[(float(w[0]), float(w[1])) for w in d.get("waypoints", [])],
        usage_rate=float(d.get("usage_rate", 0.0)),
        performance=float(d.get("performance", 0.0)),
        survival=float(d.get("survival", 0.0)),
        sample_size=int(d.get("sample_size", 0)),
        confidence=float(d.get("confidence", 0.0)),
    )


def save_routes(path: str | Path, routes: Iterable[RouteCluster]) -> None:
    Path(path).write_text(json.dumps(routes_to_dict(routes), ensure_ascii=False,
                                     indent=2), encoding="utf-8")


def load_routes(path: str | Path) -> List[RouteCluster]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [_route_from_json(d) for d in data.get("routes", [])]
