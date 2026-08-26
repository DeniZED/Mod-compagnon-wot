"""Enregistreur de trace tactique legere (Moteur V2, §34).

Echantillonne l'etat d'une bataille en cours (position propre, HP, contribution,
forces locales, phase) a intervalle regulier et le range dans l'historique local.

But : accumuler, bataille apres bataille, de quoi construire les positions/routes
efficaces du joueur (PositionCluster) et un coach personnel — sans replay, sans
reseau. Uniquement des donnees deja autorisees (Fair Play).
"""
from __future__ import annotations

from ..core.context.battle_context import BattleContext
from ..core.context.features import Features
from .store import BattleState, HistoryStore

# Pas d'echantillonnage : ~1 point toutes les 5 s de bataille suffit pour des
# trajectoires exploitables sans gonfler la base.
SAMPLE_INTERVAL_S = 5.0


class BattleTraceRecorder:
    def __init__(self, store: HistoryStore, interval_s: float = SAMPLE_INTERVAL_S) -> None:
        self.store = store
        self.interval_s = interval_s
        self._battle_id: str | None = None
        self._last_sample_s: float = -1e9

    def reset(self, battle_id: str | None) -> None:
        self._battle_id = battle_id
        self._last_sample_s = -1e9

    def maybe_record(self, ctx: BattleContext, features: Features | None) -> bool:
        """Enregistre un point si l'intervalle est ecoule. Retourne True si ecrit."""
        if ctx is None or ctx.finished:
            return False
        if self._battle_id != ctx.battle_id:
            self.reset(ctx.battle_id)
        if ctx.elapsed_s - self._last_sample_s < self.interval_s:
            return False
        self._last_sample_s = ctx.elapsed_s
        own = ctx.own_pos
        state = BattleState(
            t_s=round(ctx.elapsed_s, 1),
            x=own[0] if own else None,
            z=own[1] if own else None,
            hp_ratio=ctx.hp_ratio,
            damage=ctx.total_damage,
            assist=ctx.total_assist,
            allies_near=features.allies_near if features else 0,
            enemies_near=features.enemies_spotted_near if features else 0,
            phase=features.phase.value if features else None,
        )
        try:
            self.store.record_state(ctx.battle_id, state)
        except Exception:
            return False
        return True
