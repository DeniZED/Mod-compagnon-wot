"""Overlay graphique in-game (mascotte cartoon + bulle) en Tkinter.

Fenetre transparente, sans bordure, toujours au-dessus, click-through, ancree en
bas a droite (section 4.1). Implemente `OverlaySink` : se branche a la place de
la console sans rien changer au moteur.

Tkinter fait partie de la bibliotheque standard Python (present avec l'installeur
python.org sous Windows). Aucune autre dependance. La transparence par couleur-cle
(`-transparentcolor`) et le click-through (styles Win32) sont propres a Windows ;
sur un autre OS l'overlay s'affiche sans ces raffinements.
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Any

from ..settings import Settings
from .mascot import accent_color, asset_path, state_for_severity
from .overlay import DisplayedAdvice, OverlaySink

logger = logging.getLogger("wot_companion.overlay.tk")

# Couleur-cle de transparence (improbable dans l'image) : ce ton devient invisible.
_TRANSPARENT_KEY = "#010203"
_STATE_SEVERITY = {"normal": "INFO", "attention": "ATTENTION",
                   "critical": "CRITICAL", "positive": "POSITIVE"}


class TkOverlay(OverlaySink):
    """Sink graphique. Le moteur appelle `show()` depuis son thread ; l'affichage
    est marshalle vers le thread Tk via une file (Tk n'est pas thread-safe)."""

    #: le moteur doit tourner dans un thread separe ; la boucle Tk prend le thread principal.
    needs_main_thread = True

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._queue: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self._root = None
        self._canvas = None
        self._images: dict[str, Any] = {}
        self._hide_after_id = None
        self._history: list[DisplayedAdvice] = []
        self._closing = False

    # ---- API OverlaySink (appelable depuis le thread moteur) ---------------
    def show(self, displayed: DisplayedAdvice) -> None:
        self._history.append(displayed)
        self._queue.put({
            "text": displayed.text,
            "color": displayed.color,
            "severity": displayed.advice.severity,
            "ttl": max(3.0, float(displayed.advice.ttl_seconds)),
        })

    def clear(self) -> None:
        self._queue.put({"clear": True})

    def stop(self) -> None:
        self._closing = True
        if self._root is not None:
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass

    # ---- Boucle Tk (thread principal) --------------------------------------
    def run_mainloop(self) -> None:
        import tkinter as tk  # peut lever si Tk indisponible : message clair en amont

        root = tk.Tk()
        self._root = root
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.attributes("-transparentcolor", _TRANSPARENT_KEY)
        except tk.TclError:
            logger.warning("Transparence par couleur-cle indisponible (non Windows ?).")
        root.configure(bg=_TRANSPARENT_KEY)

        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        w, h = 520, 460
        x, y = self._anchor_xy(sw, sh, w, h)
        root.geometry("%dx%d+%d+%d" % (w, h, x, y))

        self._canvas = tk.Canvas(root, width=w, height=h, bg=_TRANSPARENT_KEY,
                                 highlightthickness=0, bd=0)
        self._canvas.pack(fill="both", expand=True)

        self._load_images(tk)
        self._make_click_through()
        self._draw_idle()

        root.after(50, self._poll_queue)
        try:
            root.mainloop()
        except KeyboardInterrupt:
            pass

    def _anchor_xy(self, sw, sh, w, h):
        margin = 12
        anchor = self.settings.ui.anchor
        if anchor == "bottom_left":
            return margin, sh - h - margin
        if anchor == "top_right":
            return sw - w - margin, margin
        if anchor == "top_left":
            return margin, margin
        return sw - w - margin, sh - h - margin  # bottom_right par defaut

    def _load_images(self, tk) -> None:
        scale = self.settings.ui.text_scale
        for state in ("idle", "attention", "critical", "positive"):
            try:
                img = tk.PhotoImage(file=str(asset_path(state)))
                # Tk ne redimensionne qu'en entier ; on reduit un peu par defaut.
                if scale <= 0.9:
                    img = img.subsample(2, 2)
                self._images[state] = img
            except Exception:
                logger.warning("Image mascotte '%s' introuvable/illisible.", state)

    def _make_click_through(self) -> None:
        """Rend la fenetre transparente aux clics (Windows). Best effort."""
        try:
            import ctypes
            from ctypes import wintypes
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_TOOLWINDOW = 0x00000080  # masque de la barre des taches
            user32 = ctypes.windll.user32
            hwnd = user32.GetParent(self._root.winfo_id()) or self._root.winfo_id()
            user32.GetWindowLongW.restype = ctypes.c_long
            style = user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE)
            user32.SetWindowLongW(
                wintypes.HWND(hwnd), GWL_EXSTYLE,
                style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW)
        except Exception:
            logger.info("Click-through indisponible (non Windows ?).")

    # ---- Traitement des messages -------------------------------------------
    def _poll_queue(self) -> None:
        if self._closing:
            return
        try:
            while True:
                msg = self._queue.get_nowait()
                if msg.get("clear"):
                    self._draw_idle()
                else:
                    self._render_advice(msg)
        except queue.Empty:
            pass
        if self._root is not None:
            self._root.after(50, self._poll_queue)

    def _render_advice(self, msg: dict) -> None:
        state = state_for_severity(msg["severity"])
        self._canvas.delete("all")
        self._draw_mascot(state)
        if self.settings.ui.character_visible or True:
            self._draw_bubble(msg["text"], accent_color(state))
        if self._hide_after_id is not None:
            try:
                self._root.after_cancel(self._hide_after_id)
            except Exception:
                pass
        self._hide_after_id = self._root.after(
            int(msg["ttl"] * 1000), self._draw_idle)

    def _draw_idle(self) -> None:
        if self._canvas is None:
            return
        self._canvas.delete("all")
        if self.settings.ui.character_visible:
            self._draw_mascot("idle")

    def _draw_mascot(self, state: str) -> None:
        if not self.settings.ui.character_visible:
            return
        img = self._images.get(state) or self._images.get("idle")
        if img is None:
            return
        w = int(self._canvas["width"])
        h = int(self._canvas["height"])
        self._canvas.create_image(w - 10, h - 10, image=img, anchor="se")

    def _draw_bubble(self, text: str, accent: str) -> None:
        w = int(self._canvas["width"])
        pad = 16
        bx0, by0 = 12, 12
        bx1, by1 = w - 12, 150
        self._round_rect(bx0, by0, bx1, by1, r=22, fill="#fbf7ea", outline=accent, width=4)
        # Petite pointe de bulle vers la mascotte (bas droite).
        self._canvas.create_polygon(bx1 - 90, by1 - 2, bx1 - 40, by1 - 2,
                                    bx1 - 55, by1 + 26, fill="#fbf7ea",
                                    outline=accent, width=0)
        font_size = max(11, int(15 * self.settings.ui.text_scale))
        self._canvas.create_text(
            bx0 + pad, by0 + pad, anchor="nw", text=text, fill="#20242b",
            font=("Segoe UI", font_size, "bold"),
            width=(bx1 - bx0 - 2 * pad))

    def _round_rect(self, x0, y0, x1, y1, r=20, **kw):
        pts = [
            x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
            x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
        ]
        return self._canvas.create_polygon(pts, smooth=True, **kw)


def is_available() -> bool:
    try:
        import tkinter  # noqa: F401
        return True
    except Exception:
        return False
