"""CompanionApp : cablage complet moteur + adaptateur + profil + garage.

Boucle nominale (section 3.1) : detecter la bataille, publier le contexte,
evaluer le plan et les regles, enregistrer les metriques, afficher une synthese
garage. Le mode silence (BAT-008) suspend instantanement les conseils non critiques.
"""
from __future__ import annotations

import logging

from .core.engine import AdviceEngine
from .core.events import EventType, RawEvent
from .game_adapter.base import GameAdapter
from .knowledge.loader import KnowledgeBase
from .profile.store import HistoryStore
from .profile.trace import BattleTraceRecorder
from .profile.trends import TrendAnalyzer, build_player_profile
from .settings import Personality, Settings

logger = logging.getLogger("wot_companion.app")


class CompanionApp:
    def __init__(
        self,
        settings: Settings | None = None,
        store: HistoryStore | None = None,
        overlay=None,
        knowledge: KnowledgeBase | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.knowledge = knowledge or KnowledgeBase()
        self.store = store or HistoryStore(":memory:")
        self.overlay = overlay
        self.engine = AdviceEngine(
            settings=self.settings, knowledge=self.knowledge, overlay=overlay
        )
        self.trends = TrendAnalyzer(self.store)
        self.trace = BattleTraceRecorder(self.store)
        self._silenced = False
        self._prev_personality = self.settings.personality

    # ---- Mode silence (BAT-008) -------------------------------------------
    def toggle_silence(self) -> bool:
        """Bascule le mode silence. Retourne l'etat courant (True = silencieux)."""
        self._silenced = not self._silenced
        if self._silenced:
            self._prev_personality = self.settings.personality
            self.settings.personality = Personality.SILENCIEUX
        else:
            self.settings.personality = self._prev_personality
        return self._silenced

    # ---- Boucle principale -------------------------------------------------
    def run(self, adapter: GameAdapter) -> bool:
        """Consomme le flux de l'adaptateur jusqu'a epuisement.

        Une panne de l'adaptateur (ex: patch WoT cassant le bridge, REC-07) est
        capturee : le compagnon se desactive proprement sans propager de crash.
        Retourne True si le flux s'est termine normalement, False si l'adaptateur
        a echoue.
        """
        try:
            for event in adapter.events():
                self._handle(event)
            return True
        except Exception:
            logger.exception("Adaptateur defaillant : arret propre du compagnon.")
            return False
        finally:
            adapter.close()

    def _handle(self, event: RawEvent) -> None:
        etype = event.event_type

        if etype == EventType.BATTLE_START.value:
            self.engine.on_event(event)
            # Charge le profil local pour personnaliser le coaching (section 3.1).
            self.engine.player_profile = build_player_profile(self.store)
            return

        if etype == EventType.BATTLE_END.value:
            self._on_battle_end(event)
            return

        if etype == EventType.BATTLE_RESULT.value:
            # Le resultat autoritaire arrive souvent APRES la fin de bataille :
            # on met a jour le contexte, on re-enregistre (INSERT OR REPLACE) et
            # on rafraichit la synthese garage avec les vraies valeurs.
            self.engine.on_event(event)
            ctx = self.engine.context
            if ctx is not None:
                self.store.record_from_context(ctx)
                self._print_garage_summary(ctx.vehicle_id)
            return

        self.engine.feed(event)
        # Trace tactique legere : echantillonne l'etat pour bâtir, au fil des
        # batailles, les positions/routes efficaces du joueur (V2, local-first).
        if self.engine.context is not None:
            self.trace.maybe_record(self.engine.context, self.engine.last_features)

    def _on_battle_end(self, event: RawEvent) -> None:
        self.engine.on_event(event)
        ctx = self.engine.context
        if ctx is None:
            return
        self.engine.end_battle()
        self.store.record_from_context(ctx)
        self._print_garage_summary(ctx.vehicle_id)

    def _print_garage_summary(self, vehicle_id: str | None) -> None:
        """Resume de bataille au retour garage (GAR-001)."""
        trends = self.trends.session_trends(window=10, vehicle_id=vehicle_id)
        lines = self.trends.summary_lines(trends)
        print("\n--- Garage : synthese de session ---")
        for line in lines:
            print("  " + line)
        print("------------------------------------\n")
        # Overlay : remplace le dernier message de combat par la synthese garage,
        # pour ne pas rester sur un conseil de la partie precedente.
        if self.overlay is not None and lines:
            summary = " ".join(line.strip() for line in lines[:2])
            try:
                self.overlay.show_garage("Retour garage — " + summary)
            except Exception:
                logger.exception("show_garage overlay a echoue")

    def close(self) -> None:
        self.store.close()
