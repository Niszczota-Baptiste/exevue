"""Onglet [MF] : présences, latence, alerte seuil, histo, liens."""
import webbrowser

import customtkinter as ctk

from ..backend import history
from .widgets import Indicator, Sparkline


class MFTab(ctk.CTkScrollableFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.cfg = app.config_store
        self._build()

    def _section(self, title):
        lbl = ctk.CTkLabel(self, text=title, font=("", 13, "bold"), anchor="w")
        lbl.pack(fill="x", padx=4, pady=(10, 2))
        frame = ctk.CTkFrame(self)
        frame.pack(fill="x", padx=4, pady=2)
        return frame

    def _build(self):
        # 1) Présences
        f = self._section("Présences")
        self.mf_presence = Indicator(f, text="Minefield : …")
        self.mf_presence.pack(fill="x", padx=8, pady=(8, 2))
        self.mf_players = ctk.CTkLabel(f, text="", anchor="w",
                                       justify="left", wraplength=380)
        self.mf_players.pack(fill="x", padx=8, pady=(0, 4))
        self.dc_presence = Indicator(f, text="Discord : …")
        self.dc_presence.pack(fill="x", padx=8, pady=2)
        self.dc_voice = ctk.CTkLabel(f, text="", anchor="w",
                                     justify="left", wraplength=380)
        self.dc_voice.pack(fill="x", padx=8, pady=(0, 8))

        # 2) Latence
        f = self._section("Latence Minefield")
        self.lat_ind = Indicator(f, text="Ping : …")
        self.lat_ind.pack(fill="x", padx=8, pady=(8, 2))
        self.lat_stats = ctk.CTkLabel(f, text="", anchor="w", justify="left")
        self.lat_stats.pack(fill="x", padx=8, pady=(0, 8))

        # 3) Alerte seuil
        f = self._section("Alerte seuil joueurs")
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=6)
        self.alert_var = ctk.BooleanVar(
            value=bool(self.cfg.get("player_alert.enabled", True)))
        ctk.CTkSwitch(row, text="Activée", variable=self.alert_var,
                      command=self._save_alert, width=80).pack(side="left")
        ctk.CTkLabel(row, text="bas").pack(side="left", padx=(10, 2))
        self.low_entry = ctk.CTkEntry(row, width=46)
        self.low_entry.insert(0, str(self.cfg.get("player_alert.low", 2)))
        self.low_entry.pack(side="left")
        ctk.CTkLabel(row, text="haut").pack(side="left", padx=(10, 2))
        self.high_entry = ctk.CTkEntry(row, width=46)
        self.high_entry.insert(0, str(self.cfg.get("player_alert.high", 30)))
        self.high_entry.pack(side="left")
        ctk.CTkButton(row, text="OK", width=40,
                      command=self._save_alert).pack(side="left", padx=8)

        # 4) Histo fréquentation
        f = self._section("Fréquentation (dernières heures)")
        self.spark = Sparkline(f, width=380, height=60)
        self.spark.pack(fill="x", padx=8, pady=8)

        # 5) Liens MF
        f = self._section("Liens Minefield")
        self.links_frame = ctk.CTkFrame(f, fg_color="transparent")
        self.links_frame.pack(fill="x", padx=8, pady=8)
        self._build_links()

    def _build_links(self):
        for w in self.links_frame.winfo_children():
            w.destroy()
        links = self.cfg.get("mf_links", []) or []
        for i, link in enumerate(links):
            ctk.CTkButton(
                self.links_frame, text=link.get("label", "?"), width=110,
                command=lambda u=link.get("url", ""): webbrowser.open(u)
            ).grid(row=i // 2, column=i % 2, padx=4, pady=4, sticky="ew")
        self.links_frame.grid_columnconfigure((0, 1), weight=1)

    def _save_alert(self):
        self.cfg.set("player_alert.enabled", bool(self.alert_var.get()))
        for key, entry in (("player_alert.low", self.low_entry),
                           ("player_alert.high", self.high_entry)):
            try:
                self.cfg.set(key, int(entry.get()))
            except ValueError:
                pass

    # ---- rafraîchissement ----
    def refresh(self, snap):
        srv = snap.get("server")
        if srv:
            self.mf_presence.set("green",
                                 f"Minefield : {srv['online']}/{srv['max']} en ligne")
            names = srv.get("sample") or []
            self.mf_players.configure(
                text=("Joueurs : " + ", ".join(names)) if names else
                "(pseudos non exposés)")
        else:
            self.mf_presence.set("red", "Minefield : injoignable")
            self.mf_players.configure(text="")

        dis = snap.get("discord")
        if dis is None:
            self.dc_presence.set("grey", "Discord : (guild id non configuré)")
            self.dc_voice.configure(text="")
        elif "error" in dis:
            self.dc_presence.set("orange", f"Discord : {dis['error']}")
            self.dc_voice.configure(text="")
        else:
            self.dc_presence.set("green", f"Discord : {dis['online']} en ligne")
            voice = dis.get("voice") or []
            self.dc_voice.configure(
                text=("Vocal : " + ", ".join(voice)) if voice else "Vocal : —")

        lat = snap.get("latency") or {}
        cur = lat.get("current_ms")
        if cur is None:
            self.lat_ind.set(lat.get("color", "red"), "Ping : perte")
        else:
            self.lat_ind.set(lat.get("color", "grey"), f"Ping : {cur:.0f} ms")
        mn, av, mx = lat.get("min"), lat.get("avg"), lat.get("max")
        if av is not None:
            self.lat_stats.configure(
                text=f"min {mn:.0f} / moy {av:.0f} / max {mx:.0f} ms"
                     f"   perte {lat.get('loss_pct', 0):.0f}%")
        else:
            self.lat_stats.configure(text="(mesures en cours…)")

        pts = history.recent_points(hours=12.0)
        self.spark.set_series([p[1] for p in pts])
