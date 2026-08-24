"""BattleContext : etat normalise d'une bataille, alimente par les RawEvent filtres.

Le contexte ne stocke QUE des donnees autorisees. Toute valeur non fournie reste
`None` : les regles doivent gerer l'absence sans inventer (fallback sur, section 5 BAT-010).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..events import EventType, RawEvent


class BattlePhase(str, Enum):
    EARLY = "early"
    MID = "mid"
    LATE = "late"


@dataclass
class TeamComposition:
    """Indicateurs agreges de composition connus au chargement (BAT-004)."""
    ally_classes: dict[str, int] = field(default_factory=dict)
    enemy_classes: dict[str, int] = field(default_factory=dict)
    ally_count: int | None = None
    enemy_count: int | None = None

    def enemy_class_count(self, klass: str) -> int:
        return self.enemy_classes.get(klass, 0)

    def ally_class_count(self, klass: str) -> int:
        return self.ally_classes.get(klass, 0)


@dataclass
class BattleContext:
    """Contexte d'une bataille unique. Un seul contexte actif a la fois (BAT-001)."""
    battle_id: str
    start_ms: int
    end_ms: int | None = None

    # Contexte statique (resolu au chargement)
    vehicle_id: str | None = None
    vehicle_tier: int | None = None
    vehicle_class: str | None = None
    vehicle_role: str | None = None        # rôle metier interne (resolu via KB)
    map_id: str | None = None
    spawn: str | None = None
    composition: TeamComposition = field(default_factory=TeamComposition)

    # Etat temps reel
    hp_ratio: float | None = None
    total_damage: float = 0.0
    total_assist: float = 0.0
    player_sector: str | None = None
    player_flank: str | None = None
    allies_alive: int | None = None
    enemies_alive: int | None = None
    elapsed_s: float = 0.0
    remaining_s: float | None = None

    # Suivi derive (pour les regles tempo / repli)
    contribution_seen: bool = False        # l'adaptateur fournit-il degats/assist ?
    last_contribution_s: float = 0.0       # dernier instant ou degats/assist ont bouge
    last_ally_loss_s: float | None = None
    flank_ally_losses: dict[str, int] = field(default_factory=dict)

    # Resultat
    result: str | None = None
    finished: bool = False

    # Champs signales absents (pour fallback sûr / audit)
    missing_fields: set[str] = field(default_factory=set)

    def apply(self, event: RawEvent) -> None:
        """Met a jour le contexte a partir d'un evenement DEJA filtre Fair Play."""
        p = event.payload
        et = event.event_type

        if et == EventType.PLAYER_VEHICLE.value:
            self.vehicle_id = p.get("vehicle_id")
            self.vehicle_tier = p.get("tier")
            self.vehicle_class = p.get("class")
            # Rôle transmis directement par l'adaptateur (deduit des tags du char,
            # information visible au joueur). Prioritaire sur la resolution KB.
            if p.get("role"):
                self.vehicle_role = p.get("role")
        elif et == EventType.MAP_INFO.value:
            self.map_id = p.get("map_id")
        elif et == EventType.SPAWN_INFO.value:
            self.spawn = p.get("spawn")
        elif et == EventType.TEAM_COMPOSITION.value:
            self.composition = TeamComposition(
                ally_classes=dict(p.get("ally_classes", {})),
                enemy_classes=dict(p.get("enemy_classes", {})),
                ally_count=p.get("ally_count"),
                enemy_count=p.get("enemy_count"),
            )
            self.allies_alive = self.composition.ally_count
            self.enemies_alive = self.composition.enemy_count
        elif et == EventType.PLAYER_HP_CHANGED.value:
            if "hp_ratio" in p:
                self.hp_ratio = float(p["hp_ratio"])
            elif "hp" in p and "max_hp" in p and p["max_hp"]:
                self.hp_ratio = float(p["hp"]) / float(p["max_hp"])
        elif et == EventType.PLAYER_DAMAGE_DEALT.value:
            self.contribution_seen = True
            new_total = p.get("total_damage")
            if new_total is None:
                new_total = self.total_damage + float(p.get("damage", 0))
            if new_total != self.total_damage:
                self.last_contribution_s = self.elapsed_s
            self.total_damage = float(new_total)
        elif et == EventType.PLAYER_ASSIST.value:
            self.contribution_seen = True
            new_total = p.get("total_assist")
            if new_total is None:
                new_total = self.total_assist + float(p.get("assist", 0))
            if new_total != self.total_assist:
                self.last_contribution_s = self.elapsed_s
            self.total_assist = float(new_total)
        elif et == EventType.PLAYER_POSITION.value:
            self.player_sector = p.get("sector")
            self.player_flank = p.get("flank")
        elif et == EventType.ALLY_DESTROYED.value:
            self.last_ally_loss_s = self.elapsed_s
            flank = p.get("flank")
            if flank:
                self.flank_ally_losses[flank] = self.flank_ally_losses.get(flank, 0) + 1
            if "allies_alive" in p:
                self.allies_alive = p["allies_alive"]
        elif et == EventType.ENEMY_DESTROYED.value:
            if "enemies_alive" in p:
                self.enemies_alive = p["enemies_alive"]
        elif et == EventType.TEAM_COUNT.value:
            if "allies_alive" in p:
                self.allies_alive = p["allies_alive"]
            if "enemies_alive" in p:
                self.enemies_alive = p["enemies_alive"]
        elif et == EventType.CLOCK_TICK.value:
            self.elapsed_s = float(p.get("elapsed_s", self.elapsed_s))
            if "remaining_s" in p:
                self.remaining_s = float(p["remaining_s"])
        elif et == EventType.BATTLE_RESULT.value:
            self.result = p.get("result")
            if "damage" in p:
                self.total_damage = float(p["damage"])
            if "assist" in p:
                self.total_assist = float(p["assist"])
            if "hp_ratio_end" in p:
                self.hp_ratio = float(p["hp_ratio_end"])
        elif et == EventType.BATTLE_END.value:
            self.finished = True
            self.end_ms = event.timestamp_ms

    def mark_missing(self, field_name: str) -> None:
        self.missing_fields.add(field_name)

    def has(self, field_name: str) -> bool:
        """Vrai si le champ est present (non None) : sert au fallback sûr des regles."""
        return getattr(self, field_name, None) is not None

    def numeric_balance(self) -> int | None:
        """Avantage/desavantage numerique observable (positif = avantage allie)."""
        if self.allies_alive is None or self.enemies_alive is None:
            return None
        return self.allies_alive - self.enemies_alive

    def snapshot(self) -> dict[str, Any]:
        """Contexte minimal pour le journal des conseils (BAT-009)."""
        return {
            "battle_id": self.battle_id,
            "map_id": self.map_id,
            "spawn": self.spawn,
            "vehicle_role": self.vehicle_role,
            "hp_ratio": self.hp_ratio,
            "elapsed_s": round(self.elapsed_s, 1),
            "allies_alive": self.allies_alive,
            "enemies_alive": self.enemies_alive,
            "player_flank": self.player_flank,
        }
