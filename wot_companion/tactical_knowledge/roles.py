"""Rôles de jeu par char (tag -> rôle), capturés depuis le roster du jeu.

Le rôle affine la classe : un LOURD d'ASSAUT (front, brawl) et un LOURD de
SOUTIEN (2e ligne) ne vont pas au même endroit. WoT expose le rôle de chaque
char via ses tags `role_*` (visible du joueur = Fair Play). Le mod capture ces
rôles dans `vehicle_roles.json` (ou la section "roles" de `vehicle_classes.json`),
qui grossit à chaque partie et alimente le rebuild `--vehicle-roles`.

Rôles canoniques (mêmes valeurs que le mod, `_ROLE_TAG_MAP`) :
    assault_heavy, support_heavy, brawler_medium, sniper_medium, scout,
    td_assault, td_sniper

Ce module n'a AUCUNE dépendance moteur : simple table tag->rôle, testable.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

ROLE_FORMAT_VERSION = 1

# Rôles reconnus : au-delà, on ignore (donnée douteuse -> rôle-agnostique).
VALID_ROLES = frozenset({
    "assault_heavy", "support_heavy", "brawler_medium", "sniper_medium",
    "scout", "td_assault", "td_sniper",
})


def _roles_from_doc(doc: object) -> Dict[str, str]:
    """Extrait la table tag->rôle d'un document JSON déjà chargé.

    Accepte {"roles": {...}}, la section "roles" d'un vehicle_classes.json, ou
    directement {tag: role}."""
    if not isinstance(doc, dict):
        return {}
    raw = doc.get("roles", doc)
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()
            if isinstance(v, str) and v in VALID_ROLES}


def load_role_table(path: str | Path) -> Dict[str, str]:
    """Charge une table tag->rôle depuis un JSON (rôles invalides ignorés).
    Fichier absent/illisible -> table vide (comportement rôle-agnostique)."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return _roles_from_doc(json.loads(p.read_text(encoding="utf-8")))
    except (ValueError, OSError):
        return {}


def role_of(tag: Optional[str], table: Dict[str, str]) -> Optional[str]:
    """Rôle d'un char (ou None si inconnu / table vide)."""
    if not tag or not table:
        return None
    r = table.get(tag)
    return r if r in VALID_ROLES else None


def merge_vehicle_roles(path: str | Path, new_map: Dict[str, str]) -> int:
    """Fusionne des rôles (tag->rôle) dans le fichier ; n'ajoute que les
    nouveaux valides. Retourne le nombre ajouté (idempotent)."""
    p = Path(path)
    doc = {"format": ROLE_FORMAT_VERSION, "roles": {}}
    if p.exists():
        try:
            loaded = json.loads(p.read_text(encoding="utf-8"))
            doc["roles"] = dict(_roles_from_doc(loaded))
        except (ValueError, OSError):
            pass
    added = 0
    for tag, role in new_map.items():
        if role in VALID_ROLES and tag not in doc["roles"]:
            doc["roles"][tag] = role
            added += 1
    if added:
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    return added
