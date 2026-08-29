"""Feature Builder : indicateurs derives du BattleContext pour les regles.

Les features sont des lectures agregees et deterministes. Elles n'ajoutent
aucune information exterieure : uniquement des transformations de donnees deja
presentes et autorisees dans le contexte.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .battle_context import BattleContext, BattlePhase

# Rayons en metres (WoT). Portee de vue max ~445 m ; engagements courants 200-350 m.
SUPPORT_RADIUS_M = 160.0     # un allie plus proche que ca peut te soutenir
ISOLATION_DIST_M = 200.0     # au-dela, aucun allie proche = isole
THREAT_RADIUS_M = 220.0      # ennemi spotte dans ce rayon = menace locale directe

# Bornes de phase (section 7 BAT-007). Une bataille WoT dure ~15 min (900 s).
EARLY_MAX_S = 150.0   # 2 min 30
MID_MAX_S = 480.0     # 8 min
# Hysteresis pour eviter l'oscillation de phase.
PHASE_HYSTERESIS_S = 10.0
# Fenetre pendant laquelle un effondrement de flanc reste "actif" apres la
# derniere perte : au-dela, l'alerte de repli n'est plus pertinente (anti-spam).
RECENT_LOSS_WINDOW_S = 60.0
# Fenetre pendant laquelle des degats subis restent "frais" pour une reaction.
RECENT_DAMAGE_WINDOW_S = 4.0


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
    took_damage_recently: bool             # a subi des degats dans la fenetre recente
    damage_taken_ratio: float              # ampleur de la derniere chute (0..1)
    # Spatial (feed minimap : soi + allies + ennemis spottes). None/0 si pas de data.
    nearest_ally_dist: float | None        # distance a l'allie vivant le plus proche
    allies_near: int                       # allies dans le rayon de soutien
    enemies_spotted_near: int              # ennemis SPOTTES proches (menace locale)
    isolated: bool                         # aucun allie a portee de soutien
    overextended: bool                     # pousse devant le gros de l'equipe


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

        took_damage = (
            ctx.last_damage_taken_s is not None
            and ctx.elapsed_s - ctx.last_damage_taken_s <= RECENT_DAMAGE_WINDOW_S
        )

        spatial = self._spatial(ctx)

        return Features(
            phase=phase,
            hp_ratio=ctx.hp_ratio,
            numeric_balance=balance,
            time_since_contribution_s=time_since_contrib,
            flank_collapsing=flank_collapsing,
            outnumbered_locally=outnumbered,
            endgame_few_left=(total_alive is not None and total_alive <= 6),
            contribution_total=ctx.total_damage + ctx.total_assist,
            took_damage_recently=took_damage,
            damage_taken_ratio=ctx.last_damage_taken_ratio if took_damage else 0.0,
            nearest_ally_dist=spatial["nearest_ally_dist"],
            allies_near=spatial["allies_near"],
            enemies_spotted_near=spatial["enemies_spotted_near"],
            isolated=spatial["isolated"],
            overextended=spatial["overextended"],
        )

    def _spatial(self, ctx: BattleContext) -> dict:
        """Indicateurs spatiaux a partir du feed minimap. Fallback sur : sans
        position propre, tout est neutre (None/0/False)."""
        own = ctx.own_pos
        blank = {"nearest_ally_dist": None, "allies_near": 0,
                 "enemies_spotted_near": 0, "isolated": False, "overextended": False}
        if own is None:
            return blank

        def dist(a, b):
            return math.hypot(a[0] - b[0], a[1] - b[1])

        allies = ctx.ally_positions or []
        enemies = ctx.enemy_positions_spotted or []

        ally_dists = sorted(dist(own, a) for a in allies)
        nearest = ally_dists[0] if ally_dists else None
        allies_near = sum(1 for d in ally_dists if d <= SUPPORT_RADIUS_M)
        enemies_near = sum(1 for e in enemies if dist(own, e) <= THREAT_RADIUS_M)

        # Isole : on connait des allies mais aucun a portee de soutien.
        isolated = bool(allies) and (nearest is None or nearest > ISOLATION_DIST_M)

        # Surextension : le joueur est nettement plus AVANCE que son equipe le long
        # de l'axe equipe->ennemis. On PROJETTE la position sur cet axe : un decalage
        # LATERAL (etre "a cote" de la team) ne compte pas, seule l'avance vers
        # l'ennemi compte. Necessite allies + ennemis spottes, et un axe net.
        overextended = False
        if allies and enemies:
            ax = sum(a[0] for a in allies) / len(allies)
            az = sum(a[1] for a in allies) / len(allies)
            ex = sum(e[0] for e in enemies) / len(enemies)
            ez = sum(e[1] for e in enemies) / len(enemies)
            dxe, dze = ex - ax, ez - az          # axe equipe -> ennemis
            axis_len = math.hypot(dxe, dze)
            if axis_len >= 80.0:                 # axe assez net pour juger l'avance
                ux, uz = dxe / axis_len, dze / axis_len
                # Avance du joueur DEVANT le centre de l'equipe, projetee sur l'axe.
                ahead = (own[0] - ax) * ux + (own[1] - az) * uz
                overextended = ahead > SUPPORT_RADIUS_M

        return {"nearest_ally_dist": nearest, "allies_near": allies_near,
                "enemies_spotted_near": enemies_near, "isolated": isolated,
                "overextended": overextended}
