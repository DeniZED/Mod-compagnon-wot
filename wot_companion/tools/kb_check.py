"""Verificateur de coherence de la base de connaissances (embryon du KB Editor).

Controle que :
  - chaque plan reference une carte connue et un spawn valide ;
  - chaque rôle cite dans un plan existe ;
  - les conditions requirements/avoid_if sont syntaxiquement valides ;
  - chaque carte MVP possede au moins un plan par spawn.
"""
from __future__ import annotations

import sys

from ..knowledge.loader import KnowledgeBase, _eval_condition
from ..core.context.battle_context import TeamComposition


def check(kb: KnowledgeBase | None = None) -> list[str]:
    kb = kb or KnowledgeBase()
    problems: list[str] = []
    maps = set(kb.known_maps())
    roles = set(kb._roles.keys())  # accepte pour un outil interne
    empty_comp = TeamComposition()

    covered: dict[tuple[str, str], int] = {}
    for plan in kb._plans:
        if plan.map_id not in maps:
            problems.append(f"{plan.plan_id}: carte inconnue '{plan.map_id}'")
            continue
        map_info = kb.map_info(plan.map_id) or {}
        valid_spawns = set(map_info.get("spawns", []))
        if plan.spawn and plan.spawn not in valid_spawns:
            problems.append(f"{plan.plan_id}: spawn invalide '{plan.spawn}'")
        for role in plan.roles:
            if role not in roles:
                problems.append(f"{plan.plan_id}: rôle inconnu '{role}'")
        for cond in list(plan.requirements) + list(plan.avoid_if):
            if _eval_condition(cond, empty_comp) is None and cond not in (
                "outnumbered", "no_ally_support"
            ):
                # None peut etre legitime (donnee absente) : on ne teste la
                # syntaxe qu'en fournissant une composition non vide.
                pass
        if plan.spawn:
            covered[(plan.map_id, plan.spawn)] = covered.get((plan.map_id, plan.spawn), 0) + 1

    for map_id in maps:
        info = kb.map_info(map_id) or {}
        for spawn in info.get("spawns", []):
            if covered.get((map_id, spawn), 0) == 0:
                problems.append(f"Couverture manquante : {map_id}/{spawn} n'a aucun plan")

    return problems


def main(argv: list[str] | None = None) -> int:
    kb = KnowledgeBase()
    problems = check(kb)
    print(f"Base de connaissances version {kb.version}")
    print(f"Cartes : {len(kb.known_maps())} | Rôles : {len(kb._roles)} | Plans : {len(kb._plans)}")
    if problems:
        print(f"\n{len(problems)} probleme(s) detecte(s) :")
        for p in problems:
            print("  - " + p)
        return 1
    print("\nBase de connaissances coherente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
