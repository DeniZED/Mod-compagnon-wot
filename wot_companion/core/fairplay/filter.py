"""FairPlayFilter : filtre bloquant et mode audit.

Responsabilites (section 10.1) :
  - classer chaque evenement ALLOW / BLOCK et le loguer ;
  - retirer tout champ non whiteliste d'un payload autorise (pas d'invention) ;
  - refuser au chargement toute regle dependant d'un champ non whiteliste ;
  - produire un rapport d'audit des donnees consommees par fonction.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable

from ..events import RawEvent, FORBIDDEN_EVENT_TYPES
from .whitelist import FairPlayClass, allowed_fields, is_event_allowed

logger = logging.getLogger("wot_companion.fairplay")


@dataclass
class FairPlayViolation:
    """Motif d'un rejet, pour le journal et l'audit."""
    kind: str            # "forbidden_event" | "unknown_event" | "forbidden_field" | "rule_dependency"
    subject: str         # type d'evenement ou id de regle
    detail: str


@dataclass
class FilteredEvent:
    """Resultat du filtrage d'un evenement."""
    event: RawEvent | None
    fairplay_class: FairPlayClass
    violations: list[FairPlayViolation] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.fairplay_class is FairPlayClass.ALLOW and self.event is not None


@dataclass
class FairPlayReport:
    """Rapport d'audit : quelles donnees ont ete consommees, quels rejets."""
    consumed_fields: dict[str, set[str]] = field(default_factory=dict)
    violations: list[FairPlayViolation] = field(default_factory=list)
    allowed_count: int = 0
    blocked_count: int = 0

    def as_dict(self) -> dict:
        return {
            "consumed_fields": {k: sorted(v) for k, v in sorted(self.consumed_fields.items())},
            "violations": [v.__dict__ for v in self.violations],
            "allowed_count": self.allowed_count,
            "blocked_count": self.blocked_count,
        }


class FairPlayFilter:
    """Point de passage obligatoire entre l'adapter et le moteur."""

    def __init__(self, audit: bool = True) -> None:
        self.audit = audit
        self.report = FairPlayReport()

    def filter_event(self, event: RawEvent) -> FilteredEvent:
        """Classe et nettoie un evenement.

        - type interdit -> BLOCK et journalisation ;
        - type inconnu (hors whitelist) -> BLOCK ;
        - type autorise -> on ne garde que les champs whitelistes (les autres
          sont retires, jamais remplaces arbitrairement).
        """
        etype = event.event_type

        if etype in FORBIDDEN_EVENT_TYPES:
            return self._block(
                event, "forbidden_event", etype,
                "Type d'evenement explicitement interdit par la politique Fair Play.",
            )

        if not is_event_allowed(etype):
            return self._block(
                event, "unknown_event", etype,
                "Type d'evenement absent de la whitelist.",
            )

        allowed = allowed_fields(etype)
        clean_payload = {}
        violations: list[FairPlayViolation] = []
        for key, value in event.payload.items():
            if key in allowed:
                clean_payload[key] = value
            else:
                v = FairPlayViolation(
                    "forbidden_field", etype,
                    f"Champ '{key}' non whiteliste sur l'evenement {etype}.",
                )
                violations.append(v)
                logger.warning("FairPlay: %s", v.detail)

        clean_event = RawEvent(
            event_type=etype,
            payload=clean_payload,
            timestamp_ms=event.timestamp_ms,
            battle_id=event.battle_id,
            event_id=event.event_id,
        )

        if self.audit:
            self.report.consumed_fields.setdefault(etype, set()).update(clean_payload.keys())
            self.report.allowed_count += 1
            self.report.violations.extend(violations)

        return FilteredEvent(clean_event, FairPlayClass.ALLOW, violations)

    def validate_rule(self, rule_id: str, dependencies: Iterable[str]) -> list[FairPlayViolation]:
        """Refuse une regle qui depend d'un champ non whiteliste (section 10.1).

        `dependencies` = liste de "EVENT_TYPE.field" ou "EVENT_TYPE" que la regle
        declare consommer. Retourne la liste des violations (vide = regle valide).
        """
        from .whitelist import is_event_allowed as _evt_ok, is_field_allowed as _field_ok

        violations: list[FairPlayViolation] = []
        for dep in dependencies:
            if "." in dep:
                etype, fname = dep.split(".", 1)
                ok = _evt_ok(etype) and _field_ok(etype, fname)
            else:
                etype, fname = dep, None
                ok = _evt_ok(etype)
            if not ok:
                v = FairPlayViolation(
                    "rule_dependency", rule_id,
                    f"La regle '{rule_id}' depend de '{dep}' qui n'est pas whiteliste.",
                )
                violations.append(v)
        if violations and self.audit:
            self.report.violations.extend(violations)
        return violations

    def _block(self, event: RawEvent, kind: str, subject: str, detail: str) -> FilteredEvent:
        v = FairPlayViolation(kind, subject, detail)
        logger.warning("FairPlay BLOCK: %s", detail)
        if self.audit:
            self.report.blocked_count += 1
            self.report.violations.append(v)
        return FilteredEvent(None, FairPlayClass.BLOCK, [v])
