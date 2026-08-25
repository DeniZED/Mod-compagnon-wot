"""Overlay graphique in-game (mascotte cartoon + bulle) en Tkinter.

Fenetre transparente, sans bordure, toujours au-dessus, click-through, ancree en
bas a droite (section 4.1). Implemente `OverlaySink` : se branche a la place de
la console sans rien changer au moteur.

La mascotte utilise les 12 visuels (condition x expression) : la CONDITION suit
les HP du joueur (neuf/abime), l'EXPRESSION suit le conseil.

Tkinter fait partie de la bibliotheque standard Python (present avec l'installeur
python.org sous Windows). La transparence par couleur-cle et le click-through
(styles Win32) sont propres a Windows ; ailleurs l'overlay s'affiche sans eux.
"""
from __future__ import annotations

import logging
import queue
from typing import Any

from ..settings import Settings
from .mascot import (
    accent_color, all_asset_paths, condition_for_hp, expression_for, resolve,
)
from .overlay import DisplayedAdvice, OverlaySink

logger = logging.getLogger("wot_companion.overlay.tk")

_TRANSPARENT_KEY = "#010203"  # couleur-cle rendue transparente (Windows)


class TkOverlay(OverlaySink):
    """Sink graphique. Le moteur appelle `show()` depuis son thread ; l'affichage
    est marshalle vers le thread Tk via une file (Tk n'est pas thread-safe)."""

    needs_main_thread = True

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._queue: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self._root = None
        self._canvas = None
        self._images: dict[tuple[str, str], Any] = {}
        self._hide_after_id = None
        self._history: list[DisplayedAdvice] = []
        self._last_condition = "neuf"
        self._closing = False

    # ---- API OverlaySink (appelable depuis le thread moteur) ---------------
    def show(self, displayed: DisplayedAdvice) -> None:
        self._history.append(displayed)
        adv = displayed.advice
        hp_pct = adv.context.get("hp_pct")
        self._queue.put({
            "text": displayed.text,
            "severity": adv.severity,
            "category": adv.category,
            "action": adv.action,
            "hp_ratio": (hp_pct / 100.0) if isinstance(hp_pct, (int, float)) else None,
            "ttl": max(3.0, float(adv.ttl_seconds)),
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
        import tkinter as tk

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
        w, h = 520, 470
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
        m = 12
        a = self.settings.ui.anchor
        if a == "bottom_left":
            return m, sh - h - m
        if a == "top_right":
            return sw - w - m, m
        if a == "top_left":
            return m, m
        return sw - w - m, sh - h - m

    def _load_images(self, tk) -> None:
        subsample = self.settings.ui.text_scale <= 0.9
        for path in all_asset_paths():
            # nom: tank_<condition>_<expression>.png
            stem = path.stem[len("tank_"):]
            cond, _, expr = stem.partition("_")
            try:
                img = tk.PhotoImage(file=str(path))
                if subsample:
                    img = img.subsample(2, 2)
                self._images[(cond, expr)] = img
            except Exception:
                logger.warning("Image mascotte introuvable: %s", path.name)

    def _make_click_through(self) -> None:
        try:
            import ctypes
            from ctypes import wintypes
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_TOOLWINDOW = 0x00000080
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
        if msg.get("hp_ratio") is not None:
            self._last_condition = condition_for_hp(msg["hp_ratio"])
        expr = expression_for(msg["category"], msg["severity"], msg["action"])
        self._canvas.delete("all")
        self._draw_mascot(self._last_condition, expr)
        self._draw_bubble(msg["text"], accent_color(msg["severity"]))
        if self._hide_after_id is not None:
            try:
                self._root.after_cancel(self._hide_after_id)
            except Exception:
                pass
        self._hide_after_id = self._root.after(int(msg["ttl"] * 1000), self._draw_idle)

    def _draw_idle(self) -> None:
        if self._canvas is None:
            return
        self._canvas.delete("all")
        if self.settings.ui.character_visible:
            self._draw_mascot(self._last_condition, "idle")

    def _draw_mascot(self, condition: str, expression: str) -> None:
        if not self.settings.ui.character_visible:
            return
        key = resolve(condition, expression)
        img = self._images.get(key) or self._images.get((condition, "idle")) \
            or self._images.get(("neuf", "idle"))
        if img is None:
            return
        w = int(self._canvas["width"])
        h = int(self._canvas["height"])
        self._canvas.create_image(w - 10, h - 10, image=img, anchor="se")

    def _draw_bubble(self, text: str, accent: str) -> None:
        w = int(self._canvas["width"])
        pad = 16
        bx0, by0, bx1, by1 = 12, 12, w - 12, 150
        self._round_rect(bx0, by0, bx1, by1, r=22, fill="#fbf7ea", outline=accent, width=4)
        self._canvas.create_polygon(bx1 - 90, by1 - 2, bx1 - 40, by1 - 2,
                                    bx1 - 55, by1 + 26, fill="#fbf7ea", outline="", width=0)
        font_size = max(11, int(15 * self.settings.ui.text_scale))
        self._canvas.create_text(
            bx0 + pad, by0 + pad, anchor="nw", text=text, fill="#20242b",
            font=("Segoe UI", font_size, "bold"), width=(bx1 - bx0 - 2 * pad))

    def _round_rect(self, x0, y0, x1, y1, r=20, **kw):
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
               x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return self._canvas.create_polygon(pts, smooth=True, **kw)


def is_available() -> bool:
    try:
        import tkinter  # noqa: F401
        return True
    except Exception:
        return False
