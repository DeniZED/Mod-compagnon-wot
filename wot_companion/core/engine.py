"""AdviceEngine : orchestration du pipeline de decision (section 7.1).

Game Adapter -> RawEvent -> FairPlayFilter -> BattleContext -> Feature Builder
-> Rules + KB -> CandidateAdvice[] -> Scorer -> Arbiter -> Text Renderer -> Overlay.

Le moteur est deterministe : memes evenements + memes versions = meme sortie.
"""
from __future__ import annotations

import logging

from ..knowledge.loader import KnowledgeBase
from ..settings import Settings
from .advice import AdviceObject
from .context.battle_context import BattleContext
from .context.features import FeatureBuilder
from .events import EventType, RawEvent
from .fairplay.filter import FairPlayFilter
from .journal import AdviceJournal, AdviceLogEntry
from .rules.base import Rule, RuleContext
from .rules.registry import default_rules
from .scoring.arbiter import AdviceArbiter
from .scoring.scorer import Scorer

logger = logging.getLogger("wot_companion.engine")


class AdviceEngine:
    def __init__(
        self,
        settings: Settings | None = None,
        knowledge: KnowledgeBase | None = None,
        rules: list[Rule] | None = None,
        renderer=None,
        overlay=None,
        journal: AdviceJournal | None = None,
        fairplay: FairPlayFilter | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.knowledge = knowledge or KnowledgeBase()
        self.fairplay = fairplay or FairPlayFilter(audit=True)
        self.scorer = Scorer(self.settings.scoring)
        self.arbiter = AdviceArbiter(self.settings, self.scorer)
        self.journal = journal or AdviceJournal()

        # Rendu/overlay optionnels : le coeur fonctionne sans UI.
        if renderer is None:
            from ..ui.renderer import TextRenderer
            renderer = TextRenderer(self.settings)
        self.renderer = renderer
        self.overlay = overlay

        self.rules = self._load_rules(rules or default_rules())

        self.context: BattleContext | None = None
        self.last_features = None
        self.features_builder = FeatureBuilder()
        self._fired_once: set[str] = set()
        self.player_profile: dict | None = None

    # ---- Chargement des regles avec controle Fair Play ---------------------
    def _load_rules(self, rules: list[Rule]) -> list[Rule]:
        """Refuse toute regle dependant d'un champ non whiteliste (section 10.1)."""
        valid: list[Rule] = []
        for rule in rules:
            violations = self.fairplay.validate_rule(rule.id, rule.dependencies)
            if violations:
                for v in violations:
                    logger.error("Regle rejetee: %s", v.detail)
                continue
            valid.append(rule)
        return valid

    # ---- Cycle de vie de la bataille ---------------------------------------
    def start_battle(self, battle_id: str, start_ms: int) -> BattleContext:
        self.context = BattleContext(battle_id=battle_id, start_ms=start_ms)
        self.features_builder = FeatureBuilder()
        self.arbiter.reset()
        self._fired_once.clear()
        return self.context

    def on_event(self, event: RawEvent) -> bool:
        """Filtre puis applique un evenement au contexte. Retourne True si accepte."""
        filtered = self.fairplay.filter_event(event)
        if not filtered.allowed:
            return False
        evt = filtered.event
        assert evt is not None

        # Demarrage/fermeture automatiques du contexte (BAT-001), independants de l'UI.
        if evt.event_type == EventType.BATTLE_START.value:
            bid = evt.payload.get("battle_id") or evt.battle_id or "battle"
            self.start_battle(bid, evt.timestamp_ms)
            return True

        if self.context is None:
            # Aucun contexte actif : on ignore proprement (pas d'invention).
            return False

        self.context.apply(evt)

        # Resolution du rôle metier a la reception du vehicule (BAT-002).
        # Si l'adaptateur a deja fourni le rôle (tags du char), on le garde ;
        # sinon on tente la resolution via la base de connaissances locale.
        if evt.event_type == EventType.PLAYER_VEHICLE.value and not self.context.vehicle_role:
            self.context.vehicle_role = self.knowledge.resolve_role(self.context.vehicle_id)

        return True

    def evaluate(self) -> AdviceObject | None:
        """Evalue les regles et retourne au plus un conseil (BAT-006)."""
        if self.context is None or self.context.finished:
            return None

        # Etat de jeu continu vers l'overlay (mascotte reactive aux HP), meme
        # quand aucun conseil n'est affiche.
        if self.overlay is not None:
            try:
                self.overlay.notify_state(hp_ratio=self.context.hp_ratio)
            except Exception:
                logger.exception("notify_state overlay a echoue")

        features = self.features_builder.build(self.context)
        self.last_features = features   # expose pour la trace tactique (V2)
        self.arbiter.set_clock(self.context.elapsed_s)

        rc = RuleContext(
            battle=self.context, features=features, knowledge=self.knowledge,
            session_objective=self.settings.session_objective,
            player_profile=self.player_profile,
        )

        candidates = []
        for rule in self.rules:
            if rule.once_per_battle and rule.id in self._fired_once:
                continue
            try:
                candidates.extend(rule.evaluate(rc))
            except Exception:  # une regle defaillante ne casse jamais le moteur
                logger.exception("Regle %s a leve une exception", rule.id)

        advice = self.arbiter.select(
            candidates, features=features, player_profile=self.player_profile
        )

        entry = AdviceLogEntry(
            elapsed_s=self.context.elapsed_s,
            battle_id=self.context.battle_id,
            decision="SILENCE",
            context=self.context.snapshot(),
            candidates=[{
                "rule_id": c.rule_id, "category": c.category.value,
                "action": c.action, "urgency": round(c.urgency, 2),
                "impact": round(c.impact, 2), "confidence": round(c.confidence, 2),
            } for c in candidates],
        )

        if advice is not None:
            # HP courant dans le contexte du conseil : l'overlay choisit la
            # condition de la mascotte (neuf/abime) a partir de la.
            if self.context.hp_ratio is not None:
                advice.context.setdefault("hp_pct", round(self.context.hp_ratio * 100))
            advice.text = self.renderer.render(advice)
            entry.decision = "SHOWN"
            entry.advice = advice.as_dict()
            if self._is_once_rule(advice.rule_id):
                self._fired_once.add(advice.rule_id)
            if self.overlay is not None:
                from ..ui.overlay import DisplayedAdvice, color_for
                self.overlay.show(DisplayedAdvice(advice, advice.text, color_for(advice)))

        if candidates or advice is not None:
            self.journal.record(entry)
        return advice

    def feed(self, event: RawEvent) -> AdviceObject | None:
        """Raccourci : applique un evenement puis evalue."""
        accepted = self.on_event(event)
        if not accepted:
            return None
        return self.evaluate()

    def end_battle(self) -> BattleContext | None:
        if self.context is not None:
            self.context.finished = True
        return self.context

    def _is_once_rule(self, rule_id: str) -> bool:
        return any(r.id == rule_id and r.once_per_battle for r in self.rules)
