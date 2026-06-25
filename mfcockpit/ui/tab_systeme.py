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
from . import theme
from .base import ThemedScroll
from .theme import C
from .widgets import Indicator


class SystemeTab(ThemedScroll):
    def __init__(self, master, app):
        super().__init__(master, app)
        self._art_sig = None
        self._art_image = None
        self._build()

    def _build(self):
        # --- santé site ---
        f = self._section("Santé du site")
        self.site_ind = Indicator(f, text="baptiste-niszczota.com")
        self.site_ind.set("grey", "baptiste-niszczota.com")
        self.site_ind.pack(fill="x", pady=(0, 2))
        self.site_detail = ctk.CTkLabel(f, text="", anchor="w", text_color=C["dim"],
                                        font=theme.font("mono", 11))
        self.site_detail.pack(fill="x", padx=(25, 0), pady=(0, 6))
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x")
        self.site_url = ctk.CTkEntry(row, font=theme.font("body", 12))
        self.site_url.insert(0, self.cfg.get("site_health_url", ""))
        self.site_url.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(row, text="OK", width=42, command=self._save_site,
                      fg_color=C["accent"], hover_color=C["accent_dk"],
                      text_color="#f6f2ff", border_width=0,
                      font=theme.font("head", 11, "bold")).pack(side="left")

        # --- média ---
        f = self._section("Média en cours")
        body = ctk.CTkFrame(f, fg_color="transparent")
        body.pack(fill="x", pady=(0, 8))
        self.art_label = ctk.CTkLabel(body, text="♪", width=66, height=66,
                                      fg_color=C["inset"], corner_radius=8,
                                      font=theme.font("body", 22),
                                      text_color=C["accent_lt"])
        self.art_label.pack(side="left", padx=(0, 10))
        txt = ctk.CTkFrame(body, fg_color="transparent")
        txt.pack(side="left", fill="x", expand=True)
        self.media_title = ctk.CTkLabel(txt, text="—", font=theme.font("body", 13, "bold"),
                                        anchor="w", wraplength=240, justify="left",
                                        text_color=C["text"])
        self.media_title.pack(fill="x")
        self.media_artist = ctk.CTkLabel(txt, text="", anchor="w", text_color=C["muted"],
                                         wraplength=240, justify="left",
                                         font=theme.font("body", 12))
        self.media_artist.pack(fill="x")
        ctrl = ctk.CTkFrame(f, fg_color="transparent")
        ctrl.pack(fill="x")
        for sym, act in (("⏮", "prev"), ("⏯", "playpause"), ("⏭", "next")):
            ctk.CTkButton(ctrl, text=sym, font=theme.font("body", 15),
                          command=lambda a=act: media.control(a)).pack(
                side="left", expand=True, fill="x", padx=2)
        if not media.available():
            ctk.CTkLabel(f, text="SMTC indisponible sur cette plateforme",
                         text_color=C["dim"], font=theme.font("body", 11)).pack(
                fill="x", pady=(6, 0))

        # --- horloges ---
        f = self._section("Horloges")
        self.clock_local = self._clock_box(f, "LOCAL", C["dim"])
        self.clock_seoul = self._clock_box(f, "SÉOUL", C["accent_lt"])
        self._tick_clock()

    def _clock_box(self, parent, caption, cap_color):
        box = ctk.CTkFrame(parent, fg_color=C["inset"], corner_radius=8,
                           border_color=C["inset_border"], border_width=1)
        box.pack(fill="x", pady=3)
        ctk.CTkLabel(box, text=caption, font=theme.font("head", 9, "bold"),
                     text_color=cap_color).pack(side="left", padx=(12, 0), pady=8)
        val = ctk.CTkLabel(box, text="--:--:--", font=theme.font("mono", 16),
                           text_color=C["text"])
        val.pack(side="right", padx=12)
        return val

    def _save_site(self):
        self.cfg.set("site_health_url", self.site_url.get().strip())

    def _tick_clock(self):
        self.clock_local.configure(
            text=datetime.now().strftime("%H:%M:%S  ·  %a %d %b"))
        if ZoneInfo is not None:
            try:
                self.clock_seoul.configure(
                    text=datetime.now(ZoneInfo("Asia/Seoul")).strftime(
                        "%H:%M:%S  ·  %a %d %b"))
            except Exception:
                pass
        self.after(1000, self._tick_clock)

    def refresh(self, snap):
        site = snap.get("site")
        if site is None:
            self.site_ind.set("grey", "site : URL non configurée")
            self.site_detail.configure(text="")
        elif site.get("up"):
            ms = site.get("ms")
            self.site_ind.set("green", "site : en ligne")
            self.site_detail.configure(
                text=f"HTTP {site.get('status')} · {ms:.0f} ms" if ms else "")
        else:
            self.site_ind.set("red", "site : hors ligne")
            self.site_detail.configure(text=f"statut {site.get('status')}")

        med = snap.get("media")
        if not med or not med.get("title"):
            self.media_title.configure(text="— rien en lecture")
            self.media_artist.configure(text="")
            self._set_art(None)
        else:
            mark = "▶" if med.get("playing") else "⏸"
            self.media_title.configure(text=f"{mark}  {med['title']}")
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
                                           size=(66, 66))
            self.art_label.configure(image=self._art_image, text="")
        except Exception:
            self.art_label.configure(image=None, text="♪")
            self._art_image = None
