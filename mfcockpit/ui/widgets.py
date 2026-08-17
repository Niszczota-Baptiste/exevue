"""Petits widgets de dessin (tkinter.Canvas) : voyant à halo, sparkline, barres.

Pas de matplotlib — tout est tracé à la main pour rester léger et
PyInstaller-friendly. Couleurs alignées sur le thème violet (theme.C).
"""
import tkinter as tk

import customtkinter as ctk

from . import theme

C = theme.C

# clés de couleur des voyants -> hex du thème
DOT = {
    "green": C["green"], "orange": C["orange"], "red": C["red"],
    "blue": C["blue"], "grey": C["grey"], "accent": C["accent_lt"],
}


def _mix(hex1, hex2, t):
    """Mélange linéaire de deux couleurs hex (t=0 -> hex1, t=1 -> hex2)."""
    a = [int(hex1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex2[i:i + 2], 16) for i in (1, 3, 5)]
    m = [round(a[i] + (b[i] - a[i]) * t) for i in range(3)]
    return f"#{m[0]:02x}{m[1]:02x}{m[2]:02x}"


class Indicator(ctk.CTkFrame):
    """Voyant (point lumineux avec halo) + libellé."""

    def __init__(self, master, text="", size=16, bg=None, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self._bg_color = bg or C["card"]
        self._size = size
        self._canvas = tk.Canvas(self, width=size, height=size,
                                 highlightthickness=0, bg=self._bg_color)
        self._canvas.grid(row=0, column=0, padx=(0, 9))
        self._halo = None
        self._dot = None
        self._color = C["grey"]
        self._render_dot()
        self._label = ctk.CTkLabel(self, text=text, anchor="w",
                                   font=theme.font("body", 13),
                                   text_color=C["text_norm"])
        self._label.grid(row=0, column=1, sticky="w")

    def _render_dot(self):
        s = self._size
        self._canvas.delete("all")
        # halo : anneau diffus dans une teinte sombre de la couleur
        halo = _mix(self._bg_color, self._color, 0.45)
        self._canvas.create_oval(0, 0, s, s, fill=halo, outline="")
        pad = s * 0.28
        self._canvas.create_oval(pad, pad, s - pad, s - pad,
                                 fill=self._color, outline="")

    def set(self, color_key, text=None):
        self._color = DOT.get(color_key, C["grey"])
        self._render_dot()
        if text is not None:
            self._label.configure(text=text)


class Sparkline(tk.Canvas):
    """Courbe + aire dégradée approximée (violet)."""

    def __init__(self, master, width=380, height=64, bg=None, **kw):
        self._bg = bg or C["page"]
        super().__init__(master, width=width, height=height,
                         highlightthickness=0, bg=self._bg, **kw)
        self._cw = width
        self._ch = height

    def set_series(self, values):
        self.delete("all")
        w, h = self._cw, self._ch
        if not values:
            self.create_text(w / 2, h / 2, text="(pas de données)",
                             fill=C["dim"], font=theme.font("head", 9))
            return
        vmax, vmin = max(values), min(values)
        span = (vmax - vmin) or 1
        n = len(values)
        pad = 5
        usable_h = h - 2 * pad
        usable_w = w - 2 * pad
        step = usable_w / max(1, n - 1) if n > 1 else 0
        pts = []
        for i, v in enumerate(values):
            x = pad + i * step
            y = pad + usable_h * (1 - (v - vmin) / span)
            pts.extend([x, y])
        # aire sous la courbe (teinte sombre) pour simuler le dégradé
        if len(pts) >= 4:
            area = [pad, h - pad] + pts + [pad + (n - 1) * step, h - pad]
            self.create_polygon(*area, fill=_mix(self._bg, C["accent"], 0.28),
                                outline="")
            self.create_line(*pts, fill=C["accent_lt"], width=2, smooth=True)
        if pts:
            self.create_oval(pts[-2] - 3, pts[-1] - 3, pts[-2] + 3, pts[-1] + 3,
                             fill=C["accent_lt2"], outline="")
        self.create_text(w - pad, pad + 2, text=f"max {int(vmax)}",
                         fill=C["dim"], anchor="ne", font=theme.font("head", 8))
        self.create_text(w - pad, h - pad, text=f"min {int(vmin)}",
                         fill=C["dim"], anchor="se", font=theme.font("head", 8))


class LineChart(tk.Canvas):
    """Une ou plusieurs courbes sur un axe commun, avec grille et légende.

    Même esprit que `Sparkline` mais multi-séries : c'est ce qui permet de
    superposer la courbe des douleurs et le volume jambes sur le même graphe.
    """

    def __init__(self, master, width=380, height=150, bg=None, **kw):
        self._bg = bg or C["page"]
        super().__init__(master, width=width, height=height,
                         highlightthickness=0, bg=self._bg, **kw)
        self._cw = width
        self._ch = height

    def set_series(self, series, labels=None, y_max=None, y_min=None):
        """series = [(nom, couleur_hex, [valeurs|None])]. Les `None` coupent la
        courbe (pas de données ce jour-là) au lieu de la faire plonger à zéro."""
        self.delete("all")
        w, h = self._cw, self._ch
        series = [s for s in series if s[2]]
        if not series:
            self.create_text(w / 2, h / 2, text="(pas encore de données)",
                             fill=C["dim"], font=theme.font("head", 10))
            return

        pad_l, pad_r, pad_t, pad_b = 34, 8, 12, 20
        zone_w = w - pad_l - pad_r
        zone_h = h - pad_t - pad_b
        plates = [v for _, _, vals in series for v in vals if v is not None]
        if not plates:
            return
        vmax = y_max if y_max is not None else max(plates)
        vmin = y_min if y_min is not None else min(0, min(plates))
        span = (vmax - vmin) or 1

        for i in range(4):                                  # grille horizontale
            y = pad_t + zone_h * i / 3
            self.create_line(pad_l, y, w - pad_r, y, fill=C["inset_border"])
            self.create_text(pad_l - 5, y, anchor="e",
                             text=f"{vmax - span * i / 3:.0f}", fill=C["dim"],
                             font=theme.font("head", 8))

        n = max(len(vals) for _, _, vals in series)
        step = zone_w / max(1, n - 1)
        for nom, couleur, vals in series:
            segment = []
            for i, v in enumerate(vals):
                if v is None:
                    if len(segment) >= 4:
                        self.create_line(*segment, fill=couleur, width=2,
                                         smooth=True)
                    segment = []
                    continue
                segment += [pad_l + i * step,
                            pad_t + zone_h * (1 - (v - vmin) / span)]
            if len(segment) >= 4:
                self.create_line(*segment, fill=couleur, width=2, smooth=True)
            elif len(segment) == 2:
                self.create_oval(segment[0] - 3, segment[1] - 3,
                                 segment[0] + 3, segment[1] + 3,
                                 fill=couleur, outline="")

        if labels:
            pas = max(1, n // 6)
            for i in range(0, n, pas):
                if i < len(labels):
                    self.create_text(pad_l + i * step, h - pad_b + 9,
                                     text=labels[i], fill=C["dim"],
                                     font=theme.font("head", 8))
        x = pad_l
        for nom, couleur, _ in series:                       # légende
            self.create_rectangle(x, 2, x + 8, 8, fill=couleur, outline="")
            texte = self.create_text(x + 12, 5, anchor="w", text=nom,
                                     fill=C["muted"], font=theme.font("head", 8))
            # on avance de la largeur réellement occupée, sinon les libellés
            # se chevauchent dès qu'un nom est un peu long
            x = self.bbox(texte)[2] + 12


class Heatmap(tk.Canvas):
    """Calendrier façon GitHub : une case par jour, 7 lignes (L→D)."""

    def __init__(self, master, width=380, height=104, bg=None, **kw):
        self._bg = bg or C["page"]
        super().__init__(master, width=width, height=height,
                         highlightthickness=0, bg=self._bg, **kw)
        self._cw = width
        self._ch = height

    def set_data(self, cellules, on_click=None):
        """cellules = [(date_iso, intensite 0-1 ou None, jour_semaine 0-6)],
        du plus ancien au plus récent."""
        self.delete("all")
        if not cellules:
            return
        w, h = self._cw, self._ch
        pad_l, pad_t = 16, 10
        semaines = (len(cellules) // 7) + 2
        cote = max(4, min(11, int((w - pad_l - 6) / semaines)))
        ecart = 1 if cote < 8 else 2

        for i, (date_str, valeur, jsem) in enumerate(cellules):
            colonne = (i + cellules[0][2]) // 7
            x = pad_l + colonne * (cote + ecart)
            y = pad_t + jsem * (cote + ecart)
            if valeur is None:
                couleur = C["inset"]
            elif valeur <= 0:
                couleur = "#2a1a25"
            else:
                couleur = _mix(C["inset"], C["green"], 0.25 + 0.75 * valeur)
            self.create_rectangle(x, y, x + cote, y + cote, fill=couleur,
                                  outline="", tags=("j", date_str))
        for i, lettre in enumerate("LMMJVSD"):
            self.create_text(pad_l - 5, pad_t + i * (cote + ecart) + cote / 2,
                             anchor="e", text=lettre, fill=C["dimmer"],
                             font=theme.font("head", 7))
        if on_click:
            self.tag_bind("j", "<Button-1>",
                          lambda e: on_click(self.gettags("current")[1]))


class BarChart(tk.Canvas):
    """Barres empilées : solo (violet, bas) + multi (vert, haut)."""

    def __init__(self, master, width=380, height=120, bg=None, **kw):
        self._bg = bg or C["page"]
        super().__init__(master, width=width, height=height,
                         highlightthickness=0, bg=self._bg, **kw)
        self._cw = width
        self._ch = height

    def set_data(self, rows):
        """rows = [(label, solo_seconds, multi_seconds)]."""
        self.delete("all")
        w, h = self._cw, self._ch
        if not rows:
            return
        pad_bottom, pad_top = 18, 8
        usable_h = h - pad_bottom - pad_top
        n = len(rows)
        slot = w / n
        bar_w = slot * 0.55
        vmax = max((s + m) for _, s, m in rows) or 1
        for i, (label, solo, multi) in enumerate(rows):
            cx = slot * i + slot / 2
            x0, x1 = cx - bar_w / 2, cx + bar_w / 2
            y_base = h - pad_bottom
            solo_h = usable_h * (solo / vmax)
            multi_h = usable_h * (multi / vmax)
            if solo_h > 0:
                self.create_rectangle(x0, y_base - solo_h, x1, y_base,
                                      fill=C["accent"], outline="")
            if multi_h > 0:
                self.create_rectangle(x0, y_base - solo_h - multi_h, x1,
                                      y_base - solo_h, fill=C["green"], outline="")
            self.create_text(cx, h - pad_bottom + 9, text=label,
                             fill=C["dim"], font=theme.font("head", 8))
            total = solo + multi
            if total > 0:
                self.create_text(cx, y_base - solo_h - multi_h - 7,
                                 text=f"{int(total / 60)}m", fill=C["muted"],
                                 font=theme.font("head", 8))
