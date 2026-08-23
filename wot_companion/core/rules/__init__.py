"""Regles tactiques autorisees et registre par defaut."""
from .base import Rule, RuleContext
from .registry import default_rules

__all__ = ["Rule", "RuleContext", "default_rules"]
