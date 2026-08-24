"""Chargement et interrogation de la base de connaissances tactique."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.context.battle_context import TeamComposition

_KB_DIR = Path(__file__).parent

_CLASS_ALIASES = {"heavy", "medium", "light", "td", "spg"}
_COND_RE = re.compile(r"^(ally|enemy)_(\w+)\s*(>=|<=|==|>|<)\s*(\d+)$")


@dataclass
class TacticalPlan:
    """Plan candidat (section 7.3)."""
    plan_id: str
    map_id: str
    spawn: str | None
    roles: list[str]
    phase: str
    flank: str | None
    anchor: str
    risk: str
    aggression: str
    base_score: int
    requirements: list[str] = field(default_factory=list)
    avoid_if: list[str] = field(default_factory=list)
    explanation: str = ""
    source: str = ""
    version: str = ""

    def matches(self, map_id: str, spawn: str | None, role: str | None) -> bool:
        if self.map_id != map_id:
            return False
        if self.spawn and spawn and self.spawn != spawn:
            return False
        if role and self.roles and role not in self.roles:
            return False
        return True


def _eval_condition(cond: str, comp: TeamComposition) -> bool | None:
    """Evalue une condition symbolique contre la composition.

    Retourne True/False, ou None si l'information necessaire est absente
    (on n'invente jamais de contexte : fallback sûr).
    """
    cond = cond.strip()
    if cond == "outnumbered":
        if comp.ally_count is None or comp.enemy_count is None:
            return None
        return comp.ally_count < comp.enemy_count
    if cond == "no_ally_support":
        if not comp.ally_classes:
            return None
        return (comp.ally_class_count("medium") + comp.ally_class_count("heavy")) == 0

    m = _COND_RE.match(cond)
    if not m:
        return None
    side, klass, op, num_s = m.groups()
    num = int(num_s)
    classes = comp.ally_classes if side == "ally" else comp.enemy_classes
    if not classes:
        return None
    value = classes.get(klass, 0)
    return {
        ">=": value >= num, "<=": value <= num, "==": value == num,
        ">": value > num, "<": value < num,
    }[op]


class KnowledgeBase:
    """Acces en lecture a la connaissance tactique versionnee."""

    def __init__(self, base_dir: Path | None = None) -> None:
        d = base_dir or _KB_DIR
        self._roles_doc = json.loads((d / "tanks" / "roles.json").read_text(encoding="utf-8"))
        self._maps_doc = json.loads((d / "maps" / "maps.json").read_text(encoding="utf-8"))
        plans_doc = json.loads((d / "tactics" / "plans.json").read_text(encoding="utf-8"))

        self.version = plans_doc.get("version", "unknown")
        self._source = plans_doc.get("source", "")
        self._roles = self._roles_doc["roles"]
        self._vehicles = self._roles_doc["vehicles"]
        self._maps = self._maps_doc["maps"]
        self._plans = [
            TacticalPlan(
                plan_id=p["plan_id"], map_id=p["map_id"], spawn=p.get("spawn"),
                roles=p.get("roles", []), phase=p.get("phase", "early"),
                flank=p.get("flank"), anchor=p["anchor"], risk=p.get("risk", "medium"),
                aggression=p.get("aggression", "neutre"), base_score=p.get("base_score", 50),
                requirements=p.get("requirements", []), avoid_if=p.get("avoid_if", []),
                explanation=p.get("explanation", ""), source=self._source, version=self.version,
            )
            for p in plans_doc["plans"]
        ]

    # ---- Rôles / vehicules -------------------------------------------------
    def resolve_role(self, vehicle_id: str | None) -> str | None:
        if not vehicle_id:
            return None
        return self._vehicles.get(vehicle_id)

    def role_info(self, role: str | None) -> dict[str, Any] | None:
        if not role:
            return None
        return self._roles.get(role)

    def role_reminder(self, role: str | None) -> str | None:
        info = self.role_info(role)
        return info.get("reminder") if info else None

    def known_maps(self) -> list[str]:
        return sorted(self._maps.keys())

    def map_info(self, map_id: str | None) -> dict[str, Any] | None:
        if not map_id:
            return None
        return self._maps.get(map_id)

    def flank_label(self, map_id: str | None, flank: str | None) -> str | None:
        info = self.map_info(map_id)
        if not info or not flank:
            return flank
        return info.get("flanks", {}).get(flank, flank)

    # ---- Plans -------------------------------------------------------------
    def candidate_plans(
        self, map_id: str, spawn: str | None, role: str | None, comp: TeamComposition
    ) -> list[tuple[TacticalPlan, int, list[str]]]:
        """Retourne (plan, score_ajuste, raisons) pour les plans applicables.

        Un plan dont un `avoid_if` est confirme vrai est ecarte. Les
        `requirements` non satisfaits (donnees presentes) penalisent le score ;
        les conditions indeterminees (donnees absentes) n'excluent pas le plan.
        """
        out: list[tuple[TacticalPlan, int, list[str]]] = []
        for plan in self._plans:
            if not plan.matches(map_id, spawn, role):
                continue
            excluded = False
            reasons: list[str] = []
            for cond in plan.avoid_if:
                if _eval_condition(cond, comp) is True:
                    excluded = True
                    reasons.append(f"avoid_if:{cond}")
                    break
            if excluded:
                continue

            score = plan.base_score
            for cond in plan.requirements:
                res = _eval_condition(cond, comp)
                if res is False:
                    score -= 15
                    reasons.append(f"req_unmet:{cond}")
                elif res is True:
                    score += 5
                    reasons.append(f"req_ok:{cond}")
            # Bonus si le plan cible explicitement le rôle du joueur.
            if role and role in plan.roles:
                score += 8
                reasons.append("role_match")
            out.append((plan, score, reasons))

        out.sort(key=lambda t: (-t[1], t[0].plan_id))  # tri deterministe
        return out
