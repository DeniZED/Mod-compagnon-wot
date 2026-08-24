"""Whitelist explicite des types d'evenements et champs consommables.

Base sur l'annexe B (Matrice Fair Play de conception) du cahier des charges.
Regle d'or : tout ce qui n'est pas explicitement autorise est refuse.
"""
from __future__ import annotations

from enum import Enum

from ..events import EventType


class FairPlayClass(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"


# Pour chaque type d'evenement autorise, la liste blanche des champs de payload.
# Un champ absent de cette liste est considere comme non autorise -> rejet.
WHITELIST: dict[str, frozenset[str]] = {
    EventType.BATTLE_START.value: frozenset({"battle_id", "arena_id"}),
    EventType.BATTLE_END.value: frozenset({"battle_id", "reason"}),
    # Contexte propre au joueur
    EventType.PLAYER_VEHICLE.value: frozenset({"vehicle_id", "tier", "class", "role"}),
    EventType.MAP_INFO.value: frozenset({"map_id"}),
    EventType.SPAWN_INFO.value: frozenset({"spawn"}),
    # Composition connue au chargement : classes/tiers agreges uniquement.
    EventType.TEAM_COMPOSITION.value: frozenset({
        "ally_classes", "enemy_classes", "ally_tiers", "enemy_tiers",
        "ally_count", "enemy_count",
    }),
    # Etat temps reel : informations propres ou normalement visibles.
    EventType.PLAYER_HP_CHANGED.value: frozenset({"hp_ratio", "hp", "max_hp"}),
    EventType.PLAYER_DAMAGE_DEALT.value: frozenset({"damage", "total_damage"}),
    EventType.PLAYER_ASSIST.value: frozenset({"assist", "total_assist"}),
    EventType.PLAYER_POSITION.value: frozenset({"sector", "flank"}),
    EventType.ALLY_DESTROYED.value: frozenset({"flank", "allies_alive"}),
    EventType.ENEMY_DESTROYED.value: frozenset({"enemies_alive"}),
    EventType.TEAM_COUNT.value: frozenset({"allies_alive", "enemies_alive"}),
    EventType.CLOCK_TICK.value: frozenset({"elapsed_s", "remaining_s"}),
    EventType.BATTLE_RESULT.value: frozenset({
        "result", "damage", "assist", "survived", "kills", "hp_ratio_end",
    }),
}


def is_event_allowed(event_type: str) -> bool:
    """Un type d'evenement est autorise s'il figure explicitement dans la whitelist."""
    return event_type in WHITELIST


def allowed_fields(event_type: str) -> frozenset[str]:
    return WHITELIST.get(event_type, frozenset())


def is_field_allowed(event_type: str, field_name: str) -> bool:
    return field_name in WHITELIST.get(event_type, frozenset())
