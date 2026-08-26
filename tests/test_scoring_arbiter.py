"""Tests du Scorer et de l'AdviceArbiter (anti-spam, arbitrage)."""
from __future__ import annotations

from wot_companion.core.advice import CandidateAdvice
from wot_companion.core.context.features import Features, BattlePhase
from wot_companion.core.scoring.arbiter import AdviceArbiter
from wot_companion.core.scoring.scorer import Scorer
from wot_companion.settings import AdviceCategory, Settings, Severity


def _features(phase=BattlePhase.MID) -> Features:
    return Features(phase=phase, hp_ratio=0.8, numeric_balance=0,
                    time_since_contribution_s=0, flank_collapsing=False,
                    outnumbered_locally=False, endgame_few_left=False,
                    contribution_total=0, took_damage_recently=False,
                    damage_taken_ratio=0.0, nearest_ally_dist=None, allies_near=0,
                    enemies_spotted_near=0, isolated=False, overextended=False)


def _cand(rule_id, cat, urgency=0.8, impact=0.8, confidence=1.0,
          severity=Severity.INFO, action="A") -> CandidateAdvice:
    return CandidateAdvice(rule_id=rule_id, category=cat, action=action,
                           reason_code="R", template_key="tempo_take_initiative",
                           severity=severity, urgency=urgency, impact=impact,
                           confidence=confidence)


def test_scorer_bounds():
    s = Scorer()
    b = s.score(_cand("r", AdviceCategory.TEMPO, urgency=1, impact=1, confidence=1))
    assert b.urgency == 30 and b.confidence == 20 and b.impact == 25
    assert b.total <= 85  # sans bonus contexte joueur


def test_low_score_prefers_silence():
    settings = Settings()
    arb = AdviceArbiter(settings)
    arb.set_clock(200)
    weak = _cand("weak", AdviceCategory.TEMPO, urgency=0.1, impact=0.1, confidence=0.2)
    assert arb.select([weak], features=_features()) is None


def test_single_output_highest_score_wins_tie_break():
    # REC-02 : deux regles urgentes -> une seule sortie.
    settings = Settings()
    arb = AdviceArbiter(settings)
    arb.set_clock(200)
    c1 = _cand("aaa.rule", AdviceCategory.TEMPO, urgency=0.9, impact=0.9)
    c2 = _cand("bbb.rule", AdviceCategory.HP, urgency=0.9, impact=0.9)
    chosen = arb.select([c1, c2], features=_features())
    assert chosen is not None
    # Scores egaux -> tie-break deterministe par rule_id.
    assert chosen.rule_id == "aaa.rule"


def test_cooldown_blocks_repetition():
    # REC-03 : meme conseil repete -> bloque par le cooldown.
    settings = Settings()
    arb = AdviceArbiter(settings)
    arb.set_clock(200)
    c = _cand("tempo.r", AdviceCategory.TEMPO)
    assert arb.select([c], features=_features()) is not None
    arb.set_clock(210)  # 10 s plus tard, < cooldown categorie (60 s)
    assert arb.select([c], features=_features()) is None
    arb.set_clock(400)  # bien au-dela du cooldown
    assert arb.select([c], features=_features()) is not None


def test_reaction_min_interval_overrides_category_cooldown():
    # Une reaction (min_interval_s) doit pouvoir se repeter bien avant le cooldown
    # de categorie (60 s), mais reste espacee par son intervalle propre.
    settings = Settings()
    arb = AdviceArbiter(settings)
    react = _cand("reaction.hit", AdviceCategory.REACTION, urgency=0.6, impact=0.5)
    react.min_interval_s = 9.0
    arb.set_clock(100)
    assert arb.select([react], features=_features()) is not None
    arb.set_clock(105)  # < intervalle propre -> bloque
    assert arb.select([react], features=_features()) is None
    arb.set_clock(110)  # >= 9 s -> repasse, bien avant les 60 s de categorie
    assert arb.select([react], features=_features()) is not None


def test_critical_bypasses_global_cooldown_but_not_category():
    settings = Settings()
    arb = AdviceArbiter(settings)
    arb.set_clock(100)
    info = _cand("info.r", AdviceCategory.TEMPO)
    assert arb.select([info], features=_features()) is not None
    # 2 s plus tard : global cooldown actif, mais un critique d'une AUTRE
    # categorie doit pouvoir passer.
    arb.set_clock(102)
    crit = _cand("crit.r", AdviceCategory.RETREAT, severity=Severity.CRITICAL)
    assert arb.select([crit], features=_features()) is not None
    # Le meme critique 5 s apres est bloque par le cooldown de categorie.
    arb.set_clock(107)
    assert arb.select([crit], features=_features()) is None


def test_early_game_cap_limits_non_critical():
    settings = Settings()
    settings.anti_spam.max_early_advices = 2
    settings.anti_spam.global_cooldown_s = 0  # isole le plafond early
    settings.anti_spam.category_cooldown_s = 0
    arb = AdviceArbiter(settings)
    shown = 0
    for i in range(5):
        arb.set_clock(10 + i)
        c = _cand(f"r{i}", AdviceCategory.TEMPO, action=f"A{i}")
        if arb.select([c], features=_features(BattlePhase.EARLY)) is not None:
            shown += 1
    assert shown == 2


def test_silent_personality_only_critical():
    settings = Settings()
    settings.personality = settings.personality.SILENCIEUX
    arb = AdviceArbiter(settings)
    arb.set_clock(200)
    info = _cand("i", AdviceCategory.TEMPO)
    assert arb.select([info], features=_features()) is None
    crit = _cand("c", AdviceCategory.RETREAT, severity=Severity.CRITICAL)
    assert arb.select([crit], features=_features()) is not None
