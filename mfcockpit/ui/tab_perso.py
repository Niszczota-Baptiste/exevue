"""Onglet [Perso] : tableau de bord configurable.

Tu coches les modules à afficher (⚙) ; ils sont repris des autres onglets sous
forme compacte. La sélection est persistée dans config.json (perso.modules).
Aucune charge réseau ici : tout lit le snapshot du poller / le tracker.
"""
import webbrowser
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

import customtkinter as ctk

from ..backend import stacks
from ..backend.tracker import fmt
from . import theme
from .base import ThemedScroll
from .theme import C
from .widgets import BarChart, Indicator

# (clé, libellé) — ordre d'affichage
MODULES = [
    ("presence", "Présences MF + Discord"),
    ("latence", "Latence Minefield"),
    ("today", "Temps du jour"),
    ("semaine", "7 derniers jours"),
    ("seoul", "Horloges (local + Séoul)"),
    ("stacks", "Calculateur de stacks"),
    ("liens", "Liens rapides"),
    ("sante", "Santé du site"),
    ("media", "Média en cours"),
]
DEFAULT_ON = {"presence", "latence", "today", "seoul"}


class PersoTab(ThemedScroll):
    def __init__(self, master, app):
        super().__init__(master, app)
        self._updaters = []
        self._settings_open = False
        self._build()

    def _enabled(self):
        saved = self.cfg.get("perso.modules", None)
        if not isinstance(saved, dict):
            saved = {k: (k in DEFAULT_ON) for k, _ in MODULES}
        return saved

    def _build(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(bar, text="MON COCKPIT", font=theme.font("head", 13, "bold"),
                     text_color=C["accent_lt"]).pack(side="left", padx=2)
        ctk.CTkButton(bar, text="⚙ Configurer", width=110, command=self._toggle_settings,
                      font=theme.font("head", 11, "bold")).pack(side="right")

        self.settings = ctk.CTkFrame(self, fg_color=C["card"],
                                     border_color=C["card_border"], border_width=1,
                                     corner_radius=11)
        self._build_settings()  # construit dedans mais ne l'affiche pas encore

        self.mods = ctk.CTkFrame(self, fg_color="transparent")
        self.mods.pack(fill="both", expand=True)
        self._render_modules()

    # ---- réglages ----
    def _build_settings(self):
        ctk.CTkLabel(self.settings, text="Modules affichés",
                     font=theme.font("head", 11, "bold"),
                     text_color=C["muted"]).pack(anchor="w", padx=14, pady=(10, 4))
        self._vars = {}
        enabled = self._enabled()
        for key, label in MODULES:
            var = ctk.BooleanVar(value=bool(enabled.get(key, key in DEFAULT_ON)))
            self._vars[key] = var
            ctk.CTkCheckBox(self.settings, text=label, variable=var,
                            command=self._save_settings, checkbox_width=18,
                            checkbox_height=18, font=theme.font("body", 12)).pack(
                anchor="w", padx=14, pady=2)
        ctk.CTkLabel(self.settings, text="", height=4).pack()

    def _toggle_settings(self):
        self._settings_open = not self._settings_open
        if self._settings_open:
            self.settings.pack(fill="x", pady=(0, 8), before=self.mods)
        else:
            self.settings.pack_forget()

    def _save_settings(self):
        self.cfg.set("perso.modules", {k: bool(v.get()) for k, v in self._vars.items()})
        self._render_modules()

    # ---- rendu des modules ----
    def _render_modules(self):
        for w in self.mods.winfo_children():
            w.destroy()
        self._updaters = []
        enabled = self._enabled()
        any_on = False
        for key, _ in MODULES:
            if enabled.get(key, key in DEFAULT_ON):
                any_on = True
                getattr(self, f"_m_{key}")(self.mods)
        if not any_on:
            ctk.CTkLabel(self.mods, text="Aucun module — clique sur ⚙ Configurer.",
                         text_color=C["dim"], font=theme.font("body", 12)).pack(
                pady=20)
        try:
            self.refresh(self.app.poller.get_snapshot())
        except Exception:
            pass

    def _row(self, parent, dot, name):
        ind = Indicator(parent, text=name)
        ind.set(dot, name)
        ind.pack(side="left")
        val = ctk.CTkLabel(parent, text="…", font=theme.font("mono", 13),
                           text_color=C["text_norm"])
        val.pack(side="right")
        return ind, val

    # ---- modules ----
    def _m_presence(self, parent):
        f = theme.section(parent, "Présences")
        r1 = ctk.CTkFrame(f, fg_color="transparent"); r1.pack(fill="x", pady=2)
        self._p_mf_i, self._p_mf = self._row(r1, "green", "Minefield")
        r2 = ctk.CTkFrame(f, fg_color="transparent"); r2.pack(fill="x", pady=2)
        self._p_dc_i, self._p_dc = self._row(r2, "blue", "Discord")

        def upd(snap):
            srv = snap.get("server")
            if srv:
                self._p_mf.configure(text=f"{srv['online']} / {srv['max']}",
                                     text_color=C["green"])
                self._p_mf_i.set("green", "Minefield")
            else:
                self._p_mf.configure(text="injoignable", text_color=C["red"])
                self._p_mf_i.set("red", "Minefield")
            dis = snap.get("discord")
            if dis is None:
                self._p_dc.configure(text="non configuré", text_color=C["dim"])
            elif "error" in dis:
                self._p_dc.configure(text=dis["error"], text_color=C["orange"])
            else:
                v = dis.get("voice") or []
                txt = f"{dis['online']} en ligne" + (f" · 🔊{len(v)}" if v else "")
                self._p_dc.configure(text=txt, text_color=C["accent_lt2"])
        self._updaters.append(upd)

    def _m_latence(self, parent):
        f = theme.section(parent, "Latence Minefield")
        big = ctk.CTkFrame(f, fg_color="transparent"); big.pack(fill="x")
        self._l_dot = Indicator(big, text=""); self._l_dot.set("grey", "")
        self._l_dot.pack(side="left")
        ctk.CTkLabel(big, text="PING", font=theme.font("head", 11, "bold"),
                     text_color=C["muted"]).pack(side="left", padx=(0, 8))
        self._l_val = ctk.CTkLabel(big, text="—", font=theme.font("mono", 24, "bold"),
                                   text_color=C["text"])
        self._l_val.pack(side="left")
        ctk.CTkLabel(big, text="ms", font=theme.font("mono", 13),
                     text_color=C["muted"]).pack(side="left", padx=(4, 0))
        self._l_stats = ctk.CTkLabel(f, text="", font=theme.font("mono", 11),
                                     text_color=C["dim"])
        self._l_stats.pack(anchor="w", pady=(4, 0))

        def upd(snap):
            lat = snap.get("latency") or {}
            cur = lat.get("current_ms")
            self._l_dot.set(lat.get("color", "grey"), "")
            self._l_val.configure(text=f"{cur:.0f}" if cur is not None else "—")
            mn, av, mx = lat.get("min"), lat.get("avg"), lat.get("max")
            if av is not None:
                self._l_stats.configure(
                    text=f"min {mn:.0f} · moy {av:.0f} · max {mx:.0f} · "
                         f"perte {lat.get('loss_pct', 0):.0f}%")
        self._updaters.append(upd)

    def _m_today(self, parent):
        f = theme.section(parent, "Temps du jour")
        self._t_state = self._kv(f, "État")
        self._t_today = self._kv(f, "Aujourd'hui (solo / multi)")
        self._t_streak = self._kv(f, "D'affilée", C["accent_lt2"])

        def upd(snap):
            t = self.app.tracker
            if t.playing:
                self._t_state.configure(text=f"EN COURS · {(t.mode or '').upper()}",
                                        text_color=C["green"])
            elif t.mode == "menu":
                self._t_state.configure(text="menu (non compté)",
                                        text_color=C["orange"])
            else:
                self._t_state.configure(text="à l'arrêt", text_color=C["dim"])
            solo_d, multi_d = t.today()
            self._t_today.configure(text=f"{fmt(solo_d)} / {fmt(multi_d)}")
            self._t_streak.configure(text=fmt(t.continuous_seconds))
        self._updaters.append(upd)

    def _m_semaine(self, parent):
        f = theme.section(parent, "7 derniers jours")
        wrap = ctk.CTkFrame(f, fg_color=C["page"], corner_radius=8,
                            border_color=C["card_border"], border_width=1)
        wrap.pack(fill="x")
        self._w_bars = BarChart(wrap, width=380, height=110, bg=C["page"])
        self._w_bars.pack(fill="x", padx=6, pady=6)

        def upd(snap):
            self._w_bars.set_data(self.app.tracker.last_n_days(7))
        self._updaters.append(upd)

    def _m_seoul(self, parent):
        f = theme.section(parent, "Horloges")
        self._c_local = self._kv(f, "Local", C["text"])
        self._c_seoul = self._kv(f, "Séoul", C["accent_lt2"])

        def upd(snap):
            self._c_local.configure(text=datetime.now().strftime("%H:%M:%S"))
            if ZoneInfo is not None:
                try:
                    self._c_seoul.configure(
                        text=datetime.now(ZoneInfo("Asia/Seoul")).strftime("%H:%M:%S"))
                    return
                except Exception:
                    pass
            self._c_seoul.configure(text="indispo (tzdata)")
        self._updaters.append(upd)

    def _m_stacks(self, parent):
        f = theme.section(parent, "Calculateur de stacks")
        row = ctk.CTkFrame(f, fg_color="transparent"); row.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(row, text="Nombre", font=theme.font("body", 13),
                     text_color=C["muted"]).pack(side="left")
        entry = ctk.CTkEntry(row, width=120, font=theme.font("mono", 14))
        entry.pack(side="left", padx=8)
        out = ctk.CTkLabel(f, text="=  …", anchor="w", justify="left",
                           font=theme.font("mono", 12), text_color=C["accent_lt2"])
        out.pack(fill="x")

        def calc(_=None):
            try:
                n = int(entry.get())
            except ValueError:
                out.configure(text="=  …"); return
            out.configure(text="=  " + stacks.describe(
                n, int(self.cfg.get("stack.size", 64)),
                int(self.cfg.get("stack.chest_slots", 27))))
        entry.bind("<KeyRelease>", calc)
        self._updaters.append(lambda snap: None)

    def _m_liens(self, parent):
        f = theme.section(parent, "Liens rapides")
        grid = ctk.CTkFrame(f, fg_color="transparent"); grid.pack(fill="x")
        links = (self.cfg.get("quick_links", []) or []) + (self.cfg.get("mf_links", []) or [])
        for i, link in enumerate(links):
            ctk.CTkButton(grid, text=link.get("label", "?"),
                          font=theme.font("head", 12, "bold"),
                          command=lambda u=link.get("url", ""): webbrowser.open(u)
                          ).grid(row=i // 2, column=i % 2,
                                 padx=(0 if i % 2 == 0 else 8, 0), pady=4, sticky="ew")
        grid.grid_columnconfigure((0, 1), weight=1, uniform="pl")
        self._updaters.append(lambda snap: None)

    def _m_sante(self, parent):
        f = theme.section(parent, "Santé du site")
        self._s_ind = Indicator(f, text="site")
        self._s_ind.set("grey", "site")
        self._s_ind.pack(fill="x")
        self._s_detail = ctk.CTkLabel(f, text="", font=theme.font("mono", 11),
                                      text_color=C["dim"])
        self._s_detail.pack(anchor="w", padx=(25, 0), pady=(2, 0))

        def upd(snap):
            site = snap.get("site")
            if site is None:
                self._s_ind.set("grey", "site : URL non configurée")
                self._s_detail.configure(text="")
            elif site.get("up"):
                ms = site.get("ms")
                self._s_ind.set("green", "site : en ligne")
                self._s_detail.configure(
                    text=f"HTTP {site.get('status')} · {ms:.0f} ms" if ms else "")
            else:
                self._s_ind.set("red", "site : hors ligne")
                self._s_detail.configure(text=f"statut {site.get('status')}")
        self._updaters.append(upd)

    def _m_media(self, parent):
        from ..backend import media
        f = theme.section(parent, "Média en cours")
        self._md_title = ctk.CTkLabel(f, text="—", font=theme.font("body", 13, "bold"),
                                      anchor="w", wraplength=300, justify="left",
                                      text_color=C["text"])
        self._md_title.pack(fill="x")
        self._md_artist = ctk.CTkLabel(f, text="", anchor="w", text_color=C["muted"],
                                       font=theme.font("body", 12))
        self._md_artist.pack(fill="x", pady=(0, 6))
        ctrl = ctk.CTkFrame(f, fg_color="transparent"); ctrl.pack(fill="x")
        for sym, act in (("⏮", "prev"), ("⏯", "playpause"), ("⏭", "next")):
            ctk.CTkButton(ctrl, text=sym, font=theme.font("body", 14),
                          command=lambda a=act: media.control(a)).pack(
                side="left", expand=True, fill="x", padx=2)

        def upd(snap):
            med = snap.get("media")
            if not med or not med.get("title"):
                self._md_title.configure(text="— rien en lecture")
                self._md_artist.configure(text="")
            else:
                mark = "▶" if med.get("playing") else "⏸"
                self._md_title.configure(text=f"{mark}  {med['title']}")
                self._md_artist.configure(text=med.get("artist", ""))
        self._updaters.append(upd)

    # ---- util ----
    def _kv(self, parent, key, value_color=None):
        row = ctk.CTkFrame(parent, fg_color="transparent"); row.pack(fill="x", pady=2)
        ctk.CTkLabel(row, text=key, font=theme.font("body", 13),
                     text_color=C["muted"]).pack(side="left")
        val = ctk.CTkLabel(row, text="—", font=theme.font("mono", 13),
                           text_color=value_color or C["text_norm"])
        val.pack(side="right")
        return val

    def refresh(self, snap):
        for u in self._updaters:
            try:
                u(snap)
            except Exception:
                pass
