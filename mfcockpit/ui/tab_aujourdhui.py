"""Onglet [Aujourd'hui] — ce qu'il y a à faire, et de quoi tout cocher.

C'est l'onglet d'accueil du cockpit (réglage `ui.onglet_demarrage`). Il lit
`backend/jour.etat_jour()` — la **même** fonction que celle servie au téléphone,
donc les deux écrans ne peuvent pas diverger.

Perf : l'état complet coûte quelques dizaines de millisecondes de SQL. On ne le
recalcule donc pas à chaque tick d'une seconde mais toutes les `RECALC_S`
secondes — et immédiatement après une action de l'utilisateur, pour que cocher
reste instantané. Quand l'onglet n'est pas visible, `refresh()` n'est pas appelé
du tout : rien ne tourne.
"""
import time
import tkinter as tk
import webbrowser
from tkinter import messagebox

import customtkinter as ctk

from ..backend import db, jour, qr, webserver
from . import theme
from .base import ThemedScroll
from .theme import C

RECALC_S = 5.0        # rafraîchissement de l'état hors action utilisateur

COULEUR_ETAT = {"fait": C["green"], "partiel": C["orange"], "manque": C["red"],
                "avenir": C["grey"]}

# Les notes « par côté / par jambe / par bras » reviennent sur la moitié des
# lignes : abrégées, elles tiennent dans la ligne au lieu de la faire déborder.
ABREGES = ((" par côté", "/côté"), ("par côté", "/côté"),
           ("par jambe", "/jambe"), ("par bras", "/bras"))


def _ligne_exo(exo: dict, largeur_nom=22) -> tuple:
    """(nom à cocher, cible à droite) pour un exercice de la journée.

    Le nom seul à gauche, l'objectif chiffré à droite en mono : c'est ce qu'on
    lit d'un coup d'œil, et ça ne déborde jamais de la ligne.
    """
    note = exo.get("note") or ""
    suffixe = ""
    for motif, court in ABREGES:
        if motif in note:
            suffixe = " " + court
            break
    nom = exo["nom"]
    if len(nom) > largeur_nom:
        nom = nom[:largeur_nom - 1].rstrip() + "…"

    detail = f"{exo['cible']}{suffixe}"
    if exo.get("charge_proposee"):
        detail += f" · {exo['charge_proposee']:g} kg"
    return nom, detail


