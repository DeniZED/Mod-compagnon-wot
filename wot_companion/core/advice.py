"""Objets de conseil : candidat (interne) et AdviceObject (sortie du moteur)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from ..settings import AdviceCategory, Severity


@dataclass
class ScoreBreakdown:
    """Detail du score (section 7.2), pour l'explicabilite et le debug."""
    urgency: float = 0.0
    confidence: float = 0.0
    impact: float = 0.0
    player_context: float = 0.0
    repetition_penalty: float = 0.0
    intrusion_penalty: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.urgency + self.confidence + self.impact + self.player_context
            + self.repetition_penalty + self.intrusion_penalty
        )

    def as_dict(self) -> dict[str, float]:
        d = {
            "urgency": self.urgency, "confidence": self.confidence,
            "impact": self.impact, "player_context": self.player_context,
            "repetition_penalty": self.repetition_penalty,
            "intrusion_penalty": self.intrusion_penalty, "total": round(self.total, 2),
        }
        return {k: round(v, 2) for k, v in d.items()}


@dataclass
class CandidateAdvice:
    """Conseil candidat produit par une regle, avant scoring/arbitrage.

    Les composantes brutes (urgency/impact 0..1) sont fournies par la regle ;
    le Scorer les convertit en points selon les poids configures.
    """
    rule_id: str
    category: AdviceCategory
    action: str                 # code d'action (ex: TAKE_INITIATIVE, RETREAT)
    reason_code: str            # code de raison (ex: LOW_CONTRIBUTION_WINDOW)
    template_key: str           # cle du template textuel
    severity: Severity = Severity.INFO
    ttl_seconds: float = 8.0
    cooldown_key: str = ""      # cle de cooldown (souvent = categorie)
    # Signaux bruts normalises (0..1) fournis par la regle :
    urgency: float = 0.0
    impact: float = 0.0
    confidence: float = 0.5     # proportion de signaux fiables disponibles
    # Donnees contextuelles pour le rendu textuel et le journal.
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.cooldown_key:
            self.cooldown_key = self.category.value.lower()


@dataclass
class AdviceObject:
    """Sortie finale du moteur (section 12.2), prete a etre rendue puis affichee."""
    rule_id: str
    category: str
    severity: str
    score: float
    action: str
    reason_code: str
    template_key: str
    ttl_seconds: float
    cooldown_key: str
    fairplay: str = "ALLOW"
    text: str = ""                                   # rempli par le TextRenderer
    breakdown: dict[str, float] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"adv-{uuid.uuid4().hex[:12]}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "rule_id": self.rule_id, "category": self.category,
            "severity": self.severity, "score": round(self.score, 2),
            "action": self.action, "reason_code": self.reason_code,
            "template_key": self.template_key, "ttl_seconds": self.ttl_seconds,
            "cooldown_key": self.cooldown_key, "fairplay": self.fairplay,
            "text": self.text, "breakdown": self.breakdown,
        }
