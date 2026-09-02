"""SectorResolver : projette une position live sur le secteur tactique (§5.3).

Charge les annotations JSON (une par carte), et résout `(map_id, pos, bounds)`
en `Sector`. La position monde `(x, z)` est normalisée en `(fx, fz)` avec les
bornes d'arène — même convention que `core.maps.grid_cell` — puis testée contre
les polygones.

Fallback strict (§5.4) : carte non annotée, bornes absentes ou point hors de
tout secteur → `None`. L'appelant retombe alors sur les clusters/features
existants. On ne casse jamais une carte non annotée.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional

from ..core.maps import canonical_map_id
from .models import MapEdge, MapGraph, Sector, SectorType

logger = logging.getLogger("wot_companion.tactical_map")

TM_FORMAT_VERSION = 1
_DATA_DIR = Path(__file__).with_name("data")


def _sector_from_json(map_id: str, d: dict) -> Sector:
    return Sector(
        id=d["id"], map_id=map_id,
        sector_type=SectorType(d["type"]),
        polygon=[(float(p[0]), float(p[1])) for p in d["polygon"]],
        tags=list(d.get("tags", [])),
        **{k: float(v) for k, v in (d.get("values") or {}).items()
           if k in _VALUE_KEYS},
    )


_VALUE_KEYS = {"exposure", "cover", "hull_down_value", "sniper_value",
               "spotting_value", "brawl_value", "rotation_value",
               "retreat_value", "risk_level"}


def _graph_from_json(d: dict) -> MapGraph:
    map_id = canonical_map_id(d["map_id"])
    g = MapGraph(map_id=map_id)
    for sd in d.get("sectors", []):
        g.add_sector(_sector_from_json(map_id, sd))
    for ed in d.get("edges", []):
        g.add_edge(MapEdge(
            from_id=ed["from"], to_id=ed["to"],
            distance=float(ed.get("distance", 0.5)),
            exposure=float(ed.get("exposure", 0.5)),
            retreat_possible=bool(ed.get("retreat_possible", True)),
            rotation_possible=bool(ed.get("rotation_possible", True)),
        ))
    return g


class SectorResolver:
    """Index en mémoire des graphes tactiques, requêtable par position."""

    def __init__(self, graphs: Optional[Dict[str, MapGraph]] = None) -> None:
        self.graphs: Dict[str, MapGraph] = dict(graphs or {})

    @classmethod
    def from_dir(cls, path=None) -> "SectorResolver":
        """Charge tous les `*.json` d'annotation d'un dossier (défaut : data/)."""
        directory = Path(path) if path is not None else _DATA_DIR
        graphs: Dict[str, MapGraph] = {}
        if directory.is_dir():
            for fp in sorted(directory.glob("*.json")):
                try:
                    d = json.loads(fp.read_text(encoding="utf-8"))
                    g = _graph_from_json(d)
                    graphs[g.map_id] = g
                except (OSError, ValueError, KeyError):
                    logger.exception("Annotation carte illisible: %s", fp)
        return cls(graphs)

    def graph(self, map_id) -> Optional[MapGraph]:
        return self.graphs.get(canonical_map_id(map_id))

    @staticmethod
    def _normalize(pos, bounds):
        """(x,z) monde -> (fx,fz) fraction. fx=0 ouest→1 est, fz=0 nord→1 sud.
        Retourne None si bornes absentes/incohérentes (fallback sûr)."""
        if not pos or not bounds or len(bounds) != 4:
            return None
        minx, minz, maxx, maxz = bounds
        if maxx <= minx or maxz <= minz:
            return None
        fx = (pos[0] - minx) / (maxx - minx)
        fz = (maxz - pos[1]) / (maxz - minz)
        return fx, fz

    def resolve(self, map_id, pos, bounds) -> Optional[Sector]:
        """Secteur tactique contenant `pos`, ou None (carte inconnue / hors zone)."""
        g = self.graph(map_id)
        if g is None:
            return None
        norm = self._normalize(pos, bounds)
        if norm is None:
            return None
        return g.locate_norm(norm[0], norm[1])
