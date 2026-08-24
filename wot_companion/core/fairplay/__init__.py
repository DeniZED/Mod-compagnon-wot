"""Couche Fair Play : whitelist des donnees et filtre bloquant.

Traitee comme une exigence de securite produit (section 10), pas une simple
verification finale. Tout evenement et toute regle passent par ici.
"""
from .whitelist import (
    WHITELIST,
    FairPlayClass,
    is_field_allowed,
    is_event_allowed,
    allowed_fields,
)
from .filter import FairPlayFilter, FairPlayReport, FairPlayViolation

__all__ = [
    "WHITELIST",
    "FairPlayClass",
    "is_field_allowed",
    "is_event_allowed",
    "allowed_fields",
    "FairPlayFilter",
    "FairPlayReport",
    "FairPlayViolation",
]
