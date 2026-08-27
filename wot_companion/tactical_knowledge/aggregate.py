"""Agrégation replays -> PositionCluster (Tactical Knowledge Base, §9/§23).

Chaîne : parse_replay_full() -> meilleurs joueurs -> leurs trajectoires ->
clustering spatial par (carte, phase, CLASSE) -> zones efficaces.

Principe Fair Play : on n'agrège QUE de la connaissance historique (où les bons
joueurs se placent et performent). Aucune position live, aucune présence réelle.
On n'apprend jamais du joueur moyen : seuls les meilleurs impacts de chaque
partie alimentent la base (règle « best of each battle »).

Le regroupement se fait par CLASSE de véhicule (medium, heavy, ...). Un char dont
le tag n'est pas classé alimente les zones AGNOSTIQUES (classe = None) plutôt que
d'être ignoré : « les gagnants jouent ici ». Ainsi aucun replay n'est perdu, même
sans table de classes exhaustive (voir `classify.VehicleClassifier`).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from ..core.maps import canonical_map_id
from ..replays.parse import ReplayDataset, VehicleResult
from .classify import archetype_of, default_class_of
from .models import Archetype, PositionCluster, VehicleClass

XZ = Tuple[float, float]

# Bornes de phase alignées sur core.context.features (EARLY<=150s, MID<=480s).
_EARLY_MAX_S = 150.0
_MID_MAX_S = 480.0


def phase_at(t_s: float) -> str:
    if t_s <= _EARLY_MAX_S:
        return "early"
    if t_s <= _MID_MAX_S:
        return "mid"
    return "late"


@dataclass
class _Cell:
    """Accumulateur d'une cellule de grille pour une clé (carte, phase, archétype).

    Uniquement des compteurs scalaires : aucune structure ne croît avec le nombre
    de replays (impératif à l'échelle de dizaines de milliers de parties). La
    déduplication char↔cellule se fait dans la boucle, pas ici.
    """
    sx: float = 0.0            # somme pondérée des x
    sz: float = 0.0
    weight: float = 0.0        # somme des poids (impact combat)
    points: int = 0            # nb de points bruts
    n_veh: int = 0             # nb de chars distincts ayant contribué
    dmg: float = 0.0           # somme impact des chars contributeurs (dédupliqué)
    survived: int = 0


def _sample_cluster(
    datasets: Iterable[ReplayDataset],
    classifier: Callable[[Optional[str]], Optional[VehicleClass]],
    performers_per_battle: int,
    winners_only: bool,
) -> Iterable[Tuple[str, str, Optional[VehicleClass], str, VehicleResult, XZ]]:
    """Génère (map_id, spawn, classe|None, phase, résultat, (x,z)) point par point."""
    for ds in datasets:
        map_id = canonical_map_id(ds.summary.map_id) or "unknown"
        best = ds.best_performers(performers_per_battle, winners_only=winners_only)
        for v in best:
            vclass = classifier(v.vehicle_type)   # None = zone agnostique de classe
            spawn = "team%s" % (v.team if v.team is not None else "?")
            for (t, x, z) in ds.trajectory_of(v.vehicle_id):
                yield map_id, spawn, vclass, phase_at(t), v, (x, z)


def build_position_clusters(
    datasets: Iterable[ReplayDataset],
    *,
    classifier: Callable[[Optional[str]], Optional[VehicleClass]] = default_class_of,
    cell_size: float = 40.0,
    performers_per_battle: int = 5,
    winners_only: bool = False,
    min_samples: int = 3,
    full_sample_size: int = 40,
) -> List[PositionCluster]:
    """Construit les PositionCluster depuis un lot de replays déjà parsés.

    - `classifier` : tag -> VehicleClass (None => zone agnostique de classe).
    - `cell_size` : côté (m) de la grille de clustering.
    - `performers_per_battle` : combien de meilleurs chars retenir par partie.
    - `winners_only` : n'apprendre que de l'équipe gagnante.
    - `min_samples` : nb minimal de points pour émettre une zone (anti-bruit).
    - `full_sample_size` : nb de chars distincts au-delà duquel la confiance sature.
    """
    cells: Dict[Tuple[str, str, Optional[VehicleClass], str, int, int], _Cell] = \
        defaultdict(_Cell)
    # Archétype dominant par cellule (métadonnée d'affinage), si classable.
    arch_vote: Dict[tuple, Dict[Archetype, int]] = defaultdict(lambda: defaultdict(int))
    # Déduplication char↔cellule à mémoire bornée : les points d'un même char
    # arrivent consécutivement (voir _sample_cluster), donc il suffit de retenir
    # les cellules du char COURANT ; on remet à zéro au changement de char.
    cur_vid = None
    seen_cells: set = set()
    for map_id, spawn, vclass, phase, v, (x, z) in _sample_cluster(
        datasets, classifier, performers_per_battle, winners_only
    ):
        if v.vehicle_id != cur_vid:
            cur_vid = v.vehicle_id
            seen_cells = set()
        gx, gz = int(x // cell_size), int(z // cell_size)
        key = (map_id, spawn, vclass, phase, gx, gz)
        c = cells[key]
        w = float(max(v.combat_score, 1))
        c.sx += x * w
        c.sz += z * w
        c.weight += w
        c.points += 1
        if key not in seen_cells:
            seen_cells.add(key)
            c.n_veh += 1
            c.dmg += v.combat_score
            c.survived += 1 if v.survived else 0
            arch = archetype_of(v.vehicle_type)
            if arch is not None:
                arch_vote[key][arch] += 1

    # Normalisation : popularité relative au max de points dans la même (carte,phase).
    max_points: Dict[Tuple[str, str], int] = defaultdict(int)
    for (map_id, spawn, vclass, phase, _gx, _gz), c in cells.items():
        mp = (map_id, phase)
        if c.points > max_points[mp]:
            max_points[mp] = c.points

    clusters: List[PositionCluster] = []
    for key, c in cells.items():
        (map_id, spawn, vclass, phase, _gx, _gz) = key
        if c.points < min_samples or c.weight <= 0:
            continue
        cx, cz = c.sx / c.weight, c.sz / c.weight
        n_veh = c.n_veh or 1
        avg_impact = c.dmg / n_veh
        popularity = c.points / float(max_points[(map_id, phase)] or 1)
        survival = c.survived / float(n_veh)
        # 3000 d'impact combat ~ excellent -> ancre la normalisation.
        effectiveness = min(avg_impact / 3000.0, 1.0)
        # Confiance = nb de chars DISTINCTS (≈ parties) ayant validé la zone,
        # pas le nb de points bruts : robuste à l'échantillonnage des trajectoires.
        confidence = min(n_veh / float(full_sample_size), 1.0)
        votes = arch_vote.get(key)
        archetype = max(votes, key=votes.get) if votes else None
        clusters.append(PositionCluster(
            map_id=map_id, spawn=spawn, phase=phase,
            vehicle_class=vclass, archetype=archetype,
            center=(round(cx, 1), round(cz, 1)), radius=cell_size / 2.0,
            popularity=popularity, effectiveness=effectiveness,
            damage_score=effectiveness, assist_score=0.0,
            survival_score=survival, sample_size=c.points, confidence=confidence,
        ))
    clusters.sort(key=lambda k: (k.effectiveness, k.popularity), reverse=True)
    return clusters
