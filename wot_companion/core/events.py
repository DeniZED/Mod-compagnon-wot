"""Modele d'evenements normalises (RawEvent) et types autorises.

Un `RawEvent` est le seul point d'entree du moteur. Il est produit par un
GameAdapter (client reel) ou par le simulateur, puis passe imperativement par
le FairPlayFilter avant d'atteindre le BattleContext.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """Types d'evenements consommables par le moteur.

    IMPORTANT Fair Play : cette enumeration ne contient QUE des informations
    normalement disponibles au joueur. Aucun type ne represente une donnee
    ennemie cachee (reload adverse, position non spot, direction de canon...).
    """
    # Cycle de vie de la bataille
    BATTLE_START = "BATTLE_START"
    BATTLE_END = "BATTLE_END"

    # Contexte du joueur (informations propres)
    PLAYER_VEHICLE = "PLAYER_VEHICLE"
    MAP_INFO = "MAP_INFO"
    SPAWN_INFO = "SPAWN_INFO"
    TEAM_COMPOSITION = "TEAM_COMPOSITION"   # composition connue au chargement

    # Etat temps reel (informations propres / normalement visibles)
    PLAYER_HP_CHANGED = "PLAYER_HP_CHANGED"
    PLAYER_DAMAGE_DEALT = "PLAYER_DAMAGE_DEALT"
    PLAYER_ASSIST = "PLAYER_ASSIST"
    PLAYER_POSITION = "PLAYER_POSITION"     # position du joueur (secteur symbolique)
    # Positions du feed minimap : SA position, celles de ses ALLIES, et celles des
    # ennemis DEJA SPOTTES (exactement ce que la minimap montre au joueur). Aucune
    # position d'ennemi non spotte (cf. ENEMY_UNSPOTTED_POSITION, interdit).
    POSITIONS = "POSITIONS"
    ALLY_DESTROYED = "ALLY_DESTROYED"       # allie detruit (visible dans le tableau)
    ENEMY_DESTROYED = "ENEMY_DESTROYED"     # kill visible dans le tableau de bord
    TEAM_COUNT = "TEAM_COUNT"               # nombre de vehicules restants par camp
    CLOCK_TICK = "CLOCK_TICK"               # temps ecoule dans la bataille

    # Resultat
    BATTLE_RESULT = "BATTLE_RESULT"


# Types d'evenements EXPLICITEMENT interdits (annexe B). Utilises par les tests
# negatifs du FairPlayFilter : si l'un d'eux apparait, il DOIT etre rejete.
FORBIDDEN_EVENT_TYPES: frozenset[str] = frozenset({
    "ENEMY_RELOAD",             # timer de reload adverse
    "ENEMY_GUN_DIRECTION",      # direction de canon cachee / laser
    "ENEMY_UNSPOTTED_POSITION",  # derniere position memorisee illegitime
    "ARTY_TRAJECTORY",          # trajectoire pour localiser une arty
    "AUTO_FIRE",                # automatisation du tir
})


@dataclass(frozen=True)
class RawEvent:
    """Evenement brut normalise. Immuable pour faciliter le rejeu deterministe."""
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    battle_id: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def with_battle(self, battle_id: str) -> "RawEvent":
        return RawEvent(
            event_type=self.event_type,
            payload=self.payload,
            timestamp_ms=self.timestamp_ms,
            battle_id=battle_id,
            event_id=self.event_id,
        )
