"""Overlay graphique in-game (mascotte cartoon + bulle) en Tkinter.

Fenetre sans bordure, toujours au-dessus, transparente et click-through sous
Windows (via SetLayeredWindowAttributes + WS_EX_TRANSPARENT, plus fiable que les
attributs Tk). Une carte HUD est TOUJOURS dessinee : meme si la transparence
echoue, quelque chose reste visible. Position reglable (ancrage + decalage) pour
eviter la minimap. Implemente `OverlaySink`.

La mascotte utilise les 12 visuels (condition x expression) : la CONDITION suit
les HP du joueur (neuf/abime), l'EXPRESSION suit le conseil.
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

_KEY = "#010203"                 # couleur-cle transparente
_KEY_COLORREF = 0x00030201       # 0x00BBGGRR pour #010203
_CARD = "#161d13"                # fond de la carte HUD (visible)
_CARD_EDGE = "#33421f"


class TkOverlay(OverlaySink):
    needs_main_thread = True

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._queue: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self._root = None
        self._canvas = None
        self._images: dict[tuple[str, str], Any] = {}
        self._hide_after_id = None
        self._last_condition = "neuf"
        self._closing = False
        self._w = 400
        self._h = 340

    # ---- API OverlaySink (thread moteur) -----------------------------------
    def show(self, displayed: DisplayedAdvice) -> None:
        adv = displayed.advice
        hp_pct = adv.context.get("hp_pct")
        self._queue.put({
            "text": displayed.text, "severity": adv.severity,
            "category": adv.category, "action": adv.action,
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
        root.title("WoT Companion")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=_KEY)

        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        x, y = self._anchor_xy(sw, sh)
        root.geometry("%dx%d+%d+%d" % (self._w, self._h, x, y))

        self._canvas = tk.Canvas(root, width=self._w, height=self._h, bg=_KEY,
                                 highlightthickness=0, bd=0)
        self._canvas.pack(fill="both", expand=True)

        n_imgs = self._load_images(tk)
        root.update_idletasks()  # la fenetre doit exister avant les styles Win32
        win32 = self._apply_win32()
        self._draw_idle(startup=True)

        print("[Overlay] fenetre %dx%d @ (%d,%d) | ancrage=%s | images=%d | %s"
              % (self._w, self._h, x, y, self.settings.ui.anchor, n_imgs, win32))
        print("[Overlay] Deplacer : --overlay-anchor {top_right,top_left,"
              "bottom_left,bottom_right} et --overlay-x / --overlay-y (px).")

        root.after(50, self._poll_queue)
        try:
            root.mainloop()
        except KeyboardInterrupt:
            pass

    def _anchor_xy(self, sw, sh):
        m = 16
        a = self.settings.ui.anchor
        ox, oy = self.settings.ui.offset_x, self.settings.ui.offset_y
        if a == "bottom_left":
            x, y = m, sh - self._h - m
        elif a == "bottom_right":
            x, y = sw - self._w - m, sh - self._h - m
        elif a == "top_left":
            x, y = m, m
        else:  # top_right (defaut : evite la minimap bas-droite)
            x, y = sw - self._w - m, m
        return x + ox, y + oy

    def _load_images(self, tk) -> int:
        subsample = self.settings.ui.text_scale <= 0.9
        for path in all_asset_paths():
            stem = path.stem[len("tank_"):]
            cond, _, expr = stem.partition("_")
            try:
                img = tk.PhotoImage(file=str(path))
                if subsample:
                    img = img.subsample(2, 2)
                self._images[(cond, expr)] = img
            except Exception:
                logger.warning("Image mascotte introuvable: %s", path.name)
        return len(self._images)

    def _apply_win32(self) -> str:
        """Transparence (couleur-cle) + click-through via l'API Win32. Retourne un
        court diagnostic. Sur non-Windows : carte HUD opaque, sans click-through."""
        try:
            import ctypes
            from ctypes import wintypes
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_TOOLWINDOW = 0x00000080
            LWA_COLORKEY = 0x00000001
            GA_ROOT = 2
            u = ctypes.windll.user32
            u.GetWindowLongW.restype = ctypes.c_long
            hwnd = u.GetAncestor(self._root.winfo_id(), GA_ROOT) or self._root.winfo_id()
            hwnd = wintypes.HWND(hwnd)

            exstyle = WS_EX_LAYERED | WS_EX_TOOLWINDOW
            if self.settings.ui.click_through:
                exstyle |= WS_EX_TRANSPARENT
            cur = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
            u.SetWindowLongW(hwnd, GWL_EXSTYLE, cur | exstyle)
            # Definit la couleur-cle transparente ET force le repaint (sinon une
            # fenetre layered sans attributs reste invisible).
            u.SetLayeredWindowAttributes(hwnd, _KEY_COLORREF, 255, LWA_COLORKEY)
            SWP = 0x0001 | 0x0002 | 0x0004 | 0x0020  # NOMOVE|NOSIZE|NOZORDER|FRAMECHANGED
            u.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP)
            ct = "click-through=ON" if self.settings.ui.click_through else "click-through=OFF"
            return "win32=OK transparence=ON " + ct
        except Exception as exc:
            return "win32=INDISPONIBLE (%s) - carte opaque, sans click-through" % exc

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
        accent = accent_color(msg["severity"])
        self._canvas.delete("all")
        self._draw_card(accent)
        self._draw_mascot(self._last_condition, expr)
        self._draw_bubble(msg["text"], accent)
        if self._hide_after_id is not None:
            try:
                self._root.after_cancel(self._hide_after_id)
            except Exception:
                pass
        self._hide_after_id = self._root.after(int(msg["ttl"] * 1000), self._draw_idle)

    def _draw_idle(self, startup: bool = False) -> None:
        if self._canvas is None:
            return
        self._canvas.delete("all")
        self._draw_card(_CARD_EDGE)
        if self.settings.ui.character_visible:
            self._draw_mascot(self._last_condition, "idle")
        label = "WoT Companion — prêt" if startup else "WoT Companion"
        self._canvas.create_text(24, 24, anchor="nw", text=label, fill="#b9c9ac",
                                 font=("Segoe UI", 11, "bold"))

    def _draw_card(self, accent: str) -> None:
        self._round_rect(6, 6, self._w - 6, self._h - 6, r=22,
                         fill=_CARD, outline=accent, width=3)

    def _draw_mascot(self, condition: str, expression: str) -> None:
        if not self.settings.ui.character_visible:
            return
        key = resolve(condition, expression)
        img = self._images.get(key) or self._images.get((condition, "idle")) \
            or self._images.get(("neuf", "idle"))
        if img is not None:
            self._canvas.create_image(self._w - 16, self._h - 12, image=img, anchor="se")

    def _draw_bubble(self, text: str, accent: str) -> None:
        pad = 15
        bx0, by0, bx1, by1 = 16, 16, self._w - 16, 132
        self._round_rect(bx0, by0, bx1, by1, r=18, fill="#fbf7ea", outline=accent, width=3)
        font_size = max(11, int(14 * self.settings.ui.text_scale))
        self._canvas.create_text(bx0 + pad, by0 + pad, anchor="nw", text=text,
                                 fill="#20242b", font=("Segoe UI", font_size, "bold"),
                                 width=(bx1 - bx0 - 2 * pad))

    def _round_rect(self, x0, y0, x1, y1, r=18, **kw):
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
               x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return self._canvas.create_polygon(pts, smooth=True, **kw)


def is_available() -> bool:
    try:
        import tkinter  # noqa: F401
        return True
    except Exception:
        return False
