"""Persistance de la Tactical Knowledge Base : PositionCluster <-> JSON.

La base est une donnée DÉRIVÉE, entièrement reconstructible depuis les replays.
On la stocke donc dans un fichier JSON portable (versionné, partageable, livrable
avec le mod) plutôt que dans la base SQLite du profil live.

Requête à chaud (§9) : `nearest_clusters()` renvoie les zones efficaces proches
d'une position, filtrées par carte/phase/archétype. 100 % connaissance historique.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, List, Optional

from .models import Archetype, PositionCluster, VehicleClass
from .utility import compute_baseline

TK_FORMAT_VERSION = 1

# Sous ce nombre de chars distincts, une référence (carte,phase,classe) est jugée
# trop mince : on retombe sur la référence agnostique de classe (carte,phase).
_BASELINE_MIN_SAMPLE = 30


def clusters_to_dict(clusters: Iterable[PositionCluster]) -> dict:
    return {
        "format": TK_FORMAT_VERSION,
        "clusters": [_cluster_to_json(c) for c in clusters],
    }


def _cluster_to_json(c: PositionCluster) -> dict:
    d = asdict(c)
    d["archetype"] = c.archetype.value if c.archetype is not None else None
    d["vehicle_class"] = c.vehicle_class.value if c.vehicle_class is not None else None
    d["center"] = list(c.center)
    return d


def _cluster_from_json(d: dict) -> PositionCluster:
    arch = d.get("archetype")
    vclass = d.get("vehicle_class")
    return PositionCluster(
        map_id=d["map_id"], spawn=d["spawn"], phase=d["phase"],
        vehicle_class=VehicleClass(vclass) if vclass else None,
        archetype=Archetype(arch) if arch else None,
        center=(float(d["center"][0]), float(d["center"][1])),
        radius=float(d["radius"]),
        popularity=float(d.get("popularity", 0.0)),
        effectiveness=float(d.get("effectiveness", 0.0)),
        damage_score=float(d.get("damage_score", 0.0)),
        assist_score=float(d.get("assist_score", 0.0)),
        survival_score=float(d.get("survival_score", 0.0)),
        winrate_score=(float(d["winrate_score"])
                       if d.get("winrate_score") is not None else None),
        sample_size=int(d.get("sample_size", 0)),
        confidence=float(d.get("confidence", 0.0)),
        vehicle_id=d.get("vehicle_id"),
    )


def save_clusters(path: str | Path, clusters: Iterable[PositionCluster]) -> None:
    payload = clusters_to_dict(clusters)
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def load_clusters(path: str | Path) -> List[PositionCluster]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [_cluster_from_json(d) for d in data.get("clusters", [])]


class TacticalKnowledgeBase:
    """Index en mémoire des zones efficaces, requêtable par proximité."""

    def __init__(self, clusters: Optional[Iterable[PositionCluster]] = None,
                 utility=None) -> None:
        self.clusters: List[PositionCluster] = list(clusters or [])
        # Index par carte : à 100k+ zones, un scan complet par tick serait trop
        # lent en live. On ne balaie que les zones de la carte courante.
        self._by_map: dict[str, List[PositionCluster]] = {}
        for c in self.clusters:
            self._by_map.setdefault(c.map_id, []).append(c)
        self._extent_cache: dict[str, tuple] = {}
        # Utilité apprise (§8) : si fournie, les zones sont notées en avantage
        # RELATIF à la référence de leur (carte, phase, classe) et filtrées par
        # une garde de fiabilité, au lieu d'un simple `effectiveness` brut.
        self.utility = utility
        self._baselines: dict = {}
        if utility is not None:
            self._build_baselines()

    def map_extent(self, map_id: str):
        """Emprise (xmin,xmax,zmin,zmax) des zones d'une carte, ou None si inconnue.

        Sert d'échelle au radar : la boîte englobante des zones ≈ l'aire jouable.
        """
        if map_id in self._extent_cache:
            return self._extent_cache[map_id]
        zones = self._by_map.get(map_id)
        if not zones:
            return None
        xs = [c.center[0] for c in zones]
        zs = [c.center[1] for c in zones]
        ext = (min(xs), max(xs), min(zs), max(zs))
        self._extent_cache[map_id] = ext
        return ext

    @classmethod
    def load(cls, path: str | Path) -> "TacticalKnowledgeBase":
        return cls(load_clusters(path))

    def save(self, path: str | Path) -> None:
        save_clusters(path, self.clusters)

    def nearest_clusters(
        self,
        map_id: str,
        pos,
        *,
        phase: Optional[str] = None,
        archetype: Optional[Archetype] = None,
        vehicle_class: Optional[VehicleClass] = None,
        max_dist: float = 120.0,
        limit: int = 3,
    ) -> List[PositionCluster]:
        """Zones efficaces proches de `pos` sur `map_id`, triées par pertinence.

        Pertinence = efficacité pondérée par la proximité (les zones lointaines
        pèsent moins) et la correspondance de classe. Filtres optionnels : phase,
        archétype exact, classe de véhicule.

        Correspondance de classe : une zone de la MÊME classe est préférée ; une
        zone AGNOSTIQUE (classe None) reste éligible en repli (léger malus) ; une
        zone d'une AUTRE classe est exclue. Sans classe demandée, tout est éligible.
        """
        x, z = pos
        scored = []
        for c in self._by_map.get(map_id, ()):   # index carte : balayage ciblé
            if phase is not None and c.phase != phase:
                continue
            if archetype is not None and c.archetype != archetype:
                continue
            class_factor = 1.0
            if vehicle_class is not None:
                if c.vehicle_class == vehicle_class:
                    class_factor = 1.0
                elif c.vehicle_class is None:
                    class_factor = 0.75          # zone agnostique : repli acceptable
                else:
                    continue                     # autre classe : hors sujet
            dx, dz = c.center[0] - x, c.center[1] - z
            dist = (dx * dx + dz * dz) ** 0.5
            if dist > max_dist:
                continue
            proximity = 1.0 - dist / max_dist
            if self.utility is not None:
                # Utilité RELATIVE : avantage sur la référence, garde de fiabilité.
                sc = self._utility_of(c)
                if sc is None or not self.utility.passes(sc):
                    continue                     # sous la référence / non prouvé
                merit = sc.value * sc.confidence
            else:
                merit = c.effectiveness * c.confidence
            relevance = merit * (0.4 + 0.6 * proximity) * class_factor
            scored.append((relevance, dist, c))
        scored.sort(key=lambda t: (-t[0], t[1]))
        return [c for _, _, c in scored[:limit]]

    # ---- Utilité apprise (§8) ------------------------------------------------
    @staticmethod
    def _row(c: PositionCluster) -> dict:
        """Ligne de métriques d'une zone pour l'utilité/la référence.

        `effectiveness` sert de proxy dégâts (impact combat normalisé) : commun à
        toutes les zones, donc comparable en avantage relatif même sur une base
        antérieure sans winrate."""
        return {"survival": c.survival_score, "damage": c.effectiveness,
                "sample": c.sample_size,
                "winrate": getattr(c, "winrate_score", None)}

    def _build_baselines(self) -> None:
        """Références moyennes par (carte, phase, classe) + repli (carte, phase)."""
        groups: dict = {}
        pooled: dict = {}
        for c in self.clusters:
            groups.setdefault((c.map_id, c.phase, c.vehicle_class), []).append(
                self._row(c))
            pooled.setdefault((c.map_id, c.phase), []).append(self._row(c))
        self._baselines = {k: compute_baseline(v) for k, v in groups.items()}
        self._pooled_baselines = {k: compute_baseline(v) for k, v in pooled.items()}

    def _baseline_for(self, c: PositionCluster):
        b = self._baselines.get((c.map_id, c.phase, c.vehicle_class))
        if b is not None and b.sample >= _BASELINE_MIN_SAMPLE:
            return b
        return self._pooled_baselines.get((c.map_id, c.phase)) or b

    def _utility_of(self, c: PositionCluster):
        base = self._baseline_for(c)
        if base is None:
            return None
        r = self._row(c)
        return self.utility.score(
            survival=r["survival"], damage=r["damage"], sample=r["sample"],
            baseline=base, winrate=r["winrate"])
