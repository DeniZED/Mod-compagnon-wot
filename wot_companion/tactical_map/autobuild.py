"""Auto-génération de secteurs depuis la base de zones (couvre les 72 cartes).

Annoter 72 cartes à la main est irréaliste. Mais on dispose déjà, par carte, des
`PositionCluster` agrégés depuis les replays (efficacité, survie, spotting…). On
en DÉRIVE une grille de secteurs : chaque cellule reçoit des valeurs tactiques
issues des zones qui y tombent. Grossier mais réel et data-driven, et surtout
disponible PARTOUT — les cartes annotées à la main restent des overrides de
meilleure qualité.

Fair Play : purement dérivé de connaissance historique agrégée, jamais une
position ennemie. Local, déterministe.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .models import MapGraph, Sector, SectorType

Bounds = Tuple[float, float, float, float]     # (minX, minZ, maxX, maxZ)
AUTO_FORMAT_VERSION = 1


def _infer_type(assist: float, survival: float, effectiveness: float) -> SectorType:
    """Type tactique approché à partir des signaux statistiques disponibles."""
    if assist >= 0.5 and assist >= effectiveness:
        return SectorType.SPOTTING_ZONE
    if survival >= 0.6 and effectiveness >= 0.4:
        return SectorType.RIDGE            # tient bien + performe = crête/hull-down
    if survival < 0.4 and effectiveness >= 0.4:
        return SectorType.SNIPER_LINE      # performe mais meurt = ligne exposée
    return SectorType.TRANSITION


def build_graph_from_clusters(
    map_id: str, clusters: Iterable, bounds: Bounds,
    *, cols: int = 5, rows: int = 5, min_samples: int = 5,
) -> Optional[MapGraph]:
    """Construit un MapGraph en grille cols×rows depuis les zones d'une carte.

    Chaque cellule agrège (pondéré par sample_size) l'efficacité/survie/assist des
    zones qui y tombent ; une cellule sans support suffisant est omise (le
    résolveur renverra None -> fallback). Retourne None si la carte n'a rien.
    """
    minx, minz, maxx, maxz = bounds
    if maxx <= minx or maxz <= minz:
        return None

    # Accumulateurs par cellule (col, row).
    acc: Dict[Tuple[int, int], List[float]] = defaultdict(
        lambda: [0.0, 0.0, 0.0, 0.0, 0])  # [eff, surv, dmg, assist, samples] pondérés
    for c in clusters:
        fx = (c.center[0] - minx) / (maxx - minx)
        fz = (maxz - c.center[1]) / (maxz - minz)
        if not (0.0 <= fx <= 1.0 and 0.0 <= fz <= 1.0):
            continue
        col = min(cols - 1, max(0, int(fx * cols)))
        row = min(rows - 1, max(0, int(fz * rows)))
        w = float(max(c.sample_size, 1))
        a = acc[(col, row)]
        a[0] += c.effectiveness * w
        a[1] += c.survival_score * w
        a[2] += c.damage_score * w
        a[3] += c.assist_score * w
        a[4] += c.sample_size

    g = MapGraph(map_id=map_id)
    for (col, row), a in acc.items():
        if a[4] < min_samples:
            continue
        # Chaque champ a été pondéré par sample_size ; on divise par leur somme.
        denom = float(a[4]) if a[4] else 1.0
        eff = min(a[0] / denom, 1.0)
        surv = min(a[1] / denom, 1.0)
        assist = min(a[3] / denom, 1.0)
        stype = _infer_type(assist, surv, eff)
        x0, x1 = col / cols, (col + 1) / cols
        z0, z1 = row / rows, (row + 1) / rows
        g.add_sector(Sector(
            id="auto_c%dr%d" % (col, row), map_id=map_id, sector_type=stype,
            polygon=[(x0, z0), (x1, z0), (x1, z1), (x0, z1)],
            tags=["auto"],
            exposure=min(1.0, 1.0 - surv + 0.2), cover=surv,
            hull_down_value=min(1.0, surv * (0.5 + eff)),
            sniper_value=eff, spotting_value=assist,
            brawl_value=max(0.0, 1.0 - assist - 0.2 * eff),
            rotation_value=0.5, retreat_value=surv, risk_level=min(1.0, 1.0 - surv),
        ))
    return g if g.sectors else None


# --- Fichier combiné multi-cartes (artefact utilisateur, non versionné) ------ #
def graphs_to_dict(graphs: Dict[str, MapGraph]) -> dict:
    out = {}
    for map_id, g in graphs.items():
        out[map_id] = {
            "map_id": map_id,
            "sectors": [{
                "id": s.id, "type": s.sector_type.value,
                "polygon": [list(p) for p in s.polygon], "tags": list(s.tags),
                "values": {
                    "exposure": s.exposure, "cover": s.cover,
                    "hull_down_value": s.hull_down_value,
                    "sniper_value": s.sniper_value, "spotting_value": s.spotting_value,
                    "brawl_value": s.brawl_value, "rotation_value": s.rotation_value,
                    "retreat_value": s.retreat_value, "risk_level": s.risk_level,
                },
            } for s in g.sectors.values()],
            "edges": [],
        }
    return {"format": AUTO_FORMAT_VERSION, "maps": out}


def save_graphs(path: str | Path, graphs: Dict[str, MapGraph]) -> None:
    Path(path).write_text(json.dumps(graphs_to_dict(graphs), ensure_ascii=False,
                                     indent=2), encoding="utf-8")
