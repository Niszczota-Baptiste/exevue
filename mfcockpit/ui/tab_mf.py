"""Onglet [MF] : présences, latence, alerte seuil, histo, liens."""
import webbrowser

import customtkinter as ctk

from ..backend import history
from . import theme
from .base import ThemedScroll
from .theme import C
from .widgets import Indicator, Sparkline


class MFTab(ThemedScroll):
    def __init__(self, master, app):
        super().__init__(master, app)
        self._build()

    def _presence_row(self, parent, dot_color, name):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)
        left = Indicator(row, text=name)
        left.set(dot_color, name)
        left.pack(side="left")
        val = ctk.CTkLabel(row, text="…", font=theme.font("mono", 13),
                           text_color=C["text_norm"])
        val.pack(side="right")
        return val

    def _detail_row(self, parent):
        lbl = ctk.CTkLabel(parent, text="", anchor="w", justify="left",
                           font=theme.font("body", 12), text_color=C["muted"],
                           wraplength=300)
        lbl.pack(fill="x", padx=(25, 0))
        return lbl

    def _build(self):
        # 1) Présences
        f = self._section("Présences")
        self.mf_val = self._presence_row(f, "green", "Minefield")
        self.mf_players = self._detail_row(f)
        self.dc_val = self._presence_row(f, "blue", "Discord")
        self.dc_voice = self._detail_row(f)

        # 2) Latence
        f = self._section("Latence Minefield")
        big = ctk.CTkFrame(f, fg_color="transparent")
        big.pack(fill="x", pady=(0, 10))
        self.lat_dot = Indicator(big, text="")
        self.lat_dot.set("grey", "")
        self.lat_dot.pack(side="left")
        ctk.CTkLabel(big, text="PING", font=theme.font("head", 11, "bold"),
                     text_color=C["muted"]).pack(side="left", padx=(0, 8))
        self.lat_value = ctk.CTkLabel(big, text="—", font=theme.font("mono", 26, "bold"),
                                      text_color=C["text"])
        self.lat_value.pack(side="left")
        ctk.CTkLabel(big, text="ms", font=theme.font("mono", 13),
                     text_color=C["muted"]).pack(side="left", padx=(4, 0),
                                                 anchor="s", pady=(0, 4))

        boxes = ctk.CTkFrame(f, fg_color="transparent")
        boxes.pack(fill="x")
        self.lat_min = self._stat(boxes, "min", 0)
        self.lat_avg = self._stat(boxes, "moy", 1)
        self.lat_max = self._stat(boxes, "max", 2)
        self.lat_loss = self._stat(boxes, "perte", 3, color=C["pink"])
        for i in range(4):
            boxes.grid_columnconfigure(i, weight=1, uniform="lat")

        # 3) Alerte seuil
        f = self._section("Alerte seuil joueurs")
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x")
        self.alert_var = ctk.BooleanVar(
            value=bool(self.cfg.get("player_alert.enabled", True)))
        ctk.CTkSwitch(row, text="Activée", variable=self.alert_var,
                      command=self._save_alert, width=80,
                      font=theme.font("body", 12)).pack(side="left")
        ctk.CTkButton(row, text="OK", width=42, command=self._save_alert,
                      fg_color=C["accent"], hover_color=C["accent_dk"],
                      text_color="#f6f2ff", border_width=0,
                      font=theme.font("head", 11, "bold")).pack(side="right")
        self.high_entry = self._mini_entry(row, "haut",
                                           self.cfg.get("player_alert.high", 30))
        self.low_entry = self._mini_entry(row, "bas",
                                          self.cfg.get("player_alert.low", 2))

        # 4) Fréquentation
        f = self._section("Fréquentation", "dernières heures")
        wrap = ctk.CTkFrame(f, fg_color=C["page"], corner_radius=8,
                            border_color=C["card_border"], border_width=1)
        wrap.pack(fill="x")
        self.spark = Sparkline(wrap, width=380, height=66, bg=C["page"])
        self.spark.pack(fill="x", padx=6, pady=6)

        # 5) Liens
        f = self._section("Liens Minefield")
        self.links_frame = ctk.CTkFrame(f, fg_color="transparent")
        self.links_frame.pack(fill="x")
        self._build_links()

    def _stat(self, parent, label, col, color=None):
        box, val = theme.stat_box(parent, label, "—", color)
        box.grid(row=0, column=col, padx=(0 if col == 0 else 6, 0), sticky="ew")
        return val

    def _mini_entry(self, parent, label, value):
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(side="right", padx=(10, 0))
        ctk.CTkLabel(wrap, text=label.upper(), font=theme.font("head", 10, "bold"),
                     text_color=C["muted"]).pack(side="left", padx=(0, 4))
        e = ctk.CTkEntry(wrap, width=46, justify="center",
                         font=theme.font("mono", 13))
        e.insert(0, str(value))
        e.pack(side="left")
        return e

    def _build_links(self):
        for w in self.links_frame.winfo_children():
            w.destroy()
        links = self.cfg.get("mf_links", []) or []
        for i, link in enumerate(links):
            ctk.CTkButton(
                self.links_frame, text=link.get("label", "?"),
                font=theme.font("head", 12, "bold"),
                command=lambda u=link.get("url", ""): webbrowser.open(u)
            ).grid(row=i // 2, column=i % 2, padx=(0 if i % 2 == 0 else 8, 0),
                   pady=4, sticky="ew")
        self.links_frame.grid_columnconfigure((0, 1), weight=1, uniform="lnk")

    def _save_alert(self):
        self.cfg.set("player_alert.enabled", bool(self.alert_var.get()))
        for key, entry in (("player_alert.low", self.low_entry),
                           ("player_alert.high", self.high_entry)):
            try:
                self.cfg.set(key, int(entry.get()))
            except ValueError:
                pass

    # ---- refresh ----
    def refresh(self, snap):
        srv = snap.get("server")
        if srv:
            self.mf_val.configure(text=f"{srv['online']} / {srv['max']}",
                                  text_color=C["green"])
            names = srv.get("sample") or []
            self.mf_players.configure(
                text=", ".join(names) if names else "pseudos non exposés")
        else:
            self.mf_val.configure(text="injoignable", text_color=C["red"])
            self.mf_players.configure(text="")

        dis = snap.get("discord")
        if dis is None:
            self.dc_val.configure(text="non configuré", text_color=C["dim"])
            self.dc_voice.configure(text="")
        elif "error" in dis:
            self.dc_val.configure(text=dis["error"], text_color=C["orange"])
            self.dc_voice.configure(text="")
        else:
            self.dc_val.configure(text=f"{dis['online']} en ligne",
                                  text_color=C["accent_lt2"])
            voice = dis.get("voice") or []
            self.dc_voice.configure(text=("🔊 " + ", ".join(voice)) if voice else "")

        lat = snap.get("latency") or {}
        cur = lat.get("current_ms")
        self.lat_dot.set(lat.get("color", "grey"), "")
        self.lat_value.configure(text=f"{cur:.0f}" if cur is not None else "—")
        mn, av, mx = lat.get("min"), lat.get("avg"), lat.get("max")
        self.lat_min.configure(text=f"{mn:.0f}" if mn is not None else "—")
        self.lat_avg.configure(text=f"{av:.0f}" if av is not None else "—")
        self.lat_max.configure(text=f"{mx:.0f}" if mx is not None else "—")
        self.lat_loss.configure(text=f"{lat.get('loss_pct', 0):.0f}%")

        pts = history.recent_points(hours=12.0)
        self.spark.set_series([p[1] for p in pts])
