"""Onglet [Temps] : session, totaux, jour, 7 jours, rappel pause."""
import customtkinter as ctk

from ..backend.tracker import fmt
from . import theme
from .base import ThemedScroll
from .theme import C
from .widgets import BarChart


class TempsTab(ThemedScroll):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.tracker = app.tracker
        self._build()

    def _kv(self, parent, key, value_color=None):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text=key, font=theme.font("body", 13),
                     text_color=C["muted"]).pack(side="left")
        val = ctk.CTkLabel(row, text="—", font=theme.font("mono", 13),
                           text_color=value_color or C["text_norm"])
        val.pack(side="right")
        return val

    def _build(self):
        f = self._section("Session en cours")
        self.k_state = self._kv(f, "État")
        self.k_sess = self._kv(f, "Session (solo / multi)")
        self.k_streak = self._kv(f, "D'affilée", C["accent_lt2"])

        f = self._section("Totaux")
        self.k_solo = self._kv(f, "Solo", C["accent_lt"])
        self.k_multi = self._kv(f, "Multi", C["green"])
        self.k_global = self._kv(f, "Global", C["text"])
        self.k_today = self._kv(f, "Aujourd'hui")

        f = self._section("7 derniers jours")
        self.week_lbl = ctk.CTkLabel(f, text="", anchor="w", justify="left",
                                     font=theme.font("body", 12),
                                     text_color=C["muted"])
        self.week_lbl.pack(fill="x", pady=(0, 6))
        wrap = ctk.CTkFrame(f, fg_color=C["page"], corner_radius=8,
                            border_color=C["card_border"], border_width=1)
        wrap.pack(fill="x")
        self.bars = BarChart(wrap, width=380, height=120, bg=C["page"])
        self.bars.pack(fill="x", padx=6, pady=6)
        legend = ctk.CTkFrame(f, fg_color="transparent")
        legend.pack(fill="x", pady=(6, 0))
        self._legend(legend, C["accent"], "solo")
        self._legend(legend, C["green"], "multi")

        f = self._section("Rappel pause")
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(row, text="Notif après", font=theme.font("body", 13),
                     text_color=C["muted"]).pack(side="left")
        ctk.CTkButton(row, text="OK", width=42, command=self._save_break,
                      fg_color=C["accent"], hover_color=C["accent_dk"],
                      text_color="#f6f2ff", border_width=0,
                      font=theme.font("head", 11, "bold")).pack(side="right")
        ctk.CTkLabel(row, text="h", font=theme.font("body", 12),
                     text_color=C["muted"]).pack(side="right", padx=6)
        self.break_entry = ctk.CTkEntry(row, width=56, justify="center",
                                        font=theme.font("mono", 13))
        self.break_entry.insert(0, str(self.cfg.get("break_reminder_hours", 2.0)))
        self.break_entry.pack(side="right")

    def _legend(self, parent, color, text):
        import tkinter as tk
        cell = ctk.CTkFrame(parent, fg_color="transparent")
        cell.pack(side="left", padx=(0, 14))
        cv = tk.Canvas(cell, width=10, height=10, highlightthickness=0,
                       bg=C["card"])
        cv.create_rectangle(0, 0, 10, 10, fill=color, outline="")
        cv.pack(side="left", padx=(0, 5))
        ctk.CTkLabel(cell, text=text, font=theme.font("body", 11),
                     text_color=C["muted"]).pack(side="left")

    def _save_break(self):
        try:
            self.cfg.set("break_reminder_hours",
                         float(self.break_entry.get().replace(",", ".")))
        except ValueError:
            pass

    def refresh(self, snap):
        t = self.tracker
        if t.playing:
            self.k_state.configure(text=f"EN COURS · {(t.mode or '').upper()}",
                                   text_color=C["green"])
        else:
            self.k_state.configure(text="à l'arrêt", text_color=C["dim"])
        self.k_sess.configure(
            text=f"{fmt(t.session['solo'])} / {fmt(t.session['multi'])}")
        self.k_streak.configure(text=fmt(t.continuous_seconds))

        solo_d, multi_d = t.today()
        self.k_solo.configure(text=fmt(t.total_solo))
        self.k_multi.configure(text=fmt(t.total_multi))
        self.k_global.configure(text=fmt(t.total_solo + t.total_multi))
        self.k_today.configure(text=f"{fmt(solo_d)} / {fmt(multi_d)}")

        self.bars.set_data(t.last_n_days(7))
        ws = t.week_stats()
        ratio = "∞" if ws["ratio"] == float("inf") else f"{ws['ratio']:.2f}"
        self.week_lbl.configure(
            text=f"Moyenne/jour {fmt(ws['avg_per_day'])}   ·   ratio solo/multi {ratio}")
