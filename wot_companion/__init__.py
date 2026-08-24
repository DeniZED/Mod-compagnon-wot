"""WoT Companion - compagnon intelligent World of Tanks.

Coeur tactique deterministe, respectueux de la politique Fair Play de Wargaming.
Le module `wot_companion.core` ne depend que de la bibliotheque standard.
"""

__version__ = "0.1.0"

# Versions declarees dans le cahier des charges (section 12.3).
SCHEMA_VERSION = "1.0"          # evenements IPC / EventEnvelope
RULE_VERSION = "rules-2026.08"  # reproduire une decision
KNOWLEDGE_VERSION = "kb-2026.08"  # chars / cartes / placements
APP_VERSION = __version__
