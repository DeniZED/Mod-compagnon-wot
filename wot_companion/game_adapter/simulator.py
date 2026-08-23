"""SimulatedAdapter : genere des batailles synthetiques deterministes.

Permet de developper et tester tout le moteur (regles, scoring, arbitrage,
overlay, profil) sans le client WoT, comme recommande par la roadmap
(section 17.1 : "Moteur de regles avec faux evenements/simulateur").

IMPORTANT Fair Play : le simulateur ne produit QUE des evenements whitelistes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from ..core.events import EventType, RawEvent
from .base import GameAdapter


@dataclass
class Scenario:
    battle_id: str
    map_id: str
    spawn: str
    vehicle_id: str
    vehicle_class: str
    tier: int
    ally_classes: dict[str, int]
    enemy_classes: dict[str, int]
    ally_count: int = 15
    enemy_count: int = 15
    duration_s: float = 300.0
    tick_interval_s: float = 10.0
    result: str = "victory"
    # Evenements supplementaires : (elapsed_s, event_type, payload)
    timeline: list[tuple[float, str, dict]] = field(default_factory=list)


class SimulatedAdapter(GameAdapter):
    def __init__(self, scenarios: list[Scenario], start_ms: int = 1_787_520_000_000) -> None:
        self.scenarios = scenarios
        self.start_ms = start_ms

    def _ts(self, base_ms: int, elapsed_s: float) -> int:
        return base_ms + int(elapsed_s * 1000)

    def events(self) -> Iterator[RawEvent]:
        base_ms = self.start_ms
        for sc in self.scenarios:
            yield from self._battle_events(sc, base_ms)
            base_ms += int(sc.duration_s * 1000) + 60_000  # gap garage entre batailles

    def _battle_events(self, sc: Scenario, base_ms: int) -> Iterator[RawEvent]:
        def ev(elapsed: float, etype: str, payload: dict) -> RawEvent:
            return RawEvent(
                event_type=etype, payload=payload,
                timestamp_ms=self._ts(base_ms, elapsed), battle_id=sc.battle_id,
            )

        # Ouverture : contexte statique.
        yield ev(0.0, EventType.BATTLE_START.value, {"battle_id": sc.battle_id})
        yield ev(0.0, EventType.PLAYER_VEHICLE.value,
                 {"vehicle_id": sc.vehicle_id, "tier": sc.tier, "class": sc.vehicle_class})
        yield ev(0.0, EventType.MAP_INFO.value, {"map_id": sc.map_id})
        yield ev(0.0, EventType.SPAWN_INFO.value, {"spawn": sc.spawn})
        yield ev(0.0, EventType.TEAM_COMPOSITION.value, {
            "ally_classes": sc.ally_classes, "enemy_classes": sc.enemy_classes,
            "ally_count": sc.ally_count, "enemy_count": sc.enemy_count,
        })

        # Fusion des CLOCK_TICK et des evenements de timeline, tries par temps.
        ticks = []
        t = sc.tick_interval_s
        while t <= sc.duration_s:
            ticks.append((t, EventType.CLOCK_TICK.value,
                          {"elapsed_s": t, "remaining_s": max(0.0, sc.duration_s - t)}))
            t += sc.tick_interval_s
        merged = sorted(sc.timeline + ticks, key=lambda x: x[0])
        for elapsed, etype, payload in merged:
            yield ev(elapsed, etype, payload)

        # Cloture : resultat + fin.
        yield ev(sc.duration_s, EventType.BATTLE_RESULT.value, {"result": sc.result})
        yield ev(sc.duration_s, EventType.BATTLE_END.value,
                 {"battle_id": sc.battle_id, "reason": "finished"})


def make_default_scenarios() -> list[Scenario]:
    """Scenarios de reference alignes sur les exemples du cahier des charges."""
    return [
        _scenario_prokho_initial_plan(),
        _scenario_flank_collapse_retreat(),
        _scenario_early_hp_loss(),
    ]


def _scenario_prokho_initial_plan() -> Scenario:
    """Debut de bataille : Leopard 1 - Prokhorovka sud (scenario section 3.2)."""
    return Scenario(
        battle_id="sim-prokho-01", map_id="prokhorovka", spawn="south",
        vehicle_id="leopard_1", vehicle_class="medium", tier=10,
        ally_classes={"heavy": 4, "medium": 3, "td": 3, "light": 2, "spg": 3},
        enemy_classes={"heavy": 3, "medium": 6, "td": 3, "light": 1, "spg": 2},
        duration_s=120.0,
        timeline=[
            (30.0, EventType.PLAYER_POSITION.value, {"sector": "K1", "flank": "west"}),
            (30.0, EventType.PLAYER_DAMAGE_DEALT.value, {"total_damage": 400}),
        ],
    )


def _scenario_flank_collapse_retreat() -> Scenario:
    """Alerte tempo : le flanc du joueur cede alors qu'il a la majorite des HP."""
    return Scenario(
        battle_id="sim-retreat-01", map_id="himmelsdorf", spawn="north",
        vehicle_id="e50m", vehicle_class="medium", tier=10,
        ally_classes={"heavy": 5, "medium": 4, "td": 3, "light": 1, "spg": 2},
        enemy_classes={"heavy": 5, "medium": 4, "td": 3, "light": 1, "spg": 2},
        duration_s=240.0,
        timeline=[
            (20.0, EventType.PLAYER_POSITION.value, {"sector": "D3", "flank": "town"}),
            (30.0, EventType.PLAYER_HP_CHANGED.value, {"hp_ratio": 0.9}),
            (90.0, EventType.PLAYER_DAMAGE_DEALT.value, {"total_damage": 800}),
            # Le flanc "town" du joueur s'effondre :
            (100.0, EventType.ALLY_DESTROYED.value, {"flank": "town", "allies_alive": 13}),
            (110.0, EventType.ALLY_DESTROYED.value, {"flank": "town", "allies_alive": 11}),
            (115.0, EventType.TEAM_COUNT.value, {"allies_alive": 11, "enemies_alive": 14}),
        ],
    )


def _scenario_early_hp_loss() -> Scenario:
    """Perte de HP trop tot (alimente la synthese de session, section 6.1)."""
    return Scenario(
        battle_id="sim-hploss-01", map_id="mines", spawn="south",
        vehicle_id="leopard_1", vehicle_class="medium", tier=10,
        ally_classes={"heavy": 4, "medium": 4, "td": 3, "light": 2, "spg": 2},
        enemy_classes={"heavy": 4, "medium": 4, "td": 3, "light": 2, "spg": 2},
        duration_s=150.0, result="defeat",
        timeline=[
            (20.0, EventType.PLAYER_POSITION.value, {"sector": "F5", "flank": "hill"}),
            (40.0, EventType.PLAYER_HP_CHANGED.value, {"hp_ratio": 0.42}),
            (60.0, EventType.PLAYER_DAMAGE_DEALT.value, {"total_damage": 600}),
            (150.0, EventType.PLAYER_HP_CHANGED.value, {"hp_ratio": 0.30}),
        ],
    )
