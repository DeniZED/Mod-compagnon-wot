"""Base de connaissances tactique : rôles de chars, cartes, plans de position.

Donnees versionnees (KNOWLEDGE_VERSION) et editables sans toucher au code
(section 17.2 : Tactical KB Editor). Chargees via `KnowledgeBase`.
"""
from .loader import KnowledgeBase, TacticalPlan

__all__ = ["KnowledgeBase", "TacticalPlan"]
