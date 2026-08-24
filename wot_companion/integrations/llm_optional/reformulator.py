"""Reformulation textuelle optionnelle par LLM (section 7.4).

Regles strictes :
  - le LLM REFORMULE un AdviceObject deja valide, il n'invente jamais d'action ;
  - prompt limite au contexte necessaire et filtre ;
  - reponse contrainte en longueur et ton ;
  - fallback instantane vers les templates locaux si indisponible ;
  - aucun secret / donnee personnelle envoye sans consentement explicite.

Aucune implementation reseau n'est fournie par defaut : `NullReformulator`
renvoie le texte local inchange. Un backend LLM concret implementera
`Reformulator.reformulate` en respectant ce contrat.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ...core.advice import AdviceObject


def build_reformulation_prompt(advice: AdviceObject, max_chars: int) -> str:
    """Construit un prompt minimal et filtre (aucune donnee sensible)."""
    return (
        "Reformule ce conseil de jeu World of Tanks en francais, "
        f"en {max_chars} caracteres maximum, ton concis et neutre. "
        "N'ajoute aucune information, ne change pas l'action recommandee.\n"
        f"Action: {advice.action}\n"
        f"Categorie: {advice.category}\n"
        f"Texte de base: {advice.text}"
    )


class Reformulator(ABC):
    @abstractmethod
    def reformulate(self, advice: AdviceObject, max_chars: int) -> str:
        """Retourne un texte reformule, ou le texte d'origine en cas d'echec."""
        raise NotImplementedError


class NullReformulator(Reformulator):
    """Reformulateur par defaut : renvoie le texte local, sans reseau."""

    def reformulate(self, advice: AdviceObject, max_chars: int) -> str:
        return advice.text
