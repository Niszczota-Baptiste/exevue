"""Onglet [Système] : santé du site, média (SMTC), horloge Séoul."""
import io
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

import customtkinter as ctk

try:
    from PIL import Image
except Exception:
    Image = None

from ..backend import media
from .widgets import Indicator


class SystemeTab(ctk.CTkScrollableFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.cfg = app.config_store
        self._last_site_state = None
        self._art_sig = None
        self._art_image = None
        self._build()

    def _section(self, title):
        ctk.CTkLabel(self, text=title, font=("", 13, "bold"),
                     anchor="w").pack(fill="x", padx=4, pady=(10, 2))
        frame = ctk.CTkFrame(self)
        frame.pack(fill="x", padx=4, pady=2)
        return frame

    def _build(self):
        # --- santé site ---
        f = self._section("Santé du site")
        self.site_ind = Indicator(f, text="baptiste-niszczota.com : …")
        self.site_ind.pack(fill="x", padx=8, pady=(8, 2))
        self.site_detail = ctk.CTkLabel(f, text="", anchor="w", text_color="#888")
        self.site_detail.pack(fill="x", padx=8, pady=(0, 4))
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=(0, 8))
        self.site_url = ctk.CTkEntry(row)
        self.site_url.insert(0, self.cfg.get("site_health_url", ""))
        self.site_url.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(row, text="OK", width=40,
                      command=self._save_site).pack(side="left")

        # --- média SMTC ---
        f = self._section("Média en cours")
        body = ctk.CTkFrame(f, fg_color="transparent")
        body.pack(fill="x", padx=8, pady=8)
        self.art_label = ctk.CTkLabel(body, text="♪", width=64, height=64,
                                      fg_color="#2a2a2a", corner_radius=6)
        self.art_label.pack(side="left", padx=(0, 8))
        txt = ctk.CTkFrame(body, fg_color="transparent")
        txt.pack(side="left", fill="x", expand=True)
        self.media_title = ctk.CTkLabel(txt, text="—", font=("", 13, "bold"),
                                        anchor="w", wraplength=260, justify="left")
        self.media_title.pack(fill="x")
        self.media_artist = ctk.CTkLabel(txt, text="", anchor="w",
                                         text_color="#888", wraplength=260,
                                         justify="left")
        self.media_artist.pack(fill="x")
        ctrl = ctk.CTkFrame(f, fg_color="transparent")
        ctrl.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkButton(ctrl, text="⏮", width=60,
                      command=lambda: media.control("prev")).pack(side="left", expand=True, fill="x", padx=2)
        ctk.CTkButton(ctrl, text="⏯", width=60,
                      command=lambda: media.control("playpause")).pack(side="left", expand=True, fill="x", padx=2)
        ctk.CTkButton(ctrl, text="⏭", width=60,
                      command=lambda: media.control("next")).pack(side="left", expand=True, fill="x", padx=2)
        if not media.available():
            ctk.CTkLabel(f, text="(SMTC indisponible sur cette plateforme)",
                         text_color="#888").pack(fill="x", padx=8, pady=(0, 8))

        # --- horloge Séoul ---
        f = self._section("Horloges")
        self.clock_big = ctk.CTkLabel(f, text="", font=("", 14), justify="left",
                                      anchor="w")
        self.clock_big.pack(fill="x", padx=8, pady=8)
        self._tick_clock()

    def _save_site(self):
        self.cfg.set("site_health_url", self.site_url.get().strip())

    def _tick_clock(self):
        local = datetime.now()
        line = f"Local : {local.strftime('%H:%M:%S  —  %a %d %b')}"
        if ZoneInfo is not None:
            try:
                seoul = datetime.now(ZoneInfo("Asia/Seoul"))
                line += f"\nSéoul : {seoul.strftime('%H:%M:%S  —  %a %d %b')}"
            except Exception:
                pass
        self.clock_big.configure(text=line)
        self.after(1000, self._tick_clock)

    def refresh(self, snap):
        site = snap.get("site")
        if site is None:
            self.site_ind.set("grey", "Site : (URL non configurée)")
            self.site_detail.configure(text="")
        elif site.get("up"):
            ms = site.get("ms")
            self.site_ind.set("green", "Site : en ligne")
            self.site_detail.configure(
                text=f"HTTP {site.get('status')} · {ms:.0f} ms" if ms else "")
            self._last_site_state = "up"
        else:
            self.site_ind.set("red", "Site : hors ligne")
            self.site_detail.configure(text=f"statut {site.get('status')}")
            self._last_site_state = "down"

        med = snap.get("media")
        if not med or not med.get("title"):
            self.media_title.configure(text="— (rien en lecture)")
            self.media_artist.configure(text="")
            self._set_art(None)
        else:
            mark = "▶" if med.get("playing") else "⏸"
            self.media_title.configure(text=f"{mark} {med['title']}")
            self.media_artist.configure(
                text=" — ".join(x for x in (med.get("artist"),
                                            med.get("album")) if x))
            self._set_art(med.get("thumbnail"))

    def _set_art(self, data):
        sig = None if not data else hash(data)
        if sig == self._art_sig:
            return
        self._art_sig = sig
        if not data or Image is None:
            self.art_label.configure(image=None, text="♪")
            self._art_image = None
            return
        try:
            img = Image.open(io.BytesIO(data)).convert("RGB")
            self._art_image = ctk.CTkImage(light_image=img, dark_image=img,
                                           size=(64, 64))
            self.art_label.configure(image=self._art_image, text="")
        except Exception:
            self.art_label.configure(image=None, text="♪")
            self._art_image = None
