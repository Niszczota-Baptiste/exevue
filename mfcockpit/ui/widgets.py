"""Petits widgets de dessin (tkinter.Canvas) : voyant, sparkline, barres.

Pas de matplotlib — tout est tracé à la main pour rester léger et
PyInstaller-friendly.
"""
import tkinter as tk

import customtkinter as ctk

COLORS = {
    "green": "#2ecc71",
    "orange": "#f39c12",
    "red": "#e74c3c",
    "grey": "#555555",
    "accent": "#4a9eff",
    "bg": "#1a1a1a",
    "muted": "#888888",
}


class Indicator(ctk.CTkFrame):
    """Voyant couleur + libellé."""

    def __init__(self, master, text="", size=14, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self._canvas = tk.Canvas(self, width=size, height=size,
                                 highlightthickness=0, bg=self._bg())
        self._canvas.grid(row=0, column=0, padx=(0, 6))
        pad = 2
        self._dot = self._canvas.create_oval(pad, pad, size - pad, size - pad,
                                             fill=COLORS["grey"], outline="")
        self._label = ctk.CTkLabel(self, text=text, anchor="w")
        self._label.grid(row=0, column=1, sticky="w")

    def _bg(self):
        try:
            return self._apply_appearance_mode(ctk.ThemeManager.theme["CTkFrame"]["fg_color"])
        except Exception:
            return COLORS["bg"]

    def set(self, color_key, text=None):
        self._canvas.itemconfig(self._dot, fill=COLORS.get(color_key, COLORS["grey"]))
        if text is not None:
            self._label.configure(text=text)


class Sparkline(tk.Canvas):
    """Courbe simple d'une série de valeurs."""

    def __init__(self, master, width=380, height=60, color=None, **kw):
        super().__init__(master, width=width, height=height,
                         highlightthickness=0, bg=COLORS["bg"], **kw)
        self._cw = width
        self._ch = height
        self._color = color or COLORS["accent"]

    def set_series(self, values):
        self.delete("all")
        w, h = self._cw, self._ch
        if not values:
            self.create_text(w / 2, h / 2, text="(pas de données)",
                             fill=COLORS["muted"], font=("", 9))
            return
        vmax = max(values)
        vmin = min(values)
        span = (vmax - vmin) or 1
        n = len(values)
        pad = 4
        usable_h = h - 2 * pad
        usable_w = w - 2 * pad
        step = usable_w / max(1, n - 1) if n > 1 else 0
        pts = []
        for i, v in enumerate(values):
            x = pad + i * step
            y = pad + usable_h * (1 - (v - vmin) / span)
            pts.extend([x, y])
        if len(pts) >= 4:
            self.create_line(*pts, fill=self._color, width=2, smooth=True)
        # marqueur dernière valeur
        if pts:
            self.create_oval(pts[-2] - 3, pts[-1] - 3, pts[-2] + 3, pts[-1] + 3,
                             fill=self._color, outline="")
        self.create_text(w - pad, pad + 4, text=f"max {int(vmax)}",
                         fill=COLORS["muted"], anchor="ne", font=("", 8))
        self.create_text(w - pad, h - pad, text=f"min {int(vmin)}",
                         fill=COLORS["muted"], anchor="se", font=("", 8))


class BarChart(tk.Canvas):
    """Barres empilées solo (bas) + multi (haut), avec libellés."""

    def __init__(self, master, width=380, height=120, **kw):
        super().__init__(master, width=width, height=height,
                         highlightthickness=0, bg=COLORS["bg"], **kw)
        self._cw = width
        self._ch = height

    def set_data(self, rows):
        """rows = [(label, solo_seconds, multi_seconds)]."""
        self.delete("all")
        w, h = self._cw, self._ch
        if not rows:
            return
        pad_bottom = 16
        pad_top = 6
        usable_h = h - pad_bottom - pad_top
        n = len(rows)
        slot = w / n
        bar_w = slot * 0.6
        vmax = max((s + m) for _, s, m in rows) or 1
        for i, (label, solo, multi) in enumerate(rows):
            cx = slot * i + slot / 2
            x0 = cx - bar_w / 2
            x1 = cx + bar_w / 2
            total = solo + multi
            total_h = usable_h * (total / vmax)
            y_base = h - pad_bottom
            # solo (bas)
            solo_h = usable_h * (solo / vmax)
            if solo_h > 0:
                self.create_rectangle(x0, y_base - solo_h, x1, y_base,
                                      fill=COLORS["accent"], outline="")
            # multi (au-dessus)
            multi_h = usable_h * (multi / vmax)
            if multi_h > 0:
                self.create_rectangle(x0, y_base - solo_h - multi_h, x1,
                                      y_base - solo_h, fill=COLORS["green"],
                                      outline="")
            self.create_text(cx, h - pad_bottom + 8, text=label,
                             fill=COLORS["muted"], font=("", 8))
            if total > 0:
                mins = int(total / 60)
                self.create_text(cx, y_base - total_h - 6, text=f"{mins}m",
                                 fill=COLORS["muted"], font=("", 8))
