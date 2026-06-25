"""Onglet [Temps] : session, totaux, jour, 7 jours, rappel pause."""
import customtkinter as ctk

from ..backend.tracker import fmt
from .widgets import BarChart


class TempsTab(ctk.CTkScrollableFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.cfg = app.config_store
        self.tracker = app.tracker
        self._build()

    def _section(self, title):
        ctk.CTkLabel(self, text=title, font=("", 13, "bold"),
                     anchor="w").pack(fill="x", padx=4, pady=(10, 2))
        frame = ctk.CTkFrame(self)
        frame.pack(fill="x", padx=4, pady=2)
        return frame

    def _build(self):
        f = self._section("Session en cours")
        self.session_lbl = ctk.CTkLabel(f, text="", anchor="w", justify="left")
        self.session_lbl.pack(fill="x", padx=8, pady=8)

        f = self._section("Totaux")
        self.totals_lbl = ctk.CTkLabel(f, text="", anchor="w", justify="left")
        self.totals_lbl.pack(fill="x", padx=8, pady=8)

        f = self._section("7 derniers jours")
        self.week_lbl = ctk.CTkLabel(f, text="", anchor="w", justify="left")
        self.week_lbl.pack(fill="x", padx=8, pady=(8, 2))
        self.bars = BarChart(f, width=380, height=120)
        self.bars.pack(fill="x", padx=8, pady=(0, 8))

        f = self._section("Rappel pause")
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=8)
        ctk.CTkLabel(row, text="Notif après (h) :").pack(side="left")
        self.break_entry = ctk.CTkEntry(row, width=60)
        self.break_entry.insert(0, str(self.cfg.get("break_reminder_hours", 2.0)))
        self.break_entry.pack(side="left", padx=6)
        ctk.CTkButton(row, text="OK", width=40,
                      command=self._save_break).pack(side="left")

    def _save_break(self):
        try:
            self.cfg.set("break_reminder_hours", float(
                self.break_entry.get().replace(",", ".")))
        except ValueError:
            pass

    def refresh(self, snap):
        t = self.tracker
        if t.playing:
            state = f"EN COURS ({(t.mode or '').upper()})"
        else:
            state = "à l'arrêt"
        self.session_lbl.configure(
            text=f"Jeu : {state}\n"
                 f"Session — solo {fmt(t.session['solo'])} | "
                 f"multi {fmt(t.session['multi'])}\n"
                 f"D'affilée : {fmt(t.continuous_seconds)}")

        solo_d, multi_d = t.today()
        self.totals_lbl.configure(
            text=f"TOTAL solo   : {fmt(t.total_solo)}\n"
                 f"TOTAL multi  : {fmt(t.total_multi)}\n"
                 f"TOTAL global : {fmt(t.total_solo + t.total_multi)}\n"
                 f"Aujourd'hui  : solo {fmt(solo_d)} | multi {fmt(multi_d)}")

        rows = t.last_n_days(7)
        self.bars.set_data(rows)
        ws = t.week_stats()
        ratio = ("∞" if ws["ratio"] == float("inf")
                 else f"{ws['ratio']:.2f}")
        self.week_lbl.configure(
            text=f"Moyenne/jour : {fmt(ws['avg_per_day'])}   "
                 f"ratio solo/multi : {ratio}\n"
                 f"(bleu = solo, vert = multi)")
