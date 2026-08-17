"""Onglet [Système] : accès mobile, rappels, démarrage auto, export, santé."""
import io
import os
from datetime import datetime
from tkinter import filedialog, messagebox

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

import customtkinter as ctk

try:
    from PIL import Image
except Exception:
    Image = None

from ..backend import autostart, db, media, rappels, webserver
from . import theme
from .base import ThemedScroll
from .theme import C
from .widgets import Indicator


class SystemeTab(ThemedScroll):
    def __init__(self, master, app):
        super().__init__(master, app)
        self._art_sig = None
        self._art_image = None
        self._build_mobile()
        self._build_rappels()
        self._build_demarrage()
        self._build_export()
        self._build()

    # ------------------------------------------------------ accès mobile
    def _build_mobile(self):
        f = self._section("Accès téléphone")
        self.srv_ind = Indicator(f, text="serveur mobile")
        self.srv_ind.set("grey", "serveur mobile")
        self.srv_ind.pack(fill="x", pady=(0, 4))
        self.srv_url = self.replier(ctk.CTkLabel(f, text="", anchor="w", justify="left",
                                    wraplength=300, font=theme.font("mono", 11),
                                    text_color=C["accent_lt2"]))
        self.srv_url.pack(fill="x", pady=(0, 6))

        ligne = ctk.CTkFrame(f, fg_color="transparent")
        ligne.pack(fill="x")
        ctk.CTkButton(ligne, text="Copier l'URL", command=self._copier_url,
                      font=theme.font("head", 11, "bold")).pack(
            side="left", expand=True, fill="x", padx=(0, 3))
        ctk.CTkButton(ligne, text="Régénérer le jeton",
                      command=self._regenerer_jeton, fg_color="#5a2740",
                      hover_color="#7a3b3b",
                      font=theme.font("head", 11, "bold")).pack(
            side="left", expand=True, fill="x", padx=(3, 0))

        ligne2 = ctk.CTkFrame(f, fg_color="transparent")
        ligne2.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(ligne2, text="Port", font=theme.font("body", 12),
                     text_color=C["muted"]).pack(side="left")
        self.e_port = ctk.CTkEntry(ligne2, width=64, justify="center",
                                   font=theme.font("mono", 12))
        self.e_port.insert(0, str(webserver.port()))
        self.e_port.pack(side="left", padx=6)
        ctk.CTkButton(ligne2, text="Redémarrer le serveur",
                      command=self._redemarrer_serveur,
                      font=theme.font("head", 11, "bold")).pack(
            side="left", expand=True, fill="x")

        # Encart pare-feu : affiché tant qu'aucune connexion n'est arrivée.
        self.encart_pare_feu = self.replier(ctk.CTkLabel(
            f, text="", anchor="w", justify="left", wraplength=300,
            font=theme.font("body", 10), text_color=C["orange"]))
        self.encart_pare_feu.pack(fill="x", pady=(8, 0))

    def _copier_url(self):
        etat = webserver.etat()
        if not etat["url"]:
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(etat["url"])
            self.app.show_banner("URL mobile copiée.")
        except Exception:
            pass

    def _regenerer_jeton(self):
        if not messagebox.askyesno(
                "Régénérer le jeton",
                "L'ancien lien cessera de fonctionner : il faudra rescanner "
                "le QR code depuis l'onglet Aujourd'hui.\n\nContinuer ?"):
            return
        webserver.regenerer_jeton()
        self.app.show_banner("Nouveau jeton — rescanne le QR code.")
        self.refresh(self.app.poller.get_snapshot())

    def _redemarrer_serveur(self):
        try:
            port = int(self.e_port.get().strip())
        except ValueError:
            return
        db.set_reglage("mobile.port", port)
        webserver.arreter()
        if webserver.demarrer():
            self.app.show_banner(f"Serveur mobile relancé sur le port {port}.")
        else:
            self.app.show_banner("Serveur mobile indisponible — voir l'encart "
                                 "pare-feu.")
        self.refresh(self.app.poller.get_snapshot())

    # ---------------------------------------------------------- rappels
    def _build_rappels(self):
        f = self._section("Rappels sport & coréen")
        self.replier(ctk.CTkLabel(f, text="Départ à l'ouverture du cockpit, puis toutes les "
                             "N heures tant que la journée n'est pas validée. "
                             "Chaque domaine s'éteint de son côté.",
                     anchor="w", justify="left", wraplength=300,
                     font=theme.font("body", 10),
                     text_color=C["dim"])).pack(fill="x", pady=(0, 6))

        self.var_rappels = ctk.BooleanVar(value=rappels.actif())
        ctk.CTkCheckBox(f, text="Rappels activés", variable=self.var_rappels,
                        checkbox_width=18, checkbox_height=18,
                        font=theme.font("body", 12),
                        command=lambda: db.set_reglage(
                            "rappels.actif", int(self.var_rappels.get()))
                        ).pack(anchor="w", pady=2)

        self.var_r_sport = ctk.BooleanVar(value=db.reglage_bool("rappels.sport", True))
        ctk.CTkCheckBox(f, text="Fil sport", variable=self.var_r_sport,
                        checkbox_width=18, checkbox_height=18,
                        font=theme.font("body", 12),
                        command=lambda: db.set_reglage(
                            "rappels.sport", int(self.var_r_sport.get()))
                        ).pack(anchor="w", pady=2)

        self.var_r_kr = ctk.BooleanVar(value=db.reglage_bool("rappels.coreen", True))
        ctk.CTkCheckBox(f, text="Fil coréen", variable=self.var_r_kr,
                        checkbox_width=18, checkbox_height=18,
                        font=theme.font("body", 12),
                        command=lambda: db.set_reglage(
                            "rappels.coreen", int(self.var_r_kr.get()))
                        ).pack(anchor="w", pady=2)

        ligne = ctk.CTkFrame(f, fg_color="transparent")
        ligne.pack(fill="x", pady=(6, 0))
        self.e_interv = self._petit_champ(ligne, "Toutes les",
                                          db.reglage_int("rappels.intervalle_h", 2), "h")
        self.e_debut = self._petit_champ(ligne, "de",
                                         db.reglage_int("rappels.debut_h", 9), "h")
        self.e_fin = self._petit_champ(ligne, "à",
                                       db.reglage_int("rappels.fin_h", 22), "h")
        ctk.CTkButton(f, text="Enregistrer les horaires",
                      command=self._sauver_rappels,
                      font=theme.font("head", 11, "bold")).pack(fill="x",
                                                                pady=(6, 0))

    def _petit_champ(self, parent, libelle, valeur, suffixe):
        ctk.CTkLabel(parent, text=libelle, font=theme.font("body", 11),
                     text_color=C["muted"]).pack(side="left", padx=(0, 3))
        e = ctk.CTkEntry(parent, width=38, justify="center",
                         font=theme.font("mono", 12))
        e.insert(0, str(valeur))
        e.pack(side="left")
        ctk.CTkLabel(parent, text=suffixe, font=theme.font("body", 11),
                     text_color=C["muted"]).pack(side="left", padx=(2, 8))
        return e

    def _sauver_rappels(self):
        for cle, champ in (("rappels.intervalle_h", self.e_interv),
                           ("rappels.debut_h", self.e_debut),
                           ("rappels.fin_h", self.e_fin)):
            try:
                db.set_reglage(cle, int(champ.get().strip()))
            except ValueError:
                pass
        self.app.show_banner("Horaires de rappel enregistrés.")

    # ------------------------------------------------------- démarrage
    def _build_demarrage(self):
        f = self._section("Démarrage")
        etat = autostart.etat()
        if not etat["supporte"]:
            self.replier(ctk.CTkLabel(f, text="Le démarrage automatique n'existe que sur "
                                 "Windows.", anchor="w", wraplength=300,
                         font=theme.font("body", 11),
                         text_color=C["dim"])).pack(fill="x")
            return
        self.var_auto = ctk.BooleanVar(value=etat["actif"])
        ctk.CTkCheckBox(f, text="Lancer au démarrage de Windows",
                        variable=self.var_auto, checkbox_width=18,
                        checkbox_height=18, font=theme.font("body", 12),
                        command=self._maj_autostart).pack(anchor="w", pady=2)
        self.var_reduit = ctk.BooleanVar(value=etat["reduit"])
        ctk.CTkCheckBox(f, text="Démarrer réduit (la 1re notif sert de réveil)",
                        variable=self.var_reduit, checkbox_width=18,
                        checkbox_height=18, font=theme.font("body", 12),
                        command=self._maj_autostart).pack(anchor="w", pady=2)
        self.lbl_auto = self.replier(ctk.CTkLabel(f, text="", anchor="w", justify="left",
                                     wraplength=300, font=theme.font("mono", 9),
                                     text_color=C["dim"]))
        self.lbl_auto.pack(fill="x", pady=(4, 0))
        self._maj_libelle_autostart()

    def _maj_autostart(self):
        if self.var_auto.get():
            autostart.activer(bool(self.var_reduit.get()))
        else:
            autostart.desactiver()
        self._maj_libelle_autostart()

    def _maj_libelle_autostart(self):
        etat = autostart.etat()
        self.lbl_auto.configure(
            text=etat["commande"] or "(aucune entrée dans HKCU\\…\\Run)")

    # ---------------------------------------------------------- export
    def _build_export(self):
        f = self._section("Export CSV")
        self.replier(ctk.CTkLabel(f, text="Une table par fichier. Pense aussi à sauvegarder "
                             "cockpit.db, qui contient tout.",
                     anchor="w", justify="left", wraplength=300,
                     font=theme.font("body", 10),
                     text_color=C["dim"])).pack(fill="x", pady=(0, 6))
        ligne = ctk.CTkFrame(f, fg_color="transparent")
        ligne.pack(fill="x")
        self.choix_table = ctk.CTkOptionMenu(
            ligne, values=list(db.TABLES_EXPORT), font=theme.font("body", 11),
            fg_color=C["inset"], button_color=C["accent"],
            button_hover_color=C["accent_dk"])
        self.choix_table.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(ligne, text="Exporter", width=80,
                      command=self._exporter_table,
                      font=theme.font("head", 11, "bold")).pack(side="left")
        ctk.CTkButton(f, text="Tout exporter dans un dossier",
                      command=self._exporter_tout,
                      font=theme.font("head", 11, "bold")).pack(fill="x",
                                                                pady=(6, 0))

    def _exporter_table(self):
        table = self.choix_table.get()
        chemin = filedialog.asksaveasfilename(
            defaultextension=".csv", initialfile=f"{table}.csv",
            filetypes=[("CSV", "*.csv")])
        if not chemin:
            return
        try:
            with open(chemin, "w", encoding="utf-8-sig", newline="") as fh:
                fh.write(db.export_csv(table))
            self.app.show_banner(f"Table « {table} » exportée.")
        except Exception as e:
            messagebox.showerror("Export", str(e))

    def _exporter_tout(self):
        dossier = filedialog.askdirectory()
        if not dossier:
            return
        erreurs = []
        for table in db.TABLES_EXPORT:
            try:
                with open(os.path.join(dossier, f"{table}.csv"), "w",
                          encoding="utf-8-sig", newline="") as fh:
                    fh.write(db.export_csv(table))
            except Exception as e:
                erreurs.append(f"{table} : {e}")
        if erreurs:
            messagebox.showerror("Export", "\n".join(erreurs[:6]))
        else:
            self.app.show_banner(f"{len(db.TABLES_EXPORT)} tables exportées.")

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
        self.media_title = self.replier(ctk.CTkLabel(txt, text="—", font=theme.font("body", 13, "bold"),
                                        anchor="w", wraplength=240, justify="left",
                                        text_color=C["text"]))
        self.media_title.pack(fill="x")
        self.media_artist = self.replier(ctk.CTkLabel(txt, text="", anchor="w", text_color=C["muted"],
                                         wraplength=240, justify="left",
                                         font=theme.font("body", 12)))
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
        self._refresh_mobile()

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

    def _refresh_mobile(self):
        etat = webserver.etat()
        if etat["actif"]:
            attente = etat["en_attente"]
            texte = "serveur mobile : en ligne"
            if attente:
                texte += f" · {attente} op. en attente"
            self.srv_ind.set("green" if not attente else "orange", texte)
            self.srv_url.configure(text=etat["url"] or "")
        else:
            self.srv_ind.set("red", "serveur mobile : hors ligne")
            self.srv_url.configure(text=etat["erreur"] or
                                   "démarrage impossible")

        # L'encart pare-feu ne sert que tant que rien n'est jamais arrivé :
        # dès la première visite du téléphone, il disparaît.
        if etat["actif"] and etat["jamais_visite"]:
            self.encart_pare_feu.configure(text=webserver.aide_pare_feu())
        elif not etat["actif"]:
            self.encart_pare_feu.configure(text=webserver.aide_pare_feu())
        else:
            self.encart_pare_feu.configure(text="")

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
