"""Utilitaires de construction d'evenements et de contextes pour les tests."""
from __future__ import annotations

from wot_companion.core.events import EventType, RawEvent


def ev(etype: str, payload: dict | None = None, ts: int = 0, battle_id: str = "b1") -> RawEvent:
    return RawEvent(event_type=etype, payload=payload or {}, timestamp_ms=ts, battle_id=battle_id)


def opening_events(
    battle_id: str = "b1",
    map_id: str = "prokhorovka",
    spawn: str = "south",
    vehicle_id: str = "leopard_1",
    vehicle_class: str = "medium",
    tier: int = 10,
    ally_classes: dict | None = None,
    enemy_classes: dict | None = None,
    ally_count: int = 15,
    enemy_count: int = 15,
) -> list[RawEvent]:
    ally_classes = ally_classes or {"heavy": 4, "medium": 4, "td": 3, "light": 2, "spg": 2}
    enemy_classes = enemy_classes or {"heavy": 4, "medium": 4, "td": 3, "light": 2, "spg": 2}
    return [
        ev(EventType.BATTLE_START.value, {"battle_id": battle_id}, battle_id=battle_id),
        ev(EventType.PLAYER_VEHICLE.value,
           {"vehicle_id": vehicle_id, "class": vehicle_class, "tier": tier}, battle_id=battle_id),
        ev(EventType.MAP_INFO.value, {"map_id": map_id}, battle_id=battle_id),
        ev(EventType.SPAWN_INFO.value, {"spawn": spawn}, battle_id=battle_id),
        ev(EventType.TEAM_COMPOSITION.value, {
            "ally_classes": ally_classes, "enemy_classes": enemy_classes,
            "ally_count": ally_count, "enemy_count": enemy_count,
        }, battle_id=battle_id),
    ]


def tick(elapsed_s: float, battle_id: str = "b1") -> RawEvent:
    return ev(EventType.CLOCK_TICK.value, {"elapsed_s": elapsed_s}, battle_id=battle_id)
