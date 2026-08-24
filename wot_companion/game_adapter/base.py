"""Interface d'adaptateur et contrat IPC EventEnvelope (section 9.2)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterator

from .. import SCHEMA_VERSION
from ..core.events import RawEvent


@dataclass
class EventEnvelope:
    """Contrat IPC serialisable entre le mod client et le moteur.

    Exemple (section 9.2) :
        {schema_version, timestamp_ms, battle_id, event_type, payload, fairplay_class}
    """
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp_ms: int = 0
    battle_id: str | None = None
    schema_version: str = SCHEMA_VERSION
    fairplay_class: str = "ALLOW"

    def to_raw_event(self) -> RawEvent:
        return RawEvent(
            event_type=self.event_type, payload=dict(self.payload),
            timestamp_ms=self.timestamp_ms, battle_id=self.battle_id,
        )

    @classmethod
    def from_raw_event(cls, evt: RawEvent, fairplay_class: str = "ALLOW") -> "EventEnvelope":
        return cls(
            event_type=evt.event_type, payload=dict(evt.payload),
            timestamp_ms=evt.timestamp_ms, battle_id=evt.battle_id,
            fairplay_class=fairplay_class,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "timestamp_ms": self.timestamp_ms,
            "battle_id": self.battle_id, "event_type": self.event_type,
            "payload": self.payload, "fairplay_class": self.fairplay_class,
        }


class GameAdapter(ABC):
    """Source d'evenements. Isolee derriere une interface pour limiter les
    regressions a chaque patch WoT (section 1.1, robustesse aux mises a jour)."""

    @abstractmethod
    def events(self) -> Iterator[RawEvent]:
        """Produit un flux ordonne de RawEvent (BATTLE_START ... BATTLE_END)."""
        raise NotImplementedError

    def close(self) -> None:
        """Liberation des ressources (override si besoin)."""
