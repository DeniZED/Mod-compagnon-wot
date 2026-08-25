"""LiveRunner : fait tourner le compagnon en conditions reelles.

Ecoute le pont IPC (mod WoT ou injecteur), fait tourner le moteur deterministe,
affiche les conseils (console OU overlay graphique) et enregistre l'historique.

Robustesse (REC-04/05/07) : une source qui se deconnecte ou plante n'arrete pas
le compagnon ; le moteur continue et attend la prochaine connexion.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from ..app import CompanionApp
from ..game_adapter.base import EventEnvelope
from ..game_adapter.ipc import DEFAULT_HOST, DEFAULT_PORT, SocketEventServerAdapter
from ..profile.store import HistoryStore
from ..settings import Settings
from ..ui.overlay import ConsoleOverlay, NullOverlay

logger = logging.getLogger("wot_companion.live")


def _build_overlay(kind: str, settings: Settings, use_color: bool):
    if kind == "none":
        return NullOverlay()
    if kind == "tk":
        from ..ui.tk_overlay import TkOverlay, is_available
        if not is_available():
            print("[Overlay] Tkinter indisponible : bascule sur la console.")
            return ConsoleOverlay(use_color=use_color)
        return TkOverlay(settings)
    return ConsoleOverlay(use_color=use_color)


class LiveRunner:
    def __init__(
        self,
        settings: Settings | None = None,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        db_path: str | Path = "wot_companion.sqlite",
        use_color: bool = True,
        overlay: str = "console",
        config_path: str | Path | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.host = host
        self.port = port
        self.config_path = config_path
        self.overlay = _build_overlay(overlay, self.settings, use_color)
        self._wire_overlay_persistence()
        self.store = HistoryStore(db_path)
        self.app = CompanionApp(settings=self.settings, store=self.store, overlay=self.overlay)
        self.adapter = SocketEventServerAdapter(
            host=host, port=port, control_handler=self._on_control
        )

    def _wire_overlay_persistence(self) -> None:
        """Permet a l'overlay de persister sa position (Ctrl + glisser) dans la config."""
        if self.config_path is None:
            return
        if not hasattr(self.overlay, "persist_position"):
            return

        def _persist(ox: int, oy: int) -> None:
            from ..config import save_settings
            self.settings.ui.offset_x = ox
            self.settings.ui.offset_y = oy
            try:
                save_settings(self.settings, self.config_path)
                print("[Overlay] Position memorisee (offset %+d, %+d)." % (ox, oy))
            except Exception:
                logger.exception("Sauvegarde de la position de l'overlay impossible")

        self.overlay.persist_position = _persist

    # ---- Messages de controle (non-jeu) -----------------------------------
    def _on_control(self, env: EventEnvelope) -> None:
        etype = env.event_type
        if etype == "CTRL_SILENCE_TOGGLE":
            silenced = self.app.toggle_silence()
            print(f"\n=== {'SILENCE ON' if silenced else 'SILENCE OFF'} ===\n")
        elif etype == "CTRL_PING":
            logger.info("Ping recu de la source (%s)", env.payload)

    # ---- Boucle principale -------------------------------------------------
    def run(self) -> None:
        self.adapter.start()
        print(f"WoT Companion LIVE - en ecoute sur {self.host}:{self.port}")
        print(f"Historique : {self.store.db_path}")
        print("En attente de la source d'evenements (mod WoT ou injecteur)...")
        print("Ctrl+C pour arreter.\n")

        if getattr(self.overlay, "needs_main_thread", False):
            self._run_with_gui_overlay()
        else:
            self._run_console()

    def _run_console(self) -> None:
        try:
            self.app.run(self.adapter)
        except KeyboardInterrupt:
            print("\nArret demande.")
        finally:
            self.adapter.stop()
            self.store.close()

    def _run_with_gui_overlay(self) -> None:
        """Overlay graphique : le moteur consomme le socket dans un thread, la
        boucle Tk tourne sur le thread principal (Tk l'exige)."""
        worker = threading.Thread(target=self.app.run, args=(self.adapter,), daemon=True)
        worker.start()
        try:
            self.overlay.run_mainloop()
        except KeyboardInterrupt:
            print("\nArret demande.")
        finally:
            try:
                self.overlay.stop()
            except Exception:
                pass
            self.adapter.stop()
            self.store.close()

    def stop(self) -> None:
        self.adapter.stop()
