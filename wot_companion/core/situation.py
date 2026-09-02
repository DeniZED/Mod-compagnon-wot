"""SituationState (§10, Étape 4) : structure tactique centrale et unifiée.

Consolide en UN objet ce que les différentes briques savent de l'instant :
- contexte live (phase, HP, écart numérique global) — depuis BattleContext/Features ;
- secteur tactique (géographie) — depuis le Tactical Map Model (optionnel) ;
- profil du char (comment il préfère combattre) — depuis Vehicle Profiles (optionnel) ;
- lecture LOCALE (alliés/ennemis proches) et une force locale (§7).

But : les règles et le scoring consommeront progressivement CETTE structure au
lieu d'aller piocher partout. Introduit À CÔTÉ de Features (pas de remplacement).

Principe cardinal (§10) : toute donnée absente reste optionnelle — AUCUNE
invention. Fair Play : uniquement données autorisées (position propre, alliés,
ennemis déjà spottés, écart numérique, HP, métadonnées char visibles).

CONTRAINTE DE DONNÉES connue (§7, §20) : le feed live ne fournit PAS les HP des
alliés ni des ennemis, ni l'identité des ennemis spottés. La force locale est
donc bâtie sur les COMPTES de proximité + les HP/puissance PROPRES uniquement ;
les champs HP adverses restent None (à activer si une source fiable apparaît).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from ..tactical_knowledge.models import Archetype, VehicleClass, VehicleTacticalProfile
from ..tactical_knowledge.vehicle_profiles import resolve_profile

XZ = Tuple[float, float]


@dataclass
class SituationState:
    battle_phase: str

    # Position / secteur -----------------------------------------------------
    player_position: Optional[XZ] = None
    player_sector_id: Optional[str] = None
    player_sector_type: Optional[str] = None

    # Véhicule ---------------------------------------------------------------
    vehicle_id: Optional[str] = None
    vehicle_class: Optional[VehicleClass] = None
    vehicle_archetype: Optional[Archetype] = None
    vehicle_profile: Optional[VehicleTacticalProfile] = None
    profile_source: Optional[str] = None
    profile_confidence: float = 0.0

    # HP --------------------------------------------------------------------
    player_hp_ratio: Optional[float] = None

    # Global ----------------------------------------------------------------
    global_alive_delta: Optional[int] = None      # allies_alive - enemies_alive

    # Local (proximité, feed minimap) ---------------------------------------
    local_allies: int = 0
    local_visible_enemies: int = 0
    support_distance: Optional[float] = None       # allié le plus proche (m)
    support_level: float = 0.0                     # 0..1 (soutien immédiat)
    # Force locale (§7). None si aucune lecture locale possible.
    local_strength_delta: Optional[float] = None
    # HP adverses/alliés indisponibles dans le feed -> restent None (§7, §20).
    local_ally_hp: Optional[float] = None
    local_visible_enemy_hp: Optional[float] = None

    # Terrain (depuis le secteur, si annoté) --------------------------------
    exposure: Optional[float] = None
    cover: Optional[float] = None
    retreat_quality: Optional[float] = None
    rotation_quality: Optional[float] = None

    # Synthèse --------------------------------------------------------------
    sector_status: Optional[str] = None            # calm / contested / pressured
    overextended: bool = False
    isolated: bool = False
    tactical_confidence: float = 0.0               # confiance globale de la lecture

    missing: set = field(default_factory=set)      # champs absents (audit)


# --- Constantes de lecture -------------------------------------------------- #
_SUPPORT_RADIUS_M = 160.0     # aligné sur features.SUPPORT_RADIUS_M


def _support_level(nearest: Optional[float]) -> float:
    """0..1 : 1 = un allié au contact, 0 = aucun allié à portée de soutien."""
    if nearest is None:
        return 0.0
    if nearest >= _SUPPORT_RADIUS_M:
        return 0.0
    return 1.0 - nearest / _SUPPORT_RADIUS_M


def _local_strength(local_allies: int, local_enemies: int,
                    own_hp: Optional[float], own_power: float) -> Optional[float]:
    """Force locale (§7) — HONNÊTE vu les données disponibles.

    On N'A PAS les HP/puissance des autres chars : la force locale reste donc
    fondée sur les COMPTES de proximité, corrigés par sa PROPRE présence (HP ×
    puissance du char). Positif = supériorité locale, négatif = infériorité.

    Retourne None si aucune lecture locale (personne de proche des deux côtés).
    """
    if local_allies == 0 and local_enemies == 0:
        return None
    # Sa propre présence vaut entre 0 (mort) et ~1.2 (full HP, char puissant).
    self_presence = 0.0
    if own_hp is not None:
        self_presence = own_hp * (0.6 + 0.6 * own_power)
    return (local_allies + self_presence) - local_enemies


def _sector_status(local_enemies: int, exposure: Optional[float]) -> Optional[str]:
    if local_enemies >= 2:
        return "pressured"
    if local_enemies == 1:
        return "contested"
    if exposure is not None and exposure >= 0.75:
        return "exposed"
    return "calm"


def build_situation(battle, features, *, sector_resolver=None,
                    profile_resolver=None) -> SituationState:
    """Assemble un `SituationState` à partir du contexte + features + résolveurs.

    `sector_resolver` (Tactical Map Model) et `profile_resolver` (Vehicle
    Profiles) sont optionnels : absents, les champs correspondants restent None /
    valeurs par défaut (fallback sûr, aucune carte cassée).
    """
    phase = getattr(features, "phase", None)
    phase_name = getattr(phase, "value", "mid") if phase is not None else "mid"

    st = SituationState(battle_phase=phase_name)
    st.player_position = getattr(battle, "own_pos", None)
    st.player_hp_ratio = getattr(battle, "hp_ratio", None)
    st.overextended = bool(getattr(features, "overextended", False))
    st.isolated = bool(getattr(features, "isolated", False))

    a_alive = getattr(battle, "allies_alive", None)
    e_alive = getattr(battle, "enemies_alive", None)
    if a_alive is not None and e_alive is not None:
        st.global_alive_delta = a_alive - e_alive
    else:
        st.missing.add("global_alive_delta")

    # --- Véhicule : profil tactique via fallback exact->archétype->classe ----
    vclass_raw = getattr(battle, "vehicle_class", None)
    vid = getattr(battle, "vehicle_id", None)
    resolver = profile_resolver
    res = (resolver.resolve(vehicle_id=vid, vehicle_class=vclass_raw)
           if resolver is not None
           else resolve_profile(vehicle_id=vid, vehicle_class=vclass_raw))
    st.vehicle_profile = res.profile
    st.vehicle_id = res.profile.vehicle_id
    st.vehicle_class = res.profile.vehicle_class
    st.vehicle_archetype = res.profile.archetype
    st.profile_source = res.source
    st.profile_confidence = res.confidence

    # --- Lecture locale (proximité) -----------------------------------------
    st.local_allies = int(getattr(features, "allies_near", 0) or 0)
    st.local_visible_enemies = int(getattr(features, "enemies_spotted_near", 0) or 0)
    st.support_distance = getattr(features, "nearest_ally_dist", None)
    st.support_level = _support_level(st.support_distance)
    own_power = 0.5
    if st.vehicle_profile is not None:
        # « Puissance » offensive grossière : dpm + alpha + précision.
        own_power = (st.vehicle_profile.dpm + st.vehicle_profile.alpha
                     + st.vehicle_profile.accuracy) / 3.0
    st.local_strength_delta = _local_strength(
        st.local_allies, st.local_visible_enemies, st.player_hp_ratio, own_power)

    # --- Secteur tactique (si annoté) ---------------------------------------
    bounds = getattr(battle, "map_bounds", None)
    map_id = getattr(battle, "map_id", None)
    if sector_resolver is not None and st.player_position is not None:
        sector = sector_resolver.resolve(map_id, st.player_position, bounds)
        if sector is not None:
            st.player_sector_id = sector.id
            st.player_sector_type = sector.sector_type.value
            st.exposure = sector.exposure
            st.cover = sector.cover
            st.retreat_quality = sector.retreat_value
            st.rotation_quality = sector.rotation_value
        else:
            st.missing.add("player_sector")

    st.sector_status = _sector_status(st.local_visible_enemies, st.exposure)

    # --- Confiance globale de la lecture ------------------------------------
    # Combine confiance du profil et disponibilité des données clés.
    conf = st.profile_confidence
    if st.global_alive_delta is not None:
        conf += 0.1
    if st.player_position is not None:
        conf += 0.1
    if st.player_sector_id is not None:
        conf += 0.1
    st.tactical_confidence = min(1.0, conf)

    return st
