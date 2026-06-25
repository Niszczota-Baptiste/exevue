"""Fenêtre principale MF Cockpit : titlebar, sidebar nav, contenu thémé.

L'UI ne fait JAMAIS de réseau : une boucle `after()` lit le snapshot du poller
et rafraîchit l'onglet visible. Tout le périodique vit dans le thread de fond.
Le rendu est restylé (look « cockpit » violet) sans rien changer à l'archi.
"""
import tkinter as tk
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

import customtkinter as ctk

from ..backend import notify
from ..backend.clipboard import ClipboardManager
from ..backend.config import Config
from ..backend.korean import Deck
from ..backend.poller import Poller
from ..backend.tracker import Tracker
from . import theme
from .theme import C
from .tab_coreen import CoreenTab
from .tab_mf import MFTab
from .tab_outils import OutilsTab
from .tab_systeme import SystemeTab
from .tab_temps import TempsTab

theme.apply_theme()

NAV = [
    ("MF", "mf"), ("Temps", "temps"), ("Outils", "outils"),
    ("Coréen", "coreen"), ("Système", "systeme"),
]


def _draw_icon(cv, key, color):
    cv.delete("all")
    o = {"width": 2, "fill": color, "capstyle": "round", "joinstyle": "round"}
    if key == "mf":
        cv.create_line(2, 11, 6, 7, 9, 10, 13, 5, 16, 8, **o)
        cv.create_line(2, 15, 16, 15, fill=color, width=2, capstyle="round")
    elif key == "temps":
        cv.create_oval(2, 2, 16, 16, outline=color, width=2)
        cv.create_line(9, 9, 9, 5, **o)
        cv.create_line(9, 9, 12, 11, **o)
    elif key == "outils":
        cv.create_line(4, 14, 13, 5, **o)
        cv.create_oval(11, 2, 17, 8, outline=color, width=2)
    elif key == "coreen":
        cv.create_text(9, 9, text="가", fill=color,
                       font=theme.font("body", 13, "bold"))
    elif key == "systeme":
        cv.create_rectangle(2, 4, 16, 13, outline=color, width=2)
        cv.create_line(6, 16, 12, 16, **o)


