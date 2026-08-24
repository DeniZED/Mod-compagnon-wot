"""Game Adapter : pont entre le client WoT et le moteur.

Le coeur ne connait QUE l'interface `GameAdapter` et le contrat `EventEnvelope`
(section 9.2). L'adaptateur reel (client WoT) est a valider par POC ; le
`SimulatedAdapter` fournit un flux d'evenements synthetiques pour developper et
tester tout le moteur sans le jeu.
"""
from .base import EventEnvelope, GameAdapter
from .simulator import SimulatedAdapter, Scenario, make_default_scenarios
from .ipc import (
    SocketEventServerAdapter, EnvelopeClient, DEFAULT_HOST, DEFAULT_PORT,
    is_control, CONTROL_PREFIX,
)

__all__ = [
    "EventEnvelope", "GameAdapter", "SimulatedAdapter", "Scenario",
    "make_default_scenarios", "SocketEventServerAdapter", "EnvelopeClient",
    "DEFAULT_HOST", "DEFAULT_PORT", "is_control", "CONTROL_PREFIX",
]
