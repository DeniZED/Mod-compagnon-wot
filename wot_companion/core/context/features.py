"""Feature Builder : indicateurs derives du BattleContext pour les regles.

Les features sont des lectures agregees et deterministes. Elles n'ajoutent
aucune information exterieure : uniquement des transformations de donnees deja
presentes et autorisees dans le contexte.
"""
from __future__ import annotations

from dataclasses import dataclass

from .battle_context import BattleContext, BattlePhase

# Bornes de phase (section 7 BAT-007). Une bataille WoT dure ~15 min (900 s).
EARLY_MAX_S = 150.0   # 2 min 30
MID_MAX_S = 480.0     # 8 min
# Hysteresis pour eviter l'oscillation de phase.
PHASE_HYSTERESIS_S = 10.0
# Fenetre pendant laquelle un effondrement de flanc reste "actif" apres la
# derniere perte : au-dela, l'alerte de repli n'est plus pertinente (anti-spam).
RECENT_LOSS_WINDOW_S = 60.0


@dataclass
class Features:
    phase: BattlePhase
    hp_ratio: float | None
    numeric_balance: int | None            # allies_alive - enemies_alive
    time_since_contribution_s: float
    flank_collapsing: bool                 # flanc du joueur en train de ceder
    outnumbered_locally: bool | None       # inferiorite locale observable
    endgame_few_left: bool                 # peu de chars restants au total
    contribution_total: float


class FeatureBuilder:
    """Construit les `Features` a partir d'un contexte, avec phase stable."""

    def __init__(self) -> None:
        self._last_phase: BattlePhase | None = None
        self._last_phase_change_s: float = 0.0

    def _resolve_phase(self, ctx: BattleContext) -> BattlePhase:
        t = ctx.elapsed_s
        raw = (
            BattlePhase.EARLY if t <= EARLY_MAX_S
            else BattlePhase.MID if t <= MID_MAX_S
            else BattlePhase.LATE
        )
        # Fin de partie anticipee si tres peu de vehicules subsistent.
        total_alive = None
        if ctx.allies_alive is not None and ctx.enemies_alive is not None:
            total_alive = ctx.allies_alive + ctx.enemies_alive
        if total_alive is not None and total_alive <= 6:
            raw = BattlePhase.LATE

        if self._last_phase is None:
            self._last_phase = raw
            self._last_phase_change_s = t
            return raw

        # Hysteresis : on ne change de phase que si la nouvelle tient depuis un delai,
        # et on n'autorise pas un retour en arriere (early<-mid<-late) trop vite.
        if raw != self._last_phase:
            if t - self._last_phase_change_s >= PHASE_HYSTERESIS_S:
                self._last_phase = raw
                self._last_phase_change_s = t
        return self._last_phase

    def build(self, ctx: BattleContext) -> Features:
        phase = self._resolve_phase(ctx)

        time_since_contrib = max(0.0, ctx.elapsed_s - ctx.last_contribution_s)

        # Flanc du joueur en train de ceder : au moins 2 pertes sur son flanc,
        # ET une perte recente (sinon l'effondrement est deja "digere").
        flank_collapsing = False
        if ctx.player_flank and ctx.flank_ally_losses.get(ctx.player_flank, 0) >= 2:
            if ctx.last_ally_loss_s is not None and (
                ctx.elapsed_s - ctx.last_ally_loss_s <= RECENT_LOSS_WINDOW_S
            ):
                flank_collapsing = True

        balance = ctx.numeric_balance()
        outnumbered = None if balance is None else balance < 0

        total_alive = None
        if ctx.allies_alive is not None and ctx.enemies_alive is not None:
            total_alive = ctx.allies_alive + ctx.enemies_alive

        return Features(
            phase=phase,
            hp_ratio=ctx.hp_ratio,
            numeric_balance=balance,
            time_since_contribution_s=time_since_contrib,
            flank_collapsing=flank_collapsing,
            outnumbered_locally=outnumbered,
            endgame_few_left=(total_alive is not None and total_alive <= 6),
            contribution_total=ctx.total_damage + ctx.total_assist,
        )
