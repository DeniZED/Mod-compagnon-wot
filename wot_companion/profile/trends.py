"""Tendances de session et profil joueur (GAR-003, section 8.1).

Regle d'or (section 6.2) : toute metrique est accompagnee d'un volume
d'echantillon et d'un niveau de confiance ; un echantillon trop faible est
signale et n'est pas surinterprete.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean

from .store import BattleRecord, HistoryStore

# En dessous de ce nombre de batailles, la confiance est jugee insuffisante.
MIN_SAMPLE_SIZE = 5
CONFIDENCE_FULL_SAMPLE = 20  # confiance ~1.0 a partir de ce volume


@dataclass
class SessionTrends:
    sample_size: int
    window: int
    vehicle_id: str | None
    avg_damage: float | None
    avg_assist: float | None
    survival_rate: float | None
    hp_lost_early_rate: float | None
    confidence: float
    low_sample: bool
    method: str = "moyenne glissante sur fenetre courte"

    def as_dict(self) -> dict:
        return {
            "sample_size": self.sample_size, "window": self.window,
            "vehicle_id": self.vehicle_id, "avg_damage": _r(self.avg_damage),
            "avg_assist": _r(self.avg_assist), "survival_rate": _r(self.survival_rate, 3),
            "hp_lost_early_rate": _r(self.hp_lost_early_rate, 3),
            "confidence": round(self.confidence, 2), "low_sample": self.low_sample,
            "method": self.method,
        }


def _r(x: float | None, ndigits: int = 0) -> float | None:
    return None if x is None else round(x, ndigits)


def _confidence(n: int) -> float:
    return max(0.0, min(1.0, n / CONFIDENCE_FULL_SAMPLE))


def aggregate_records(records: list[BattleRecord]) -> dict:
    """Agrege un lot de batailles (moyennes DPG/assist, survie, perte HP early)."""
    n = len(records)
    if n == 0:
        return {"sample_size": 0, "confidence": 0.0}
    return {
        "sample_size": n,
        "avg_damage": round(mean(r.damage for r in records)),
        "avg_assist": round(mean(r.assist for r in records)),
        "survival_rate": round(mean(1.0 if r.survived else 0.0 for r in records), 3),
        "hp_lost_early_rate": round(mean(1.0 if r.hp_lost_early else 0.0 for r in records), 3),
        "avg_kills": round(mean(r.kills for r in records), 2),
        "confidence": round(_confidence(n), 2),
        "low_sample": n < MIN_SAMPLE_SIZE,
    }


def group_records(records: list[BattleRecord], key: str) -> dict[str, list[BattleRecord]]:
    """Regroupe les batailles par attribut (ex: 'vehicle_id', 'vehicle_role')."""
    groups: dict[str, list[BattleRecord]] = {}
    for r in records:
        k = getattr(r, key, None) or "?"
        groups.setdefault(k, []).append(r)
    return groups


class TrendAnalyzer:
    def __init__(self, store: HistoryStore) -> None:
        self.store = store

    def session_trends(self, window: int = 10, vehicle_id: str | None = None
                      ) -> SessionTrends:
        battles = self.store.recent_battles(limit=window, vehicle_id=vehicle_id)
        n = len(battles)
        if n == 0:
            return SessionTrends(0, window, vehicle_id, None, None, None, None, 0.0, True)

        survived = [1.0 if b.survived else 0.0 for b in battles]
        hp_early = [1.0 if b.hp_lost_early else 0.0 for b in battles]
        return SessionTrends(
            sample_size=n, window=window, vehicle_id=vehicle_id,
            avg_damage=mean(b.damage for b in battles),
            avg_assist=mean(b.assist for b in battles),
            survival_rate=mean(survived),
            hp_lost_early_rate=mean(hp_early),
            confidence=_confidence(n),
            low_sample=n < MIN_SAMPLE_SIZE,
        )

    def summary_lines(self, trends: SessionTrends) -> list[str]:
        """1 a 3 constats pour le resume garage (GAR-001)."""
        if trends.sample_size == 0:
            return ["Pas encore de bataille enregistree sur cette session."]
        lines = [
            f"{trends.sample_size} batailles - DPG moyen {int(trends.avg_damage or 0)}, "
            f"assist {int(trends.avg_assist or 0)}."
        ]
        if trends.survival_rate is not None:
            lines.append(f"Survie {int(trends.survival_rate * 100)}%.")
        if trends.hp_lost_early_rate is not None and trends.hp_lost_early_rate >= 0.3:
            lines.append(
                f"HP perdus tot dans {int(trends.hp_lost_early_rate * 100)}% des parties : "
                "axe prioritaire = discipline early game."
            )
        if trends.low_sample:
            lines.append("(Echantillon faible : a confirmer sur plus de batailles.)")
        return lines[:3]


def build_player_profile(store: HistoryStore, window: int = 30) -> dict:
    """Construit le profil de coaching interne (section 8.1).

    Les scores sont des INDICATEURS de coaching, jamais des jugements, et sont
    toujours accompagnes du volume d'echantillon et d'une confiance.
    """
    battles = store.recent_battles(limit=window)
    n = len(battles)
    if n == 0:
        return {"sample_size": 0, "confidence": 0.0}

    survival = mean(1.0 if b.survived else 0.0 for b in battles)
    hp_early = mean(1.0 if b.hp_lost_early else 0.0 for b in battles)

    # Profil par rôle (section 8.1 : per_role), avec volume et confiance propres.
    per_role: dict[str, dict] = {}
    for role, recs in group_records(battles, "vehicle_role").items():
        if role == "?":
            continue
        nr = len(recs)
        hp_e = mean(1.0 if r.hp_lost_early else 0.0 for r in recs)
        per_role[role] = {
            "aggression_early": round(hp_e, 3),
            "hp_preservation": round(1.0 - hp_e, 3),
            "survival": round(mean(1.0 if r.survived else 0.0 for r in recs), 3),
            "sample_size": nr,
            "confidence": round(_confidence(nr), 3),
        }

    return {
        # aggression_early : plus il perd ses HP tot, plus il ouvre agressivement.
        "aggression_early": round(hp_early, 3),
        # hp_preservation : inverse de la perte precoce.
        "hp_preservation": round(1.0 - hp_early, 3),
        "survival": round(survival, 3),
        "sample_size": n,
        "confidence": round(_confidence(n), 3),
        "per_role": per_role,
    }
