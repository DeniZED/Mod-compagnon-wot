"""Tests des regles tactiques, y compris le fallback sûr (BAT-010)."""
from __future__ import annotations

from wot_companion.core.context.battle_context import BattleContext, TeamComposition
from wot_companion.core.context.features import FeatureBuilder
from wot_companion.core.rules.base import RuleContext
from wot_companion.core.rules.hp_management import HpManagementRule
from wot_companion.core.rules.initial_plan import InitialPlanRule
from wot_companion.core.rules.positive import PositiveReinforcementRule
from wot_companion.core.rules.reaction import HitTakenReactionRule
from wot_companion.core.rules.retreat import RetreatRule
from wot_companion.core.rules.rotation import NumericAwarenessRule
from wot_companion.core.rules.tempo import TempoInitiativeRule
from wot_companion.knowledge.loader import KnowledgeBase

KB = KnowledgeBase()


def _rc(ctx: BattleContext) -> RuleContext:
    return RuleContext(battle=ctx, features=FeatureBuilder().build(ctx), knowledge=KB)


def test_initial_plan_fires_with_full_context():
    ctx = BattleContext(battle_id="b", start_ms=0, map_id="prokhorovka", spawn="south",
                        vehicle_id="leopard_1", vehicle_role="sniper_medium")
    ctx.composition = TeamComposition(enemy_classes={"medium": 4}, ally_classes={"medium": 3},
                                      ally_count=15, enemy_count=15)
    out = InitialPlanRule().evaluate(_rc(ctx))
    assert len(out) == 1
    assert out[0].category.value == "INITIAL_PLAN"
    assert out[0].context["flank"] == "west"


def test_initial_plan_fallback_without_map():
    # REC-01 : donnee carte absente -> aucun plan invente.
    ctx = BattleContext(battle_id="b", start_ms=0, vehicle_role="sniper_medium")
    assert InitialPlanRule().evaluate(_rc(ctx)) == []


def test_hp_rule_silent_when_hp_unknown():
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = 60
    assert HpManagementRule().evaluate(_rc(ctx)) == []  # fallback sûr


def test_hp_rule_fires_early_low_hp():
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = 60
    ctx.hp_ratio = 0.4
    out = HpManagementRule().evaluate(_rc(ctx))
    assert len(out) == 1
    assert out[0].action == "PRESERVE_HP"


def test_tempo_rule_requires_inactivity_and_balance():
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = 120
    ctx.contribution_seen = True  # la source fournit degats/assist
    ctx.last_contribution_s = 0  # 120 s sans contribution
    ctx.allies_alive, ctx.enemies_alive = 14, 12  # avantage
    out = TempoInitiativeRule().evaluate(_rc(ctx))
    assert len(out) == 1 and out[0].action == "TAKE_INITIATIVE"


def test_tempo_rule_silent_without_contribution_data():
    # Faux positif evite : sans donnee de contribution, pas de conseil de tempo.
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = 120
    ctx.last_contribution_s = 0
    ctx.allies_alive, ctx.enemies_alive = 14, 12
    assert TempoInitiativeRule().evaluate(_rc(ctx)) == []


def test_tempo_rule_silent_when_outnumbered():
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = 120
    ctx.contribution_seen = True
    ctx.last_contribution_s = 0
    ctx.allies_alive, ctx.enemies_alive = 8, 12  # inferiorite -> pas d'initiative
    assert TempoInitiativeRule().evaluate(_rc(ctx)) == []


def test_retreat_rule_fires_on_flank_collapse_with_hp():
    ctx = BattleContext(battle_id="b", start_ms=0, map_id="himmelsdorf", player_flank="town")
    ctx.elapsed_s = 100
    ctx.hp_ratio = 0.8
    ctx.last_ally_loss_s = 100
    ctx.flank_ally_losses = {"town": 2}
    out = RetreatRule().evaluate(_rc(ctx))
    assert len(out) == 1 and out[0].action == "PREPARE_RETREAT"


def test_rotation_rule_silent_without_team_count():
    # Fallback sûr : sans equilibre numerique connu, pas de conseil.
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = 300  # milieu de partie
    assert NumericAwarenessRule().evaluate(_rc(ctx)) == []


