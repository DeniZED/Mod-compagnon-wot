"""Scoring d'ACTIONS tactiques par utilité — le « cerveau » de décision.

Au lieu d'une échelle de priorités figée (si A sinon si B...), on évalue un jeu
FIXE d'actions candidates et on note chacune par une utilité (valeur attendue)
dérivée de la situation. La meilleure action l'emporte ; si c'est TENIR (HOLD),
on se tait (pas de conseil superflu).

Modèle transparent et testable : chaque utilité est une somme de contributions
explicites, bornée à [0, 1]. Entrées = `StrategicPicture` (état de partie lu en
Fair Play) + quelques features. Aucune position d'ennemi non spotté.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class TacticalAction(str, Enum):
    HOLD = "hold"                 # tenir / continuer d'échanger d'ici (silence)
    RELOCATE = "relocate"         # basculer vers le front (secteur mort)
    PUSH = "push"                 # presser l'avantage
    FALL_BACK = "fall_back"       # repli défensif (sous-nombre)
    DISENGAGE = "disengage"       # décrocher MAINTENANT (survie)
    GO_CAP = "go_cap"             # aller capturer (fin de partie)


@dataclass
class ScoredAction:
    action: TacticalAction
    utility: float
    factors: Dict[str, float] = field(default_factory=dict)


def _clamp(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else float(x)


def score_actions(sp) -> List[ScoredAction]:
    """Note toutes les actions pour la situation `sp` (StrategicPicture).

    Retourne la liste triée par utilité décroissante. `sp` doit fournir :
    hp_ratio, balance, momentum, sector_calm, enemies_near_me, allies_near_me,
    healthy, late, enemies_alive, et (via features) overextended/took_damage.
    """
    hp = sp.hp_ratio if sp.hp_ratio is not None else 1.0
    bal = sp.balance
    calm = sp.sector_calm
    near_e = sp.enemies_near_me
    healthy = sp.healthy
    late = sp.late
    momentum = sp.momentum
    overext = bool(getattr(sp, "overextended", False))
    took_dmg = bool(getattr(sp, "took_damage", False))

    out = [
        ScoredAction(TacticalAction.HOLD, _u_hold(momentum, healthy, overext, calm)),
        ScoredAction(TacticalAction.DISENGAGE,
                     _u_disengage(hp, near_e, took_dmg, overext)),
        ScoredAction(TacticalAction.FALL_BACK, _u_fall_back(bal, late, overext)),
        ScoredAction(TacticalAction.RELOCATE,
                     _u_relocate(calm, momentum, healthy)),
        ScoredAction(TacticalAction.PUSH, _u_push(momentum, healthy, calm, bal)),
        ScoredAction(TacticalAction.GO_CAP,
                     _u_cap(late, bal, sp.enemies_alive)),
    ]
    out.sort(key=lambda s: s.utility, reverse=True)
    return out


# --- Utilités par action (bornées [0,1]) ----------------------------------- #
def _u_hold(momentum, healthy, overext, calm) -> float:
    v = 0.38
    if momentum == "even":
        v += 0.10
    if healthy:
        v += 0.08
    if overext:
        v -= 0.25            # rester surétendu est risqué
    if calm:
        v -= 0.22            # tenir un secteur mort ne sert à rien
    return _clamp(v)


def _u_disengage(hp, near_e, took_dmg, overext) -> float:
    threat = 1.0 if (near_e >= 1 or took_dmg) else 0.35
    if hp >= 0.45:
        # HP corrects : décrocher seulement si très exposé.
        return _clamp((0.3 if (overext and near_e >= 2) else 0.0))
    base = (0.45 - hp) / 0.45 * threat        # monte quand HP chute sous 45 %
    return _clamp(base + (0.12 if took_dmg else 0.0))


def _u_fall_back(bal, late, overext) -> float:
    if bal is None:
        return _clamp(0.3 if overext else 0.0)
    if bal >= -1:
        return _clamp(0.32 if overext else 0.0)
    sev = min(1.0, (-bal) / 5.0)              # -2 -> 0.4 ; -5 -> 1.0
    return _clamp(0.40 + sev * 0.5 + (0.1 if late else 0.0))


def _u_relocate(calm, momentum, healthy) -> float:
    if not calm:
        return 0.0
    if momentum == "losing":
        return 0.12
    return _clamp(0.55 + (0.15 if momentum == "winning" else 0.0)
                  + (0.1 if healthy else -0.2))


def _u_push(momentum, healthy, calm, bal) -> float:
    if momentum != "winning" or not healthy or calm:
        return 0.0
    sev = min(1.0, (bal or 0) / 5.0)
    return _clamp(0.45 + sev * 0.3)


def _u_cap(late, bal, enemies_alive) -> float:
    if not late or bal is None or enemies_alive is None:
        return 0.0
    # Fin de partie, avantage numérique et peu d'ennemis restants -> conclure au cap.
    if bal >= 1 and enemies_alive <= 3:
        return _clamp(0.5 + (3 - enemies_alive) * 0.1)
    return 0.0
