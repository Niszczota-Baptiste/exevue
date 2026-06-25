"""Fenêtre principale MF Cockpit : onglets, horloges, toujours-au-dessus.

L'UI ne fait JAMAIS de réseau : une boucle `after()` lit le snapshot du poller
et rafraîchit les onglets. Tout le périodique vit dans le thread de fond.
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
from .tab_coreen import CoreenTab
from .tab_mf import MFTab
from .tab_outils import OutilsTab
from .tab_systeme import SystemeTab
from .tab_temps import TempsTab

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    UI_REFRESH_MS = 1000

    def __init__(self):
        super().__init__()
        self.config_store = Config()

        self.title("MF Cockpit")
        geom = self.config_store.get("window_geometry", "440x820")
        self.geometry(geom)
        self.minsize(360, 560)

        # backend
        self.tracker = Tracker(self.config_store)
        self.clipboard = ClipboardManager(
            self.config_store, tk_root_getter=lambda: self)
        self.deck = Deck(self.config_store)
        self.poller = Poller(self.config_store, self.tracker, self.clipboard)

        notify.set_banner_callback(self.show_banner)

        self._build_topbar()
        self._build_banner()
        self._build_tabs()

        self.poller.start()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(self.UI_REFRESH_MS, self._tick_ui)
        self._tick_clocks()

        # Micro-révision coréen au lancement (après affichage).
        self.after(800, self._launch_korean_review)

    # ---- barre du haut ----
    def _build_topbar(self):
        bar = ctk.CTkFrame(self)
        bar.pack(fill="x", padx=6, pady=(6, 0))

        self.aot_var = ctk.BooleanVar(value=bool(
            self.config_store.get("always_on_top", False)))
        self.attributes("-topmost", self.aot_var.get())
        aot = ctk.CTkSwitch(bar, text="Au-dessus", variable=self.aot_var,
                            command=self._toggle_aot, width=90)
        aot.pack(side="left", padx=6, pady=6)

        self.clock_label = ctk.CTkLabel(bar, text="", anchor="e",
                                        font=("", 12), justify="right")
        self.clock_label.pack(side="right", padx=8)

    def _toggle_aot(self):
        on = bool(self.aot_var.get())
        self.attributes("-topmost", on)
        self.config_store.set("always_on_top", on)

    def _tick_clocks(self):
        local = datetime.now().strftime("%H:%M:%S")
        seoul = "--:--:--"
        if ZoneInfo is not None:
            try:
                seoul = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%H:%M:%S")
            except Exception:
                pass
        self.clock_label.configure(text=f"Local {local}   Séoul {seoul}")
        self.after(1000, self._tick_clocks)

    # ---- bannière fallback notif ----
    def _build_banner(self):
        self.banner = ctk.CTkLabel(self, text="", fg_color="#33271a",
                                   corner_radius=6, anchor="w")
        # masquée tant qu'il n'y a rien à afficher
        self._banner_after = None

    def show_banner(self, text: str, ms: int = 8000):
        def _apply():
            self.banner.configure(text="  " + text)
            self.banner.pack(fill="x", padx=6, pady=(4, 0))
            if self._banner_after:
                self.after_cancel(self._banner_after)
            self._banner_after = self.after(ms, self.banner.pack_forget)
        try:
            self.after(0, _apply)  # depuis n'importe quel thread
        except Exception:
            pass

    # ---- onglets ----
    def _build_tabs(self):
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=6, pady=6)

        for name in ("MF", "Temps", "Outils", "Coréen", "Système"):
            self.tabview.add(name)

        self.tabs = {
            "MF": MFTab(self.tabview.tab("MF"), self),
            "Temps": TempsTab(self.tabview.tab("Temps"), self),
            "Outils": OutilsTab(self.tabview.tab("Outils"), self),
            "Coréen": CoreenTab(self.tabview.tab("Coréen"), self),
            "Système": SystemeTab(self.tabview.tab("Système"), self),
        }
        for tab in self.tabs.values():
            tab.pack(fill="both", expand=True)

    # ---- boucle de rafraîchissement UI (lecture snapshot, zéro réseau) ----
    def _tick_ui(self):
        snap = self.poller.get_snapshot()
        for tab in self.tabs.values():
            try:
                tab.refresh(snap)
            except Exception:
                pass
        self.after(self.UI_REFRESH_MS, self._tick_ui)

    def _launch_korean_review(self):
        try:
            self.tabs["Coréen"].start_session()
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