def test_rotation_rule_fires_mid_game_advantage():
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = 300  # phase MID
    ctx.allies_alive, ctx.enemies_alive = 10, 7  # ecart de 3, > 6 chars au total
    out = NumericAwarenessRule().evaluate(_rc(ctx))
    assert len(out) == 1 and out[0].action == "EXPLOIT_ADVANTAGE"


def test_rotation_rule_fires_mid_game_disadvantage():
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = 300
    ctx.allies_alive, ctx.enemies_alive = 7, 10
    out = NumericAwarenessRule().evaluate(_rc(ctx))
    assert len(out) == 1 and out[0].action == "REGROUP_STRONG_SIDE"


def test_rotation_rule_silent_on_small_gap():
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = 300
    ctx.allies_alive, ctx.enemies_alive = 10, 9  # ecart de 1 : bruit normal
    assert NumericAwarenessRule().evaluate(_rc(ctx)) == []


def test_rotation_rule_silent_in_early_phase():
    # Early est couvert par le plan initial : pas de doublon.
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = 30
    ctx.allies_alive, ctx.enemies_alive = 15, 12
    assert NumericAwarenessRule().evaluate(_rc(ctx)) == []


def test_rotation_rule_no_push_when_low_hp():
    # Avantage numerique mais HP bas -> on ne pousse pas a l'attaque.
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = 300
    ctx.allies_alive, ctx.enemies_alive = 10, 7
    ctx.hp_ratio = 0.3
    assert NumericAwarenessRule().evaluate(_rc(ctx)) == []


def test_positive_rule_fires_when_healthy_midgame():
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = 300  # hors ouverture
    ctx.hp_ratio = 0.85
    out = PositiveReinforcementRule().evaluate(_rc(ctx))
    assert len(out) == 1 and out[0].action == "ENCOURAGE_HP"
    assert out[0].severity.value == "POSITIVE"


def test_positive_rule_silent_in_early_phase():
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = 30
    ctx.hp_ratio = 0.95
    assert PositiveReinforcementRule().evaluate(_rc(ctx)) == []


def test_positive_rule_silent_when_hurt():
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = 300
    ctx.hp_ratio = 0.4  # abime -> pas de compliment
    assert PositiveReinforcementRule().evaluate(_rc(ctx)) == []


def test_positive_rule_silent_when_outnumbered():
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = 300
    ctx.hp_ratio = 0.9
    ctx.allies_alive, ctx.enemies_alive = 5, 9  # nette inferiorite
    assert PositiveReinforcementRule().evaluate(_rc(ctx)) == []


def test_reaction_fires_on_recent_damage():
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = 200
    ctx.hp_ratio = 0.7
    ctx.last_damage_taken_s = 199  # touche il y a 1 s
    ctx.last_damage_taken_ratio = 0.15
    out = HitTakenReactionRule().evaluate(_rc(ctx))
    assert len(out) == 1 and out[0].action == "USE_ARMOR"
    assert out[0].min_interval_s > 0  # cadence propre a la reaction


def test_reaction_silent_without_recent_damage():
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = 200
    ctx.hp_ratio = 0.7
    ctx.last_damage_taken_s = 150  # trop ancien (> fenetre)
    assert HitTakenReactionRule().evaluate(_rc(ctx)) == []


def test_reaction_breaks_contact_when_low():
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = 200
    ctx.hp_ratio = 0.2
    ctx.last_damage_taken_s = 200
    ctx.last_damage_taken_ratio = 0.1
    out = HitTakenReactionRule().evaluate(_rc(ctx))
    assert len(out) == 1 and out[0].action == "BREAK_CONTACT"


def test_context_tracks_damage_taken():
    from wot_companion.core.events import EventType, RawEvent
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = 50
    ctx.apply(RawEvent(EventType.PLAYER_HP_CHANGED.value, {"hp": 1000, "max_hp": 1000}))
    ctx.elapsed_s = 60
    ctx.apply(RawEvent(EventType.PLAYER_HP_CHANGED.value, {"hp": 700, "max_hp": 1000}))
    assert ctx.last_damage_taken_s == 60
    assert abs(ctx.last_damage_taken_ratio - 0.3) < 1e-6
    # Une remontee de HP (kit) n'est PAS un degat subi.
    ctx.elapsed_s = 70
    ctx.apply(RawEvent(EventType.PLAYER_HP_CHANGED.value, {"hp": 900, "max_hp": 1000}))
    assert ctx.last_damage_taken_s == 60  # inchange
