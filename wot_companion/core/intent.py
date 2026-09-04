"""Intentions tactiques : réduction d'une action de conseil à une INTENTION.

Brique partagée (§11) : l'arbitre et le backtester raisonnent sur des intentions
grossières (avancer / reculer / basculer / cap…) plutôt que sur des libellés
d'action précis. Cela permet une COHÉRENCE inter-familles : quand une décision
stratégique forte est active (ex. décrocher), on empêche une autre famille de
conseiller l'inverse (ex. « repositionne-toi au front »).
"""
from __future__ import annotations

from typing import Optional

ADVANCE = "ADVANCE"
RETREAT = "RETREAT"
RELOCATE = "RELOCATE"
CAP = "CAP"
CAUTION = "CAUTION"
OTHER = "OTHER"


def intent_of(action: Optional[str]) -> str:
    """Réduit un libellé d'action à une intention tactique grossière."""
    if not action:
        return OTHER
    a = action.upper()
    if a.startswith("PUSH") or "INITIATIVE" in a:
        return ADVANCE
    if "DISENGAGE" in a or "FALL_BACK" in a or "RETREAT" in a \
            or "REGROUP" in a or "OUTNUMBERED" in a:
        return RETREAT
    if "RELOCATE" in a or "REPOSITION" in a or "ROTATE" in a \
            or "PLAYBOOK" in a or a.startswith("OPEN") or "DIRECTION" in a:
        return RELOCATE
    if "CAP" in a:
        return CAP
    if "SAFE" in a or "PRESERVE" in a:
        return CAUTION
    return OTHER


# Intentions strictement OPPOSÉES (contradiction symétrique) : pour les métriques.
_OPPOSED = {(ADVANCE, RETREAT), (RETREAT, ADVANCE)}

# Quand une intention STRATÉGIQUE est active (clé), les intentions à SUPPRIMER
# chez les autres familles (valeurs) : elles enverraient un message incohérent.
# Ex. en décrochage, on ne laisse pas « pousser » NI « repositionne-toi au front ».
_SUPPRESS = {
    RETREAT: {ADVANCE, RELOCATE},
    ADVANCE: {RETREAT},
    CAP: {ADVANCE},
}


def is_contradiction(intent_a: str, intent_b: str) -> bool:
    """Vrai si les deux intentions sont strictement opposées (avancer/reculer)."""
    return (intent_a, intent_b) in _OPPOSED


def strategic_suppresses(strategic_intent: str, candidate_intent: str) -> bool:
    """Vrai si une décision stratégique `strategic_intent` doit faire TAIRE un
    conseil d'intention `candidate_intent` (cohérence inter-familles)."""
    return candidate_intent in _SUPPRESS.get(strategic_intent, frozenset())