class App(ctk.CTk):
    UI_REFRESH_MS = 1000

    def __init__(self):
        super().__init__()
        self.config_store = Config()
        self.configure(fg_color=C["page"])

        self.title("MF Cockpit")
        self.geometry(self.config_store.get("window_geometry", "470x860"))
        self.minsize(400, 580)

        self.tracker = Tracker(self.config_store)
        self.clipboard = ClipboardManager(self.config_store,
                                          tk_root_getter=lambda: self)
        self.deck = Deck(self.config_store)
        self.poller = Poller(self.config_store, self.tracker, self.clipboard)
        notify.set_banner_callback(self.show_banner)

        self._active = "mf"
        self._nav = {}

        self._build_titlebar()
        self._build_banner()
        self._build_body()

        self.poller.start()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(self.UI_REFRESH_MS, self._tick_ui)
        self._tick_clocks()
        self.after(800, self._launch_korean_review)

    # ---- titlebar ----
    def _build_titlebar(self):
        bar = ctk.CTkFrame(self, fg_color=C["titlebar"], corner_radius=0,
                           border_width=0, height=44)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        left = ctk.CTkFrame(bar, fg_color="transparent")
        left.pack(side="left", padx=14)
        self.aot_var = ctk.BooleanVar(
            value=bool(self.config_store.get("always_on_top", False)))
        self.attributes("-topmost", self.aot_var.get())
        ctk.CTkSwitch(left, text="", width=38, variable=self.aot_var,
                      command=self._toggle_aot).pack(side="left")
        ctk.CTkLabel(left, text="AU-DESSUS", font=theme.font("head", 11, "bold"),
                     text_color=C["muted"]).pack(side="left", padx=(8, 0))

        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.pack(side="right", padx=14)
        self.clock_local = self._clock_col(right, "LOCAL", C["dim"], C["text"])
        sep = ctk.CTkFrame(right, fg_color=C["inset_border"], width=1, height=22)
        sep.pack(side="left", padx=12, pady=8)
        self.clock_seoul = self._clock_col(right, "SÉOUL", C["accent_lt"],
                                           C["accent_lt2"])

    def _clock_col(self, parent, caption, cap_color, time_color):
        col = ctk.CTkFrame(parent, fg_color="transparent")
        col.pack(side="left")
        ctk.CTkLabel(col, text=caption, font=theme.font("head", 8, "bold"),
                     text_color=cap_color).pack(anchor="e")
        lbl = ctk.CTkLabel(col, text="--:--:--", font=theme.font("mono", 13),
                           text_color=time_color)
        lbl.pack(anchor="e")
        return lbl

    def _toggle_aot(self):
        on = bool(self.aot_var.get())
        self.attributes("-topmost", on)
        self.config_store.set("always_on_top", on)

    def _tick_clocks(self):
        self.clock_local.configure(text=datetime.now().strftime("%H:%M:%S"))
        if ZoneInfo is not None:
            try:
                self.clock_seoul.configure(
                    text=datetime.now(ZoneInfo("Asia/Seoul")).strftime("%H:%M:%S"))
            except Exception:
                pass
        self.after(1000, self._tick_clocks)

    # ---- banner ----
    def _build_banner(self):
        self.banner = ctk.CTkLabel(self, text="", fg_color="#33271a",
                                   corner_radius=6, anchor="w",
                                   font=theme.font("body", 12))
        self._banner_after = None

    def show_banner(self, text, ms=8000):
        def _apply():
            self.banner.configure(text="  " + text)
            self.banner.pack(fill="x", padx=8, pady=(6, 0))
            if self._banner_after:
                self.after_cancel(self._banner_after)
            self._banner_after = self.after(ms, self.banner.pack_forget)
        try:
            self.after(0, _apply)
        except Exception:
            pass

    # ---- body : sidebar + content ----
    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)

        self._build_sidebar(body)

        self.content = ctk.CTkFrame(body, fg_color="transparent")
        self.content.pack(side="left", fill="both", expand=True, padx=(8, 8),
                          pady=8)

        self.tabs = {
            "mf": MFTab(self.content, self),
            "temps": TempsTab(self.content, self),
            "outils": OutilsTab(self.content, self),
            "coreen": CoreenTab(self.content, self),
            "systeme": SystemeTab(self.content, self),
        }
        self._show_tab("mf")

    def _build_sidebar(self, parent):
        side = ctk.CTkFrame(parent, fg_color=C["sidebar"], corner_radius=0,
                            width=132, border_width=0)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        brand = ctk.CTkFrame(side, fg_color="transparent")
        brand.pack(fill="x", padx=12, pady=(14, 12))
        theme.diamond(brand, 9).pack(side="left", padx=(0, 8))
        # le losange a un bg de carte ; corrige-le pour la sidebar
        for w in brand.winfo_children():
            if isinstance(w, tk.Canvas):
                w.configure(bg=C["sidebar"])
        ctk.CTkLabel(brand, text="PANEL", font=theme.font("head", 13, "bold"),
                     text_color="#d8cdf2").pack(side="left")

        for label, key in NAV:
            self._nav[key] = self._nav_item(side, label, key)

        spacer = ctk.CTkFrame(side, fg_color="transparent")
        spacer.pack(fill="both", expand=True)

        conn = ctk.CTkFrame(side, fg_color="transparent")
        conn.pack(fill="x", padx=14, pady=(6, 12))
        dot = tk.Canvas(conn, width=8, height=8, highlightthickness=0,
                        bg=C["sidebar"])
        dot.create_oval(0, 0, 8, 8, fill=C["green"], outline="")
        dot.pack(side="left", padx=(0, 7))
        ctk.CTkLabel(conn, text="CONNECTÉ", font=theme.font("head", 9, "bold"),
                     text_color=C["dimmer"]).pack(side="left")

    def _nav_item(self, parent, label, key):
        row = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=9,
                           height=42)
        row.pack(fill="x", padx=9, pady=2)
        row.pack_propagate(False)

        bar = ctk.CTkFrame(row, fg_color="transparent", width=3, corner_radius=2)
        bar.pack(side="left", fill="y", padx=(0, 8), pady=7)
        icon = tk.Canvas(row, width=18, height=18, highlightthickness=0,
                         bg=C["sidebar"])
        icon.pack(side="left", padx=(2, 10))
        lbl = ctk.CTkLabel(row, text=label, font=theme.font("head", 13, "bold"),
                           text_color=C["muted"])
        lbl.pack(side="left")

        meta = {"row": row, "bar": bar, "icon": icon, "lbl": lbl, "key": key}
        for w in (row, icon, lbl, bar):
            w.bind("<Button-1>", lambda e, k=key: self._show_tab(k))
            w.bind("<Enter>", lambda e, m=meta: self._nav_hover(m, True))
            w.bind("<Leave>", lambda e, m=meta: self._nav_hover(m, False))
        return meta

    def _nav_hover(self, meta, on):
        if meta["key"] == self._active:
            return
        meta["row"].configure(fg_color=C["nav_active"] if on else "transparent")

    def _style_nav(self):
        for key, m in self._nav.items():
            active = key == self._active
            m["row"].configure(fg_color=C["nav_active"] if active else "transparent")
            m["bar"].configure(fg_color=C["accent_lt"] if active else "transparent")
            color = "#f1ecff" if active else C["muted"]
            m["lbl"].configure(text_color=color)
            _draw_icon(m["icon"], key, C["accent_lt"] if active else C["muted"])

    def _show_tab(self, key):
        self._active = key
        for k, tab in self.tabs.items():
            tab.pack_forget()
        self.tabs[key].pack(fill="both", expand=True)
        self._style_nav()
        try:
            self.tabs[key].refresh(self.poller.get_snapshot())
        except Exception:
            pass

    # ---- refresh : seulement l'onglet visible (perf) ----
    def _tick_ui(self):
        snap = self.poller.get_snapshot()
        tab = self.tabs.get(self._active)
        if tab is not None:
            try:
                tab.refresh(snap)
            except Exception:
                pass
        self.after(self.UI_REFRESH_MS, self._tick_ui)

    def _launch_korean_review(self):
        try:
            self.tabs["coreen"].start_session()
        except Exception:
            pass

    # ---- fermeture ----
    def _on_close(self):
        try:
            self.config_store.set("window_geometry", self.geometry())
        except Exception:
            pass
        try:
            self.poller.stop()
        except Exception:
            pass
        try:
            self.tracker.end_session()
        except Exception:
            pass
        self.destroy()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
