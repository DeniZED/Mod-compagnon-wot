"""Utilité apprise (§8) : convertir des statistiques de replays en une note
d'utilité FIABLE et comparable, relative à une référence.

Principe (aucune IA, que de la statistique) : une direction/zone n'est « bonne »
que si elle **bat la référence** de sa (carte, phase, classe) — pas parce qu'elle
est populaire. On mesure l'avantage par composante (survie, dégâts, victoire),
on l'agrège selon un OBJECTIF configurable, et on ne l'ose que si l'avantage
tient statistiquement :

- **Borne basse de Wilson** sur les taux (survie, victoire) : jamais un ratio
  brut sur petit échantillon. La note de RANG utilise l'estimation ponctuelle
  rétrécie (shrinkage), mais la note de GARDE (`advantage_lb`) utilise la borne
  basse — conservatrice par construction.
- **Shrinkage** vers la référence : une cellule peu échantillonnée est tirée
  vers la moyenne, donc n'émerge pas tant qu'elle n'a pas fait ses preuves.
- **Objectif configurable** : `impact` (survie + dégâts, défaut), `winrate`,
  `mixed`. Si le winrate est absent des données (build antérieur), son poids est
  redistribué → l'objectif dégénère proprement vers l'impact.

Doctrine §1.2/§14 : en cas de doute (échantillon faible, avantage non prouvé),
la note s'effondre → la règle se tait.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Dict, Iterable, Optional

# Objectifs disponibles (choix utilisateur, cf. Settings.utility_objective).
OBJECTIVES = ("impact", "winrate", "mixed")

# Poids par objectif : (winrate, survival, damage). Somme = 1.
_WEIGHTS: Dict[str, Dict[str, float]] = {
    "impact":  {"winrate": 0.0, "survival": 0.40, "damage": 0.60},
    "winrate": {"winrate": 0.70, "survival": 0.20, "damage": 0.10},
    "mixed":   {"winrate": 0.50, "survival": 0.25, "damage": 0.25},
}

# Constantes de fiabilité (calibrables). z=1.64 ≈ borne basse unilatérale à 95 %.
_Z = 1.64
_SHRINK_K = 15.0          # force du tirage vers la référence (en "chars")
# Échelles de normalisation de l'avantage -> [-1, 1] : au-delà, saturation.
_RATE_SCALE = 0.20        # +20 points de taux (survie/win) = avantage plein
_DMG_SCALE = 0.50         # +50 % d'impact combat vs référence = avantage plein
_EPS = 1e-9


def wilson_lower_bound(successes: float, n: float, z: float = _Z) -> float:
    """Borne basse de l'intervalle de Wilson pour une proportion.

    Estimation prudente d'un taux : petit n -> borne basse très en-dessous du
    ratio observé, donc un taux flatteur mais peu échantillonné ne "passe" pas.
    """
    if n <= 0:
        return 0.0
    p = _clip(successes / n, 0.0, 1.0)
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = p + z2 / (2.0 * n)
    margin = z * sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)
    return _clip((centre - margin) / denom, 0.0, 1.0)


def _clip(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _shrink(metric: float, baseline: float, n: float, k: float = _SHRINK_K) -> float:
    """Estimation rétrécie vers la référence (tire les petits n vers la moyenne)."""
    if n <= 0:
        return baseline
    return (n * metric + k * baseline) / (n + k)


@dataclass(frozen=True)
class Baseline:
    """Référence moyenne d'un groupe (carte, phase[, classe])."""
    survival: float = 0.0
    damage: float = 0.0            # impact combat moyen (dégâts + assist), brut
    winrate: Optional[float] = None
    sample: int = 0


@dataclass(frozen=True)
class UtilityScore:
    """Note d'utilité d'un candidat, relative à sa référence.

    - `value` ∈ [0,1] : 0.5 = niveau de la référence ; >0.5 = au-dessus. Sert au
      CLASSEMENT (estimation ponctuelle rétrécie).
    - `advantage_lb` : avantage agrégé PRUDENT (bornes basses). Sert à la GARDE :
      on ne parle que si `advantage_lb >= margin`.
    - `confidence` ∈ [0,1] : fiabilité globale (échantillon).
    """
    value: float
    advantage_lb: float
    confidence: float

    @property
    def above_baseline(self) -> bool:
        return self.value > 0.5


def _objective_weights(objective: str, has_winrate: bool) -> Dict[str, float]:
    w = dict(_WEIGHTS.get(objective, _WEIGHTS["impact"]))
    if not has_winrate and w["winrate"] > 0.0:
        # Winrate indisponible : redistribuer son poids sur survie + dégâts au
        # prorata, pour que l'objectif dégénère proprement vers l'impact.
        wr = w.pop("winrate")
        rest = w["survival"] + w["damage"]
        if rest <= 0:
            w = {"survival": 0.5, "damage": 0.5}
        else:
            w["survival"] += wr * w["survival"] / rest
            w["damage"] += wr * w["damage"] / rest
        w["winrate"] = 0.0
    return w


