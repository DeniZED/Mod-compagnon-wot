"""Tests de l'utilité apprise (§8) : Wilson, shrinkage, objectifs, garde."""
from __future__ import annotations

from wot_companion.tactical_knowledge.utility import (
    Baseline, UtilityModel, compute_baseline, wilson_lower_bound)


# ---- Wilson lower bound -----------------------------------------------------
def test_wilson_penalises_small_samples():
    # Même taux (80 %), mais n=5 doit donner une borne bien plus basse que n=200.
    lb_small = wilson_lower_bound(4, 5)
    lb_large = wilson_lower_bound(160, 200)
    assert lb_small < lb_large
    assert lb_small < 0.8 and lb_large < 0.8      # toujours sous le ratio observé
    assert lb_large > 0.7                          # gros n -> proche du ratio


def test_wilson_bounds():
    assert wilson_lower_bound(0, 0) == 0.0
    assert 0.0 <= wilson_lower_bound(1, 1) <= 1.0
    assert wilson_lower_bound(0, 50) == 0.0


# ---- Avantage relatif à la référence ---------------------------------------
def test_below_baseline_not_above():
    m = UtilityModel(objective="impact")
    base = Baseline(survival=0.5, damage=1500.0, sample=500)
    # Pire que la référence sur les deux axes -> value < 0.5, garde refuse.
    sc = m.score(survival=0.3, damage=900.0, sample=100, baseline=base)
    assert not sc.above_baseline
    assert not m.passes(sc)


def test_above_baseline_well_sampled_passes():
    m = UtilityModel(objective="impact")
    base = Baseline(survival=0.5, damage=1500.0, sample=500)
    # Nettement au-dessus, bien échantillonné -> passe la garde.
    sc = m.score(survival=0.72, damage=2400.0, sample=120, baseline=base)
    assert sc.above_baseline
    assert m.passes(sc)
    assert sc.confidence > 0.8


def test_small_sample_collapses_guard():
    m = UtilityModel(objective="impact", min_sample=8)
    base = Baseline(survival=0.5, damage=1500.0, sample=500)
    # Excellent taux mais n=3 : la garde s'effondre (silence > doute).
    sc = m.score(survival=1.0, damage=3000.0, sample=3, baseline=base)
    assert not m.passes(sc)


def test_shrinkage_pulls_thin_cell_toward_baseline():
    m = UtilityModel(objective="impact")
    base = Baseline(survival=0.5, damage=1500.0, sample=500)
    thin = m.score(survival=0.9, damage=3000.0, sample=10, baseline=base)
    thick = m.score(survival=0.9, damage=3000.0, sample=300, baseline=base)
    # Même métriques : la cellule épaisse note plus haut (moins tirée vers la moy.)
    assert thick.value > thin.value


# ---- Objectifs configurables -----------------------------------------------
def test_objective_impact_ignores_winrate():
    m = UtilityModel(objective="impact")
    base = Baseline(survival=0.5, damage=1500.0, winrate=0.5, sample=500)
    # Winrate désastreux mais impact excellent : en mode impact, ça reste bon.
    sc = m.score(survival=0.7, damage=2400.0, winrate=0.1, sample=150, baseline=base)
    assert sc.above_baseline


def test_objective_winrate_uses_winrate():
    m = UtilityModel(objective="winrate")
    base = Baseline(survival=0.5, damage=1500.0, winrate=0.5, sample=500)
    good = m.score(survival=0.5, damage=1500.0, winrate=0.75, sample=200, baseline=base)
    bad = m.score(survival=0.5, damage=1500.0, winrate=0.25, sample=200, baseline=base)
    assert good.value > bad.value


def test_winrate_objective_degrades_to_impact_when_absent():
    # Données sans winrate (build antérieur) : l'objectif winrate ne doit pas
    # planter ni tout mettre à 0.5 ; il retombe sur l'impact.
    m = UtilityModel(objective="winrate")
    base = Baseline(survival=0.5, damage=1500.0, winrate=None, sample=500)
    sc = m.score(survival=0.72, damage=2400.0, winrate=None, sample=150, baseline=base)
    assert sc.above_baseline
    assert m.passes(sc)


# ---- Baselines -------------------------------------------------------------
def test_compute_baseline_sample_weighted():
    rows = [
        {"survival": 0.4, "damage": 1000.0, "sample": 100},
        {"survival": 0.6, "damage": 2000.0, "sample": 300},
    ]
    b = compute_baseline(rows)
    # Pondéré échantillon : tiré vers la 2e ligne (300 vs 100).
    assert abs(b.survival - (0.4 * 100 + 0.6 * 300) / 400) < 1e-6
    assert abs(b.damage - (1000 * 100 + 2000 * 300) / 400) < 1e-6
    assert b.winrate is None                       # aucune ligne ne le porte


def test_compute_baseline_winrate_only_if_all_rows_have_it():
    rows = [
        {"survival": 0.5, "damage": 1500.0, "sample": 100, "winrate": 0.5},
        {"survival": 0.5, "damage": 1500.0, "sample": 100},   # pas de winrate
    ]
    assert compute_baseline(rows).winrate is None
    rows2 = [
        {"survival": 0.5, "damage": 1500.0, "sample": 100, "winrate": 0.5},
        {"survival": 0.5, "damage": 1500.0, "sample": 100, "winrate": 0.6},
    ]
    assert compute_baseline(rows2).winrate is not None
