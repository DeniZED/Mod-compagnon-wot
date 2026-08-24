"""LiveRunner : fait tourner le compagnon en conditions reelles.

Ecoute le pont IPC (mod WoT ou injecteur), fait tourner le moteur deterministe,
affiche les conseils en direct (console) et enregistre l'historique persistant.

Robustesse (REC-04/05/07) : une source qui se deconnecte ou plante n'arrete pas
le compagnon ; le moteur continue et attend la prochaine connexion.
"""
from __future__ import annotations

import logging
from pathlib import Path

from ..app import CompanionApp
from ..game_adapter.base import EventEnvelope
from ..game_adapter.ipc import DEFAULT_HOST, DEFAULT_PORT, SocketEventServerAdapter
from ..profile.store import HistoryStore
from ..settings import Settings
from ..ui.overlay import ConsoleOverlay

logger = logging.getLogger("wot_companion.live")


class LiveRunner:
    def __init__(
        self,
        settings: Settings | None = None,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        db_path: str | Path = "wot_companion.sqlite",
        use_color: bool = True,
    ) -> None:
        self.settings = settings or Settings()
        self.host = host
        self.port = port
        self.overlay = ConsoleOverlay(use_color=use_color)
        self.store = HistoryStore(db_path)
        self.app = CompanionApp(settings=self.settings, store=self.store, overlay=self.overlay)
        self.adapter = SocketEventServerAdapter(
            host=host, port=port, control_handler=self._on_control
        )

    # ---- Messages de controle (non-jeu) -----------------------------------
    def _on_control(self, env: EventEnvelope) -> None:
        etype = env.event_type
        if etype == "CTRL_SILENCE_TOGGLE":
            silenced = self.app.toggle_silence()
            self._banner("SILENCE ON" if silenced else "SILENCE OFF")
        elif etype == "CTRL_PING":
            logger.info("Ping recu de la source (%s)", env.payload)
        else:
            logger.info("Message de controle non gere: %s", etype)

    def _banner(self, msg: str) -> None:
        print(f"\n=== {msg} ===\n")

    # ---- Boucle principale -------------------------------------------------
    def run(self) -> None:
        self.adapter.start()
        print(f"WoT Companion LIVE - en ecoute sur {self.host}:{self.port}")
        print(f"Historique : {self.store.db_path}")
        print("En attente de la source d'evenements (mod WoT ou injecteur)...")
        print("Ctrl+C pour arreter.\n")
        try:
            self.app.run(self.adapter)  # bloque : consomme le flux socket
        except KeyboardInterrupt:
            print("\nArret demande.")
        finally:
            self.adapter.stop()
            self.store.close()

    def stop(self) -> None:
        self.adapter.stop()
