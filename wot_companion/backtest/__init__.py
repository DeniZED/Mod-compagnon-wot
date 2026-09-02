"""Replay Backtester (§15, Étape 6/priorité 5) : évaluer le moteur HORS jeu.

Rejoue une timeline d'états de bataille à travers le VRAI moteur de décision et
mesure la qualité des conseils (redondance, contradictions, silence, flip
d'action…), sans lancer WoT. C'est le FILET qui permet de valider tout
changement (fusion des familles, replay prior, utilité apprise) objectivement :
« le moteur est meilleur si les métriques s'améliorent » (§25).

Déterministe et local. N'introduit aucune donnée non autorisée : la timeline ne
contient que des états Fair Play (position propre, alliés, ennemis spottés, HP,
comptes, phase).
"""
from __future__ import annotations

from .golden import GoldenScenario, GoldenResult, load_golden_dir, run_golden
from .metrics import BacktestMetrics, compute_metrics
from .runner import AdviceRecord, run_timeline
from .timeline import ScenarioTimeline, StateTick, intent_of

__all__ = [
    "ScenarioTimeline", "StateTick", "intent_of",
    "AdviceRecord", "run_timeline",
    "BacktestMetrics", "compute_metrics",
    "GoldenScenario", "GoldenResult", "load_golden_dir", "run_golden",
]