class AujourdhuiTab(ThemedScroll):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.etat = None
        self._dernier_calcul = 0.0
        self._jour_detail = None
        self._qr_signature = None
        self._build()

    # ------------------------------------------------------------ montage
    def _build(self):
        # --- bandeau date + streaks ---
        bandeau = ctk.CTkFrame(self, fg_color="transparent")
        bandeau.pack(fill="x", pady=(0, 8))
        self.lbl_date = ctk.CTkLabel(bandeau, text="—", anchor="w",
                                     font=theme.font("head", 17, "bold"),
                                     text_color=C["text"])
        self.lbl_date.pack(fill="x")
        self.lbl_semaine = ctk.CTkLabel(bandeau, text="", anchor="w",
                                        font=theme.font("body", 11),
                                        text_color=C["muted"])
        self.lbl_semaine.pack(fill="x")

        streaks = ctk.CTkFrame(self, fg_color="transparent")
        streaks.pack(fill="x", pady=(0, 8))
        self.streak_sport = self._case_streak(streaks, "SPORT")
        self.streak_kr = self._case_streak(streaks, "CORÉEN")
        streaks.grid_columnconfigure((0, 1), weight=1, uniform="s")

        self.conseils = ctk.CTkFrame(self, fg_color="transparent")
        self.conseils.pack(fill="x")

        # --- séance du jour ---
        self.f_seance = theme.section(self, "Séance du jour")
        self.lbl_seance = self.replier(ctk.CTkLabel(self.f_seance, text="—", anchor="w",
                                       justify="left", wraplength=300,
                                       font=theme.font("body", 13, "bold"),
                                       text_color=C["text"]))
        self.lbl_seance.pack(fill="x")
        self.lbl_seance_meta = self.replier(ctk.CTkLabel(self.f_seance, text="", anchor="w",
                                            justify="left", wraplength=300,
                                            font=theme.font("body", 11),
                                            text_color=C["muted"]))
        self.lbl_seance_meta.pack(fill="x", pady=(0, 6))
        self.liste_seance = ctk.CTkFrame(self.f_seance, fg_color="transparent")
        self.liste_seance.pack(fill="x")
        boutons = ctk.CTkFrame(self.f_seance, fg_color="transparent")
        boutons.pack(fill="x", pady=(8, 0))
        self.btn_demarrer = theme.primary_button(boutons, "▶ Démarrer",
                                                 self._demarrer)
        self.btn_demarrer.pack(side="left", expand=True, fill="x", padx=(0, 4))
        ctk.CTkButton(boutons, text="Marquer manquée", command=self._manquee,
                      fg_color="#5a2740", hover_color="#7a3b3b",
                      font=theme.font("head", 11, "bold")).pack(
            side="left", expand=True, fill="x", padx=(4, 0))

        # --- bloc core ---
        self.f_core = theme.section(self, "Bloc core du soir")
        self.lbl_core = ctk.CTkLabel(self.f_core, text="—", anchor="w",
                                     font=theme.font("body", 13, "bold"),
                                     text_color=C["text"])
        self.lbl_core.pack(fill="x")
        self.liste_core = ctk.CTkFrame(self.f_core, fg_color="transparent")
        self.liste_core.pack(fill="x")

        # --- coréen ---
        self.f_kr = theme.section(self, "Coréen")
        self.lbl_kr = self.replier(ctk.CTkLabel(self.f_kr, text="—", anchor="w",
                                   justify="left", wraplength=300,
                                   font=theme.font("body", 13, "bold"),
                                   text_color=C["text"]))
        self.lbl_kr.pack(fill="x")
        self.lbl_kr_meta = ctk.CTkLabel(self.f_kr, text="", anchor="w",
                                        font=theme.font("mono", 11),
                                        text_color=C["accent_lt2"])
        self.lbl_kr_meta.pack(fill="x", pady=(0, 4))
        self.liste_kr = ctk.CTkFrame(self.f_kr, fg_color="transparent")
        self.liste_kr.pack(fill="x")
        theme.primary_button(self.f_kr, "▶ Réviser",
                             self._reviser).pack(fill="x", pady=(8, 0))

        # --- cardio (masqué les jours sans) ---
        self.f_cardio = theme.section(self, "Cardio")
        self.carte_cardio = self.f_cardio.master
        self.lbl_cardio = self.replier(ctk.CTkLabel(self.f_cardio, text="—", anchor="w",
                                       justify="left", wraplength=300,
                                       font=theme.font("body", 12),
                                       text_color=C["text_norm"]))
        self.lbl_cardio.pack(fill="x", pady=(0, 6))
        saisie = ctk.CTkFrame(self.f_cardio, fg_color="transparent")
        saisie.pack(fill="x")
        self.e_km = ctk.CTkEntry(saisie, width=64, placeholder_text="km",
                                 font=theme.font("mono", 12))
        self.e_km.pack(side="left", padx=(0, 4))
        self.e_min = ctk.CTkEntry(saisie, width=64, placeholder_text="min",
                                  font=theme.font("mono", 12))
        self.e_min.pack(side="left", padx=(0, 4))
        ctk.CTkButton(saisie, text="Enregistrer", command=self._log_cardio,
                      font=theme.font("head", 11, "bold")).pack(
            side="left", expand=True, fill="x")
        self.liste_cardio = ctk.CTkFrame(self.f_cardio, fg_color="transparent")
        self.liste_cardio.pack(fill="x", pady=(6, 0))

        # --- foot en salle ---
        f = theme.section(self, "Foot en salle")
        ligne = ctk.CTkFrame(f, fg_color="transparent")
        ligne.pack(fill="x")
        ctk.CTkLabel(ligne, text="Durée", font=theme.font("body", 12),
                     text_color=C["muted"]).pack(side="left")
        self.e_foot = ctk.CTkEntry(ligne, width=52, placeholder_text="min",
                                   font=theme.font("mono", 12))
        self.e_foot.pack(side="left", padx=6)
        ctk.CTkLabel(ligne, text="Ressenti", font=theme.font("body", 12),
                     text_color=C["muted"]).pack(side="left")
        self.e_foot_res = ctk.CTkEntry(ligne, width=42, placeholder_text="/10",
                                       font=theme.font("mono", 12))
        self.e_foot_res.pack(side="left", padx=6)
        ctk.CTkButton(ligne, text="+", width=34, command=self._log_foot,
                      fg_color=C["accent"], hover_color=C["accent_dk"],
                      text_color="#f6f2ff", border_width=0,
                      font=theme.font("head", 13, "bold")).pack(side="left")

        # --- bande semaine ---
        f = theme.section(self, "Semaine")
        self.cv_semaine = tk.Canvas(f, height=88, highlightthickness=0,
                                    bg=C["card"])
        self.cv_semaine.pack(fill="x")
        self.cv_semaine.bind("<Button-1>", self._clic_semaine)
        self.lbl_detail = self.replier(ctk.CTkLabel(f, text="", anchor="w", justify="left",
                                       wraplength=300,
                                       font=theme.font("body", 11),
                                       text_color=C["muted"]))
        self.lbl_detail.pack(fill="x", pady=(6, 0))

        # --- accès téléphone ---
        f = theme.section(self, "Accès téléphone")
        corps = ctk.CTkFrame(f, fg_color="transparent")
        corps.pack(fill="x")
        self.cv_qr = tk.Canvas(corps, width=132, height=132,
                               highlightthickness=0, bg=C["card"])
        self.cv_qr.pack(side="left", padx=(0, 10))
        droite = ctk.CTkFrame(corps, fg_color="transparent")
        droite.pack(side="left", fill="both", expand=True)
        self.lbl_srv = self.replier(ctk.CTkLabel(droite, text="—", anchor="w",
                                    justify="left", wraplength=180,
                                    font=theme.font("body", 12, "bold"),
                                    text_color=C["text"]))
        self.lbl_srv.pack(fill="x")
        self.lbl_url = self.replier(ctk.CTkLabel(droite, text="", anchor="w",
                                    justify="left", wraplength=180,
                                    font=theme.font("mono", 10),
                                    text_color=C["accent_lt2"]))
        self.lbl_url.pack(fill="x", pady=(2, 6))
        ctk.CTkButton(droite, text="Copier l'URL", command=self._copier_url,
                      font=theme.font("head", 11, "bold")).pack(fill="x")
        ctk.CTkButton(droite, text="Ouvrir ici", command=self._ouvrir_url,
                      font=theme.font("head", 11, "bold")).pack(fill="x",
                                                                pady=(4, 0))

    def _case_streak(self, parent, titre):
        box = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=11,
                           border_color=C["card_border"], border_width=1)
        box.grid(row=0, column=0 if titre == "SPORT" else 1, sticky="ew",
                 padx=(0, 4) if titre == "SPORT" else (4, 0))
        ctk.CTkLabel(box, text=titre, font=theme.font("head", 9, "bold"),
                     text_color=C["accent_lt"]).pack(anchor="w", padx=11,
                                                     pady=(7, 0))
        val = ctk.CTkLabel(box, text="🔥 0 j", font=theme.font("mono", 19),
                           text_color=C["text"])
        val.pack(anchor="w", padx=11)
        rec = ctk.CTkLabel(box, text="record 0", font=theme.font("head", 9),
                           text_color=C["dimmer"])
        rec.pack(anchor="w", padx=11, pady=(0, 7))
        return {"val": val, "rec": rec}

    # ------------------------------------------------------------- rendu
    def _largeur_nom(self) -> int:
        """Combien de caractères tiennent dans la colonne de gauche.

        `CTkCheckBox` ne sait pas replier son texte : il le coupe net au bord.
        On calcule donc la coupe nous-mêmes, avec des points de suspension, en
        fonction de la largeur réelle du panneau — élargir la fenêtre montre
        vraiment plus de texte.
        """
        largeur = self._derniere_largeur or self.winfo_width() or 322
        return max(14, int((largeur - 150) / 7.5))

    def _sur_redimension(self, event=None):
        precedente = self._derniere_largeur
        super()._sur_redimension(event)
        if self.etat is not None and precedente != self._derniere_largeur:
            self._rendre_seance(self.etat)
            self._rendre_core(self.etat)

    def refresh(self, snap=None, force=False):
        maintenant = time.time()
        if not force and self.etat is not None \
                and maintenant - self._dernier_calcul < RECALC_S:
            self._maj_chrono()
            return
        self._dernier_calcul = maintenant
        try:
            self.etat = jour.etat_jour()
        except Exception as exc:            # base illisible : on ne casse rien
            self.lbl_date.configure(text="Base indisponible")
            self.lbl_semaine.configure(text=str(exc))
            return
        self._rendre()

    def _rendre(self):
        e = self.etat
        self.lbl_date.configure(text=e["libelle"])
        marques = [f"Semaine {e['semaine_programme']} du programme"]
        if e["allegee"]:
            marques.append("allégée (−40 % de volume)")
        if e["reprise"]:
            marques.append("reprise")
        self.lbl_semaine.configure(text=" · ".join(marques))

        for domaine, widgets in (("sport", self.streak_sport),
                                 ("coreen", self.streak_kr)):
            st = e["streaks"].get(domaine, {})
            valide = e["valide"].get(domaine)
            widgets["val"].configure(
                text=f"🔥 {st.get('courant', 0)} j",
                text_color=C["green"] if valide else C["text"])
            widgets["rec"].configure(text=f"record {st.get('record', 0)}")

        self._rendre_conseils(e["conseils"])
        self._rendre_seance(e)
        self._rendre_core(e)
        self._rendre_coreen(e)
        self._rendre_cardio(e)
        self._rendre_semaine(e)
        self._rendre_serveur()

    def _rendre_conseils(self, conseils):
        for w in self.conseils.winfo_children():
            w.destroy()
        for c in conseils:
            couleur = {"medical": C["red"], "adaptation": C["orange"]}.get(
                c["niveau"], C["accent_lt2"])
            box = ctk.CTkFrame(self.conseils, fg_color=C["inset"],
                               corner_radius=8, border_width=1,
                               border_color=C["inset_border"])
            box.pack(fill="x", pady=(0, 6))
            self.replier(ctk.CTkLabel(box, text=c["texte"], anchor="w", justify="left",
                         wraplength=300, font=theme.font("body", 11),
                         text_color=couleur)).pack(fill="x", padx=10, pady=7)

    def _ligne_tache(self, parent, tache_id, libelle, fait, detail=None):
        """Une ligne cochable. Le clic écrit en base tout de suite."""
        ligne = ctk.CTkFrame(parent, fg_color="transparent")
        ligne.pack(fill="x", pady=1)
        var = ctk.BooleanVar(value=bool(fait))
        # Le détail est posé EN PREMIER : avec `pack`, un widget « expand »
        # placé avant réserverait toute la largeur et le recouvrirait.
        if detail:
            ctk.CTkLabel(ligne, text=detail, font=theme.font("mono", 10),
                         text_color=C["accent_lt2"]).pack(side="right",
                                                          padx=(6, 0))
        case = ctk.CTkCheckBox(
            ligne, text=libelle, variable=var, checkbox_width=17,
            checkbox_height=17, font=theme.font("body", 11),
            text_color=C["dim"] if fait else C["text_norm"],
            command=lambda: self._cocher(tache_id, var.get()))
        case.pack(side="left", fill="x", expand=True)
        if tache_id is None:
            case.configure(state="disabled")

    def _rendre_seance(self, e):
        for w in self.liste_seance.winfo_children():
            w.destroy()
        seances = e["seances"]
        if not seances:
            self.lbl_seance.configure(text="Repos — pas de séance planifiée.")
            self.lbl_seance_meta.configure(text="")
            self.btn_demarrer.configure(state="disabled")
            return
        s = seances[0]
        self.btn_demarrer.configure(state="normal")
        etiquette = {"planifie": "", "en_cours": " · EN COURS",
                     "fait": " · faite", "partiel": " · partielle",
                     "manque": " · MANQUÉE"}.get(s["statut"], "")
        self.lbl_seance.configure(text=f"{s['nom']}{etiquette}")
        meta = [f"{s['lieu']}", f"{s['duree_cible_min']} min",
                f"{s['faits']}/{s['total']} exercices"]
        if s["contacts_plyo"]:
            meta.append(f"plyo {s['contacts_plyo']}/{s['contacts_max']} contacts")
        texte = " · ".join(meta)
        if s["contacts_plyo"]:
            texte += f"\n{s['plyo_libelle']}"
        self.lbl_seance_meta.configure(text=texte)

        for exo in s["exos"]:
            libelle, detail = _ligne_exo(exo, self._largeur_nom())
            self._ligne_tache(self.liste_seance, exo["tache_id"], libelle,
                              exo["fait"], detail)
        self._maj_chrono()

    def _maj_chrono(self):
        """Chrono de séance : recalculé sur l'horodatage de début."""
        if not self.etat or not self.etat["seances"]:
            return
        s = self.etat["seances"][0]
        if s["statut"] == "en_cours" and s["debut_ts"]:
            ecoule = int(time.time() - s["debut_ts"])
            self.btn_demarrer.configure(
                text=f"■ {ecoule // 60:02d}:{ecoule % 60:02d}")
        elif s["statut"] in ("fait", "partiel"):
            self.btn_demarrer.configure(text="✓ Terminée")
        else:
            self.btn_demarrer.configure(text="▶ Démarrer")

    def _rendre_core(self, e):
        for w in self.liste_core.winfo_children():
            w.destroy()
        core = e["core"]
        if not core:
            self.lbl_core.configure(text="Pas de bloc core ce soir (full abdos "
                                         "le samedi).")
            return
        suffixe = " · version courte" if core["version_courte"] else ""
        self.lbl_core.configure(
            text=f"{core['nom']} — {core['duree_cible_min']} min{suffixe}")
        for exo in core["exos"]:
            libelle, detail = _ligne_exo(exo, self._largeur_nom())
            self._ligne_tache(self.liste_core, exo["tache_id"], libelle,
                              exo["fait"], detail)

    def _rendre_coreen(self, e):
        for w in self.liste_kr.winfo_children():
            w.destroy()
        kr = e["coreen"]
        self.lbl_kr.configure(
            text=f"Semaine {kr['semaine']} · {kr['theme']}"
            if kr["semaine"] else "Programme coréen non initialisé")
        exo = kr.get("exercice") or {}
        self.lbl_kr_meta.configure(
            text=f"{kr['cartes_dues']} cartes dues"
                 + (f"  ·  exercice : {exo.get('type', '')}" if exo else ""))
        for tache in kr["checklist"]:
            self._ligne_tache(self.liste_kr, tache["id"], tache["libelle"],
                              tache["fait"])

    def _rendre_cardio(self, e):
        for w in self.liste_cardio.winfo_children():
            w.destroy()
        cardio = e["cardio"]
        if not cardio:
            self.carte_cardio.pack_forget()
            return
        self.carte_cardio.pack(fill="x", padx=2, pady=(0, 2))
        self.lbl_cardio.configure(
            text=f"{cardio['nom']} · {cardio['duree_cible_min']} min\n"
                 f"{cardio['plan_course'] or ''}")
        for exo in cardio["exos"]:
            self._ligne_tache(self.liste_cardio, exo["tache_id"],
                              f"{exo['nom']} — {exo['cible']}", exo["fait"])

    # ---------------------------------------------------- bande semaine
    def _rendre_semaine(self, e):
        cv = self.cv_semaine
        cv.delete("all")
        jours = e["semaine"]
        largeur = max(cv.winfo_width(), 300)
        pas = largeur / 7.0
        for i, cellule in enumerate(jours):
            cx = pas * i + pas / 2
            cv.create_text(cx, 10, text=cellule["lettre"], fill=C["dim"],
                           font=theme.font("head", 9, "bold"))
            for rang, (domaine, y) in enumerate((("sport", 34), ("coreen", 62))):
                couleur = COULEUR_ETAT.get(cellule[domaine], C["grey"])
                r = 9
                if cellule["aujourdhui"]:
                    cv.create_oval(cx - r - 4, y - r - 4, cx + r + 4, y + r + 4,
                                   outline=C["accent_lt"], width=2)
                cv.create_oval(cx - r, y - r, cx + r, y + r, fill=couleur,
                               outline="")
                if rang == 0 and i == 0:
                    cv.create_text(4, y, text="S", anchor="w", fill=C["dimmer"],
                                   font=theme.font("head", 8, "bold"))
                if rang == 1 and i == 0:
                    cv.create_text(4, y, text="K", anchor="w", fill=C["dimmer"],
                                   font=theme.font("head", 8, "bold"))
        if self._jour_detail:
            self._afficher_detail(self._jour_detail)

    def _clic_semaine(self, event):
        if not self.etat:
            return
        largeur = max(self.cv_semaine.winfo_width(), 300)
        index = min(6, max(0, int(event.x / (largeur / 7.0))))
        self._jour_detail = self.etat["semaine"][index]["date"]
        self._afficher_detail(self._jour_detail)

    def _afficher_detail(self, date_str):
        cellule = next((c for c in self.etat["semaine"] if c["date"] == date_str),
                       None)
        if not cellule:
            return
        taches = db.q("SELECT domaine, libelle, fait FROM tache_jour "
                      "WHERE date = ? ORDER BY domaine, ordre", (date_str,))
        if not taches:
            resume = "Journée non matérialisée (le cockpit n'a pas été ouvert)."
        else:
            faits = sum(1 for t in taches if t["fait"])
            manquants = [t["libelle"].split(" — ")[0] for t in taches
                         if not t["fait"]][:4]
            resume = f"{faits}/{len(taches)} tâches"
            if manquants:
                resume += " · reste : " + ", ".join(manquants)
        self.lbl_detail.configure(
            text=f"{jour.libelle_date(date_str)} — sport {cellule['sport_detail']}"
                 f" · coréen {cellule['coreen_detail']}\n{resume}")

    # ------------------------------------------------- accès téléphone
    def _rendre_serveur(self):
        etat = webserver.etat()
        if etat["actif"]:
            texte = "Serveur en ligne"
            couleur = C["green"]
        else:
            texte = "Serveur mobile hors ligne"
            couleur = C["red"]
        attente = etat["en_attente"]
        if attente:
            texte += f" · {attente} op. en attente"
        self.lbl_srv.configure(text=texte, text_color=couleur)
        self.lbl_url.configure(
            text=etat["url"] or (etat["erreur"] or "démarrage impossible"))
        self._dessiner_qr(etat["url"])

    def _dessiner_qr(self, url):
        if url == self._qr_signature:
            return
        self._qr_signature = url
        cv = self.cv_qr
        cv.delete("all")
        if not url:
            cv.create_text(66, 66, text="—", fill=C["dim"],
                           font=theme.font("head", 20))
            return
        try:
            matrice = qr.matrice(url, marge=2)
        except Exception:
            # Encodage impossible : on ne plante pas, l'URL reste lisible et
            # copiable juste à côté.
            cv.create_text(66, 60, text="QR\nindisponible", fill=C["dim"],
                           justify="center", font=theme.font("head", 10))
            return
        n = len(matrice)
        cote = 132 // n
        marge = (132 - cote * n) // 2
        cv.create_rectangle(0, 0, 132, 132, fill="#ffffff", outline="")
        for r, ligne in enumerate(matrice):
            for c, plein in enumerate(ligne):
                if plein:
                    x, y = marge + c * cote, marge + r * cote
                    cv.create_rectangle(x, y, x + cote, y + cote,
                                        fill="#0c0a13", outline="")

    def _copier_url(self):
        etat = webserver.etat()
        if not etat["url"]:
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(etat["url"])
            self.app.show_banner("URL mobile copiée dans le presse-papier.")
        except Exception:
            pass

    def _ouvrir_url(self):
        etat = webserver.etat()
        if etat["url"]:
            webbrowser.open(etat["url"])

    # ---------------------------------------------------------- actions
    def _cocher(self, tache_id, fait):
        if tache_id is None:
            return
        jour.cocher(tache_id, bool(fait), source="pc")
        self.refresh(force=True)

    def _demarrer(self):
        if not self.etat or not self.etat["seances"]:
            return
        s = self.etat["seances"][0]
        if not s["seance_id"]:
            return
        if s["statut"] == "en_cours":
            resultat = jour.terminer_seance(s["seance_id"], source="pc")
            self._annoncer_records(resultat.get("records") or [])
        else:
            jour.demarrer_seance(s["seance_id"], source="pc")
        self.refresh(force=True)

    def _annoncer_records(self, records):
        if not records:
            return
        lignes = [f"{r['exercice']} · {r['type']} : {r['valeur']:g} {r['unite']}"
                  for r in records[:5]]
        self.app.show_banner("Record battu ! " + " | ".join(lignes), ms=12000)

    def _manquee(self):
        if not self.etat or not self.etat["seances"]:
            return
        s = self.etat["seances"][0]
        if not s["seance_id"]:
            return
        if not messagebox.askyesno(
                "Séance manquée",
                "Marquer la séance comme manquée ?\n\n"
                "Elle ne sera pas replanifiée et la journée sport ne sera pas "
                "validée — la série repart de zéro."):
            return
        jour.marquer_manquee(s["seance_id"], source="pc")
        self.refresh(force=True)

    def _reviser(self):
        self.app.ouvrir_onglet("coreen")
        try:
            self.app.tabs["coreen"].start_session()
        except Exception:
            pass

    def _log_cardio(self):
        try:
            km = float((self.e_km.get() or "0").replace(",", "."))
            minutes = float((self.e_min.get() or "0").replace(",", "."))
        except ValueError:
            return
        if not km and not minutes:
            return
        jour.enregistrer_cardio(distance_km=km or None,
                                duree_s=int(minutes * 60) or None,
                                type_="course", source="pc")
        self.e_km.delete(0, "end")
        self.e_min.delete(0, "end")
        self.app.show_banner("Sortie cardio enregistrée.")
        self.refresh(force=True)

    def _log_foot(self):
        try:
            minutes = float((self.e_foot.get() or "60").replace(",", "."))
            ressenti = int(self.e_foot_res.get() or "7")
        except ValueError:
            return
        jour.enregistrer_cardio(type_="foot_salle", duree_s=int(minutes * 60),
                                ressenti=ressenti, source="pc")
        self.app.show_banner("Foot en salle enregistré — le programme s'adapte.")
        self.refresh(force=True)
