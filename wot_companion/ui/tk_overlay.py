"""Overlay graphique in-game (mascotte cartoon + bulle) en Tkinter.

Fenetre sans bordure, toujours au-dessus, transparente et click-through sous
Windows (SetLayeredWindowAttributes + WS_EX_TRANSPARENT). Une carte HUD compacte
est toujours dessinee. La bulle se dimensionne au texte et se place A GAUCHE de la
mascotte (sans la masquer). Deplacement : maintenir Ctrl et glisser la carte.

La mascotte utilise les 12 visuels (condition x expression) : la CONDITION suit
les HP (neuf/abime), l'EXPRESSION suit le conseil.
"""
from __future__ import annotations

import logging
import queue
from typing import Any, Callable

from ..settings import Settings
from .mascot import (
    accent_color, all_asset_paths, condition_for_hp, expression_for, resolve,
)
from .overlay import DisplayedAdvice, OverlaySink

logger = logging.getLogger("wot_companion.overlay.tk")

_KEY = "#010203"
_KEY_COLORREF = 0x00030201
_CARD = "#161d13"
_MASCOT_W = 168          # zone reservee a la mascotte a droite (+ espace bulle)
_GARAGE_ACCENT = "#7a5cc0"  # bulle de retour garage (teinte distincte)


class TkOverlay(OverlaySink):
    needs_main_thread = True

    def __init__(self, settings: Settings, debug_opaque: bool = False) -> None:
        self.settings = settings
        #: mode diagnostic : fenetre OPAQUE (sans transparence ni click-through),
        #: pour verifier que la fenetre s'affiche bien par-dessus le jeu.
        self.debug_opaque = debug_opaque
        self._queue: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self._root = None
        self._canvas = None
        self._images: dict[tuple[str, str], Any] = {}
        self._last_condition = "neuf"
        self._current: dict | None = None
        self._closing = False
        self._move_mode = False
        self._drag = None
        self._move_origin = None      # position (x,y) a l'entree en mode deplacement
        self._base_x = 0
        self._base_y = 0
        self._w = 470
        self._h = 210
        #: radar tactique (2e fenetre, optionnelle)
        self._radar_win = None
        self._radar_canvas = None
        self._radar_state: dict | None = None
        self._radar_size = max(120, int(settings.ui.radar_size))
        self._radar_base = (0, 0)      # position d'ancrage (avant offset radar)
        self._radar_drag = None
        #: callback(offset_x, offset_y) pour persister la position apres deplacement.
        self.persist_position: Callable[[int, int], None] | None = None
        #: idem pour le radar (position propre).
        self.persist_radar: Callable[[int, int], None] | None = None

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

    def notify_state(self, hp_ratio: float | None = None) -> None:
        if hp_ratio is not None:
            self._queue.put({"state_hp_ratio": hp_ratio})

    def notify_radar(self, state: dict) -> None:
        """Instantané radar (position, zones, alliés/ennemis spottés)."""
        if self.settings.ui.radar_enabled:
            self._queue.put({"radar": state})

    def show_garage(self, text: str) -> None:
        self._queue.put({
            "text": text, "severity": "POSITIVE", "category": "GARAGE",
            "action": "", "hp_ratio": 1.0, "ttl": 0.0, "garage": True,
        })

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
        bg = _CARD if self.debug_opaque else _KEY
        root.configure(bg=bg)

        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        self._base_x, self._base_y = self._anchor_base(sw, sh)
        x = self._base_x + self.settings.ui.offset_x
        y = self._base_y + self.settings.ui.offset_y
        x, y = self._clamp_on_screen(x, y)
        root.geometry("%dx%d+%d+%d" % (self._w, self._h, x, y))

        self._canvas = tk.Canvas(root, width=self._w, height=self._h, bg=bg,
                                 highlightthickness=0, bd=0)
        self._canvas.pack(fill="both", expand=True)
        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)

        n = self._load_images(tk)
        root.update_idletasks()
        if self.debug_opaque:
            win32 = "MODE OPAQUE (diagnostic : transparence + click-through desactives)"
        else:
            win32 = self._set_click_through(self.settings.ui.click_through)
        self._draw_idle(startup=True)

        if self.settings.ui.radar_enabled:
            self._build_radar_window(tk, root, x, y, sw, sh)

        print("[Overlay] fenetre %dx%d @ (%d,%d) | ancrage=%s | images=%d | %s"
              % (self._w, self._h, x, y, self.settings.ui.anchor, n, win32))
        print("[Overlay] Deplacer : maintiens Ctrl et glisse la carte (relache pour fixer).")
        print("[Overlay] Si rien n'apparait en bataille : mets WoT en 'Fenetre sans "
              "bordure' (le plein ecran exclusif masque tout overlay).")

        root.after(50, self._poll_queue)
        try:
            root.mainloop()
        except KeyboardInterrupt:
            pass

    # ---- Radar tactique (2e fenetre pass-through) --------------------------
    def _build_radar_window(self, tk, root, main_x, main_y, sw, sh) -> None:
        size = self._radar_size
        # Ancrage par defaut : coin bas-droit (la ou est la minimap). L'offset
        # radar (Ctrl + glisser) permet de le caler pile sur la minimap.
        self._radar_base = (sw - size - 16, sh - size - 16)
        rx = self._radar_base[0] + self.settings.ui.radar_offset_x
        ry = self._radar_base[1] + self.settings.ui.radar_offset_y
        rx, ry = self._clamp_on_screen(rx, ry)
        win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        bg = _CARD if self.debug_opaque else _KEY
        win.configure(bg=bg)
        win.geometry("%dx%d+%d+%d" % (size, size, rx, ry))
        cv = tk.Canvas(win, width=size, height=size, bg=bg,
                       highlightthickness=0, bd=0)
        cv.pack(fill="both", expand=True)
        cv.bind("<ButtonPress-1>", self._on_radar_press)
        cv.bind("<B1-Motion>", self._on_radar_drag)
        cv.bind("<ButtonRelease-1>", self._on_radar_release)
        self._radar_win = win
        self._radar_canvas = cv
        win.update_idletasks()
        if not self.debug_opaque:
            try:
                self._layer_window(win, self.settings.ui.click_through)
            except Exception:
                logger.exception("radar : layering win32 a echoue")
        self._draw_radar_idle()

    def _radar_movable(self) -> bool:
        """Le radar se deplace/redimensionne quand Ctrl est maintenu (comme la bulle)."""
        return self._move_mode

    def _on_radar_press(self, e):
        if self._radar_movable() and self._radar_win is not None:
            self._radar_drag = (e.x_root, e.y_root,
                                self._radar_win.winfo_x(), self._radar_win.winfo_y())

    def _on_radar_drag(self, e):
        if self._radar_drag and self._radar_win is not None:
            rx, ry, wx, wy = self._radar_drag
            self._radar_win.geometry("+%d+%d" % (wx + (e.x_root - rx), wy + (e.y_root - ry)))

    def _on_radar_release(self, e):
        if self._radar_drag is None or self._radar_win is None:
            return
        self._radar_drag = None
        ox = self._radar_win.winfo_x() - self._radar_base[0]
        oy = self._radar_win.winfo_y() - self._radar_base[1]
        self.settings.ui.radar_offset_x, self.settings.ui.radar_offset_y = ox, oy
        if self.persist_radar:
            try:
                self.persist_radar(ox, oy)
            except Exception:
                logger.exception("persist_radar a echoue")

    def _layer_window(self, win, click_through: bool) -> str:
        import ctypes
        from ctypes import wintypes
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_TOOLWINDOW = 0x00000080
        LWA_COLORKEY = 0x00000001
        u = ctypes.windll.user32
        h = u.GetAncestor(win.winfo_id(), 2) or win.winfo_id()
        hwnd = wintypes.HWND(h)
        u.GetWindowLongW.restype = ctypes.c_long
        base = WS_EX_LAYERED | WS_EX_TOOLWINDOW
        if click_through:
            base |= WS_EX_TRANSPARENT
        cur = u.GetWindowLongW(hwnd, GWL_EXSTYLE) & ~WS_EX_TRANSPARENT
        u.SetWindowLongW(hwnd, GWL_EXSTYLE, cur | base)
        u.SetLayeredWindowAttributes(hwnd, _KEY_COLORREF, 255, LWA_COLORKEY)
        return "radar layered"

    def _radar_overlay_mode(self) -> bool:
        return self.settings.ui.radar_mode != "panel"

    def _draw_radar_idle(self) -> None:
        if self._radar_canvas is None:
            return
        cv = self._radar_canvas
        cv.delete("all")
        s = self._radar_size
        if self._radar_overlay_mode():
            # Transparent : rien a dessiner tant qu'il n'y a pas d'etat. En mode
            # deplacement (Ctrl), un liseré aide a caler sur la minimap.
            if self._move_mode:
                cv.create_rectangle(1, 1, s - 1, s - 1, outline="#a6ff7a", width=2)
            return
        cv.create_rectangle(2, 2, s - 2, s - 2, outline="#3a4d33", width=2)
        cv.create_text(s // 2, s // 2, text="RADAR", fill="#3a4d33",
                       font=("Segoe UI", 9, "bold"))

    def _draw_radar(self, state: dict) -> None:
        from .radar import RadarProjection
        self._radar_state = state
        cv = self._radar_canvas
        if cv is None:
            return
        cv.delete("all")
        s = self._radar_size
        overlay = self._radar_overlay_mode()
        ext = state.get("extent") or [-500, 500, -500, 500]
        # En mode overlay (sur la minimap), pas de marge : l'emprise = la minimap.
        pad = 0 if overlay else 10
        proj = RadarProjection(ext[0], ext[1], ext[2], ext[3], s, s, pad=pad)

        if not overlay:
            cv.create_rectangle(2, 2, s - 2, s - 2, outline="#3a4d33", width=2)
        elif self._move_mode:
            cv.create_rectangle(1, 1, s - 1, s - 1, outline="#a6ff7a", width=2)

        zones = state.get("zones", [])
        route = state.get("route") or []
        # Itinéraire (flèche épaisse) vers la zone conseillée, sous le marqueur.
        if len(route) == 2:
            ax, ay = proj.to_px(tuple(route[0]))
            bx, by = proj.to_px(tuple(route[1]))
            cv.create_line(ax, ay, bx, by, fill="#111a0d", width=6, arrow="last",
                           arrowshape=(16, 20, 7))
            cv.create_line(ax, ay, bx, by, fill="#a6ff7a", width=3, arrow="last",
                           arrowshape=(14, 18, 6))
        # Zones : la 1re (meilleure) est un GROS marqueur bien visible.
        for i, z in enumerate(zones):
            px, py = proj.to_px(tuple(z["center"]))
            danger = z.get("kind") == "danger"
            if i == 0 and not danger:
                self._draw_target(cv, px, py)
            else:
                col = "#d9534f" if danger else "#6fcf4f"
                r = 9
                cv.create_oval(px - r, py - r, px + r, py + r, outline="#0d1a08", width=3)
                cv.create_oval(px - r, py - r, px + r, py + r, outline=col, width=2)
        # Alliés (bleu) et ennemis spottés (rouge) — petits points contrastés.
        for a in state.get("allies", []):
            px, py = proj.to_px(tuple(a))
            cv.create_oval(px - 2, py - 2, px + 2, py + 2, fill="#4f9fd9",
                           outline="#0d1a08")
        for e in state.get("enemies", []):
            px, py = proj.to_px(tuple(e))
            cv.create_oval(px - 3, py - 3, px + 3, py + 3, fill="#d9534f",
                           outline="#ffffff")
        # Position propre (triangle vert vif, contour noir).
        own = state.get("own")
        if own:
            px, py = proj.to_px(tuple(own))
            cv.create_polygon(px, py - 7, px - 6, py + 6, px + 6, py + 6,
                              fill="#a6ff7a", outline="#0d1a08", width=2)

    def _draw_target(self, cv, px: int, py: int) -> None:
        """Gros marqueur de destination : anneaux + croix + pastille — lisible
        sur une minimap chargée (contour noir pour le contraste)."""
        for r, w in ((16, 3), (16, 2), (9, 3)):
            col = "#0d1a08" if w == 3 and r == 16 else "#a6ff7a"
            cv.create_oval(px - r, py - r, px + r, py + r, outline=col, width=w)
        # Croix de visée.
        cv.create_line(px - 20, py, px + 20, py, fill="#0d1a08", width=3)
        cv.create_line(px, py - 20, px, py + 20, fill="#0d1a08", width=3)
        cv.create_line(px - 20, py, px + 20, py, fill="#a6ff7a", width=1)
        cv.create_line(px, py - 20, px, py + 20, fill="#a6ff7a", width=1)
        # Pastille centrale.
        cv.create_oval(px - 3, py - 3, px + 3, py + 3, fill="#a6ff7a", outline="#0d1a08")

    def _anchor_base(self, sw, sh):
        m = 16
        a = self.settings.ui.anchor
        if a == "bottom_left":
            return m, sh - self._h - m
        if a == "bottom_right":
            return sw - self._w - m, sh - self._h - m
        if a == "top_left":
            return m, m
        return sw - self._w - m, m  # top_right (defaut)

    def _clamp_on_screen(self, x: int, y: int) -> tuple[int, int]:
        """Garde la fenetre dans le bureau virtuel (multi-ecran) : evite qu'un
        offset memorise pousse l'overlay hors de tout ecran visible."""
        try:
            import ctypes
            gsm = ctypes.windll.user32.GetSystemMetrics
            vx = gsm(76)   # SM_XVIRTUALSCREEN
            vy = gsm(77)   # SM_YVIRTUALSCREEN
            vw = gsm(78)   # SM_CXVIRTUALSCREEN
            vh = gsm(79)   # SM_CYVIRTUALSCREEN
            min_vis = 80   # au moins 80 px doivent rester a l'ecran
            x = max(vx - self._w + min_vis, min(x, vx + vw - min_vis))
            y = max(vy, min(y, vy + vh - min_vis))
        except Exception:
            pass
        return x, y

    def _load_images(self, tk) -> int:
        for path in all_asset_paths():
            stem = path.stem[len("tank_"):]
            cond, _, expr = stem.partition("_")
            try:
                img = tk.PhotoImage(file=str(path)).subsample(2, 2)  # ~140 px
                self._images[(cond, expr)] = img
            except Exception:
                logger.warning("Image mascotte introuvable: %s", path.name)
        return len(self._images)

    # ---- Styles Win32 (transparence + click-through) -----------------------
    def _hwnd(self):
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        h = u.GetAncestor(self._root.winfo_id(), 2) or self._root.winfo_id()  # GA_ROOT
        return u, wintypes.HWND(h)

    def _set_click_through(self, enabled: bool) -> str:
        try:
            import ctypes
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_TOOLWINDOW = 0x00000080
            LWA_COLORKEY = 0x00000001
            u, hwnd = self._hwnd()
            u.GetWindowLongW.restype = ctypes.c_long
            base = WS_EX_LAYERED | WS_EX_TOOLWINDOW
            if enabled:
                base |= WS_EX_TRANSPARENT
            # On repart de l'exstyle courant en enlevant TRANSPARENT puis en le
            # remettant selon 'enabled' (permet de basculer pour le deplacement).
            cur = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
            cur &= ~WS_EX_TRANSPARENT
            u.SetWindowLongW(hwnd, GWL_EXSTYLE, cur | base)
            u.SetLayeredWindowAttributes(hwnd, _KEY_COLORREF, 255, LWA_COLORKEY)
            SWP = 0x0001 | 0x0002 | 0x0004 | 0x0020
            u.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP)
            return "win32=OK transparence=ON click-through=%s" % ("ON" if enabled else "OFF")
        except Exception as exc:
            return "win32=INDISPONIBLE (%s)" % exc

    # ---- Deplacement (Ctrl + glisser) --------------------------------------
    @staticmethod
    def _ctrl_down() -> bool:
        try:
            import ctypes
            return bool(ctypes.windll.user32.GetAsyncKeyState(0x11) & 0x8000)
        except Exception:
            return False

    def _enter_move_mode(self) -> None:
        self._move_mode = True
        self._move_origin = (self._root.winfo_x(), self._root.winfo_y())
        if not self.debug_opaque:
            self._set_click_through(False)   # capter la souris
        try:
            self._root.config(cursor="fleur")
        except Exception:
            pass
        self._redraw()
        self._refresh_radar()

    def _exit_move_mode(self) -> None:
        self._move_mode = False
        if not self.debug_opaque:
            self._set_click_through(self.settings.ui.click_through)
        try:
            self._root.config(cursor="")
        except Exception:
            pass
        # Ne persiste QUE si la fenetre a reellement bouge (evite le spam quand on
        # relache Ctrl sans avoir deplace).
        cur = (self._root.winfo_x(), self._root.winfo_y())
        moved = self._move_origin is None or \
            abs(cur[0] - self._move_origin[0]) > 2 or abs(cur[1] - self._move_origin[1]) > 2
        self._move_origin = None
        if moved:
            ox = cur[0] - self._base_x
            oy = cur[1] - self._base_y
            self.settings.ui.offset_x, self.settings.ui.offset_y = ox, oy
            if self.persist_position:
                try:
                    self.persist_position(ox, oy)
                except Exception:
                    logger.exception("persist_position a echoue")
        self._redraw()
        self._refresh_radar()

    def _refresh_radar(self) -> None:
        if self._radar_canvas is None:
            return
        if self._radar_state is not None:
            self._draw_radar(self._radar_state)
        else:
            self._draw_radar_idle()

    def _on_press(self, e):
        if self._move_mode:
            self._drag = (e.x_root, e.y_root, self._root.winfo_x(), self._root.winfo_y())

    def _on_drag(self, e):
        if self._move_mode and self._drag:
            rx, ry, wx, wy = self._drag
            self._root.geometry("+%d+%d" % (wx + (e.x_root - rx), wy + (e.y_root - ry)))

    # ---- Traitement des messages -------------------------------------------
    def _poll_queue(self) -> None:
        if self._closing:
            return
        ctrl = self._ctrl_down()
        if ctrl and not self._move_mode:
            self._enter_move_mode()
        elif not ctrl and self._move_mode:
            self._exit_move_mode()
        try:
            while True:
                msg = self._queue.get_nowait()
                if msg.get("clear"):
                    self._draw_idle()
                elif "radar" in msg:
                    self._draw_radar(msg["radar"])
                elif "state_hp_ratio" in msg:
                    self._update_condition(msg["state_hp_ratio"])
                else:
                    self._render_advice(msg)
        except queue.Empty:
            pass
        if self._root is not None:
            self._root.after(50, self._poll_queue)

    def _update_condition(self, hp_ratio: float) -> None:
        """Suit l'etat du char (neuf/abime) en direct et redessine si change."""
        cond = condition_for_hp(hp_ratio)
        if cond != self._last_condition:
            self._last_condition = cond
            self._redraw()

    def _render_advice(self, msg: dict) -> None:
        if msg.get("hp_ratio") is not None:
            self._last_condition = condition_for_hp(msg["hp_ratio"])
        self._current = msg
        self._redraw()
        # Le dernier conseil RESTE affiche jusqu'au suivant (pas de "carre vide") :
        # on n'efface plus automatiquement au bout du TTL. Le message ne disparait
        # qu'au changement de bataille (clear()).

    def _draw_idle(self, startup: bool = False) -> None:
        self._current = None
        self._redraw(startup=startup)

    # ---- Dessin ------------------------------------------------------------
    def _redraw(self, startup: bool = False) -> None:
        if self._canvas is None:
            return
        c = self._canvas
        c.delete("all")
        msg = self._current
        # Plus de grande carte de fond : uniquement la mascotte + la bulle de texte
        # (le reste de la fenetre est transparent). Prend moins de place a l'ecran.
        if self.settings.ui.character_visible:
            expr = expression_for(msg["category"], msg["severity"], msg["action"]) if msg else "idle"
            self._draw_mascot(self._last_condition, expr)
        if msg:
            accent = _GARAGE_ACCENT if msg.get("garage") else accent_color(msg["severity"])
            self._draw_bubble(msg["text"], accent)
        if self._move_mode:
            # En mode deplacement, un reperage discret pour saisir la fenetre.
            self._round_rect(2, 2, self._w - 2, self._h - 2, r=18,
                             fill=_KEY, outline="#ffd27a", width=2)
            c.create_text(self._w // 2, 10, anchor="n",
                          text="⋮ Ctrl + glisser — relâche pour fixer",
                          fill="#ffd27a", font=("Segoe UI", 10, "bold"))

    def _draw_mascot(self, condition: str, expression: str) -> None:
        key = resolve(condition, expression)
        img = self._images.get(key) or self._images.get((condition, "idle")) \
            or self._images.get(("neuf", "idle"))
        if img is not None:
            self._canvas.create_image(self._w - 8, self._h - 8, image=img, anchor="se")

    def _draw_bubble(self, text: str, accent: str) -> None:
        c = self._canvas
        pad = 12
        left = 10
        right = self._w - _MASCOT_W      # laisse la place a la mascotte + un espace
        wrap = right - left - 2 * pad
        font_size = max(10, int(13 * self.settings.ui.text_scale))
        # 1) mesurer le texte, 2) dessiner la bulle a sa taille, 3) placer le texte.
        t = c.create_text(left + pad, 0, anchor="nw", text=text, fill="#20242b",
                          font=("Segoe UI", font_size, "bold"), width=wrap)
        bb = c.bbox(t)
        text_h = (bb[3] - bb[1]) if bb else 40
        by1 = self._h - 16
        by0 = max(10, by1 - (text_h + 2 * pad))
        r = self._round_rect(left, by0, right, by1, r=16,
                             fill="#fbf7ea", outline=accent, width=3)
        c.coords(t, left + pad, by0 + pad)
        c.tag_lower(r, t)
        # Petit ergot de bulle pointant vers la mascotte (a droite).
        tip_y = (by0 + by1) / 2
        c.create_polygon(right, tip_y - 9, right + 12, tip_y, right, tip_y + 9,
                         fill="#fbf7ea", outline=accent, width=2)

    def _round_rect(self, x0, y0, x1, y1, r=16, **kw):
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
               x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return self._canvas.create_polygon(pts, smooth=True, **kw)


def is_available() -> bool:
    try:
        import tkinter  # noqa: F401
        return True
    except Exception:
        return False
