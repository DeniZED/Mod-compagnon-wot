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


def _as_xz(v: Any) -> tuple[float, float] | None:
    """Normalise une position en (x, z) plan horizontal. Tolerant : accepte
    [x, z] ou [x, y, z] (WoT : y = altitude, ignoree)."""
    try:
        if v is None:
            return None
        if len(v) >= 3:
            return (float(v[0]), float(v[2]))
        if len(v) == 2:
            return (float(v[0]), float(v[1]))
    except (TypeError, ValueError):
        return None
    return None


def _as_xz_list(v: Any) -> list[tuple[float, float]]:
    if not isinstance(v, (list, tuple)):
        return []
    out = []
    for item in v:
        xz = _as_xz(item)
        if xz is not None:
            out.append(xz)
    return out


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
    map_bounds: tuple[float, float, float, float] | None = None  # minX,minZ,maxX,maxZ
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
    # Degats subis (chute de HP) : pour les reactions "tir recu".
    last_damage_taken_s: float | None = None
    last_damage_taken_ratio: float = 0.0   # ampleur de la derniere chute (0..1)
    # Positions du feed minimap (Fair Play) : soi, allies, ennemis DEJA spottes.
    own_pos: tuple[float, float] | None = None
    ally_positions: list[tuple[float, float]] = field(default_factory=list)
    enemy_positions_spotted: list[tuple[float, float]] = field(default_factory=list)

    # Resultat
    result: str | None = None
    result_survived: bool | None = None    # survie reelle (resultat autoritaire)
    kills: int = 0
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
            b = p.get("bounds")
            if isinstance(b, (list, tuple)) and len(b) == 4:
                try:
                    self.map_bounds = (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
                except (TypeError, ValueError):
                    self.map_bounds = None
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
        elif et == EventType.POSITIONS.value:
            self.own_pos = _as_xz(p.get("own"))
            self.ally_positions = _as_xz_list(p.get("allies"))
            # SECURITE Fair Play : uniquement les ennemis deja spottes (feed minimap).
            self.enemy_positions_spotted = _as_xz_list(p.get("enemies_spotted"))
        elif et == EventType.PLAYER_HP_CHANGED.value:
            new_ratio = None
            if "hp_ratio" in p:
                new_ratio = float(p["hp_ratio"])
            elif "hp" in p and "max_hp" in p and p["max_hp"]:
                new_ratio = float(p["hp"]) / float(p["max_hp"])
            if new_ratio is not None:
                # Chute de HP = degats subis (tir recu) : on horodate pour les
                # reactions. On ignore une remontee (kit de reparation).
                if self.hp_ratio is not None and new_ratio < self.hp_ratio - 1e-6:
                    self.last_damage_taken_s = self.elapsed_s
                    self.last_damage_taken_ratio = self.hp_ratio - new_ratio
                self.hp_ratio = new_ratio
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
                self.contribution_seen = True
            if "assist" in p:
                self.total_assist = float(p["assist"])
            if "survived" in p:
                self.result_survived = bool(p["survived"])
            if "kills" in p:
                self.kills = int(p["kills"])
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