class UtilityModel:
    """Score une connaissance (zone/route) en utilité relative à sa référence."""

    def __init__(self, objective: str = "impact",
                 min_sample: int = 8, min_advantage: float = 0.05,
                 keep_floor: float = 0.5) -> None:
        self.objective = objective if objective in OBJECTIVES else "impact"
        self.min_sample = min_sample
        self.min_advantage = min_advantage
        # Plancher de CONSERVATION : une option est gardée si sa note ponctuelle
        # (rétrécie) atteint ce niveau. 0.5 = au moins au niveau de la référence.
        # Plus souple que `passes()` (borne basse) : filtre les options clairement
        # SOUS la moyenne sans réduire l'affichage au silence quasi total.
        self.keep_floor = keep_floor

    def score(
        self,
        *,
        survival: float,
        damage: float,
        sample: int,
        baseline: Baseline,
        winrate: Optional[float] = None,
    ) -> UtilityScore:
        """Note un candidat. `survival`/`winrate` en taux [0,1], `damage` en impact
        combat brut. `baseline` = moyenne du groupe."""
        n = max(int(sample), 0)
        has_wr = winrate is not None and baseline.winrate is not None
        w = _objective_weights(self.objective, has_wr)

        # --- Composantes : avantage ponctuel (rang) et borne basse (garde) ---
        # Survie (taux) : ponctuel rétréci, borne basse de Wilson.
        surv_pt = _advantage_rate(_shrink(survival, baseline.survival, n),
                                  baseline.survival)
        surv_lb = _advantage_rate(wilson_lower_bound(survival * n, n),
                                  baseline.survival)
        # Dégâts (continu) : lift relatif rétréci ; borne basse ≈ ponctuel
        # atténué par la fiabilité d'échantillon (pas d'IC analytique simple).
        dmg_pt = _advantage_dmg(_shrink(damage, baseline.damage, n), baseline.damage)
        dmg_lb = dmg_pt * _sample_conf(n)
        # Victoire (taux), si disponible.
        if has_wr:
            win_pt = _advantage_rate(_shrink(winrate, baseline.winrate, n),
                                     baseline.winrate)
            win_lb = _advantage_rate(wilson_lower_bound(winrate * n, n),
                                     baseline.winrate)
        else:
            win_pt = win_lb = 0.0

        adv_pt = (w["winrate"] * win_pt + w["survival"] * surv_pt
                  + w["damage"] * dmg_pt)
        adv_lb = (w["winrate"] * win_lb + w["survival"] * surv_lb
                  + w["damage"] * dmg_lb)

        value = _clip(0.5 + 0.5 * adv_pt, 0.0, 1.0)
        conf = _sample_conf(n)
        # Sous le plancher d'échantillon : on n'ose rien (garde effondrée).
        if n < self.min_sample:
            adv_lb = min(adv_lb, 0.0)
        return UtilityScore(value=value, advantage_lb=adv_lb, confidence=conf)

    def passes(self, score: UtilityScore) -> bool:
        """Garde STRICTE : avantage prudent (borne basse) au-dessus de la marge."""
        return score.advantage_lb >= self.min_advantage

    def keep(self, score: UtilityScore) -> bool:
        """Filtre SOUPLE : conserver si au niveau de la référence ou au-dessus.

        Utilisé pour l'affichage live (zones, priors) : on écarte le clairement
        sous-la-moyenne, mais on garde de quoi conseiller/afficher. Le classement
        par `value` fait remonter les meilleures options."""
        return score.value >= self.keep_floor


def _advantage_rate(rate: float, baseline: float) -> float:
    """Avantage d'un taux vs référence, normalisé et borné à [-1, 1]."""
    return _clip((rate - baseline) / _RATE_SCALE, -1.0, 1.0)


def _advantage_dmg(damage: float, baseline: float) -> float:
    """Avantage d'impact combat vs référence (lift relatif), borné à [-1, 1]."""
    base = max(baseline, _EPS)
    return _clip((damage / base - 1.0) / _DMG_SCALE, -1.0, 1.0)


def _sample_conf(n: int, k: float = _SHRINK_K) -> float:
    return n / (n + k) if n > 0 else 0.0


def compute_baseline(rows: Iterable[dict]) -> Baseline:
    """Référence moyenne pondérée-échantillon sur un ensemble de connaissances.

    Chaque `row` : {survival, damage, sample, winrate?}. Le winrate n'entre dans
    la référence que si TOUTES les lignes le portent (sinon référence winrate=None).
    """
    tot = 0.0
    surv = dmg = win = 0.0
    all_win = True
    for r in rows:
        s = float(r.get("sample", 0) or 0)
        if s <= 0:
            continue
        tot += s
        surv += float(r.get("survival", 0.0)) * s
        dmg += float(r.get("damage", 0.0)) * s
        wr = r.get("winrate")
        if wr is None:
            all_win = False
        else:
            win += float(wr) * s
    if tot <= 0:
        return Baseline()
    return Baseline(
        survival=surv / tot, damage=dmg / tot,
        winrate=(win / tot) if all_win else None, sample=int(tot),
    )
