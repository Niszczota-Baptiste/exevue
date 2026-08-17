"""Onglet [Coréen] — programme 9 semaines, révision SRS, exercices générés.

Tout vient désormais de SQLite (`kr_*`) via `backend/korean.py`. L'ancien deck
`config.json` a été repris par la migration : les échéances sont conservées, et
les mots ajoutés à la main réapparaissent sous le tag « vocabulaire libre ».

Chaque item porte deux cartes : KR→FR d'abord, FR→KR débloquée après trois
réussites — on ne demande pas de produire ce qu'on ne reconnaît pas encore.
"""
import json
import random
import time
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ..backend import jour, korean
from . import theme
from .base import ThemedScroll
from .theme import C

LIBELLE_DIRECTION = {"kr_fr": "KR → FR", "fr_kr": "FR → KR"}
LIBELLE_EXO = {"reco": "Reconnaissance", "prod": "Production",
               "trous": "Texte à trous", "roleplay": "Jeu de rôle",
               "ecoute": "Écoute"}


class CoreenTab(ThemedScroll):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.deck = app.deck
        self._queue = []
        self._current = None
        self._debut_carte = 0.0
        self._exo_courant = None
        self._reponses = {}
        self._build()

    # ------------------------------------------------------------ montage
    def _build(self):
        # --- semaine en cours ---
        self.f_semaine = self._section("Semaine en cours")
        self.lbl_semaine = self.replier(ctk.CTkLabel(
            self.f_semaine, text="—", anchor="w", justify="left",
            wraplength=300, font=theme.font("body", 14, "bold"),
            text_color=C["text"]))
        self.lbl_semaine.pack(fill="x")
        self.lbl_objectifs = self.replier(ctk.CTkLabel(
            self.f_semaine, text="", anchor="w", justify="left",
            wraplength=300, font=theme.font("body", 11), text_color=C["muted"]))
        self.lbl_objectifs.pack(fill="x", pady=(2, 6))
        self.lbl_culture = self.replier(ctk.CTkLabel(
            self.f_semaine, text="", anchor="w", justify="left",
            wraplength=300, font=theme.font("body", 11),
            text_color=C["accent_lt2"]))
        self.lbl_culture.pack(fill="x")

        # --- révision ---
        f = self._section("Révision")
        carte = ctk.CTkFrame(f, fg_color=C["inset"], corner_radius=10,
                             border_color=C["inset_border"], border_width=1)
        carte.pack(fill="x", pady=(0, 8))
        self.card_dir = ctk.CTkLabel(carte, text="", font=theme.font("head", 9, "bold"),
                                     text_color=C["dim"])
        self.card_dir.pack(fill="x", padx=10, pady=(8, 0))
        self.card_kr = self.replier(ctk.CTkLabel(carte, text="—", wraplength=300,
                                    font=theme.font("body", 26, "bold"),
                                    text_color=C["accent_lt2"]))
        self.card_kr.pack(fill="x", padx=10, pady=(2, 2))
        self.card_romaja = ctk.CTkLabel(carte, text="", text_color=C["dim"],
                                        font=theme.font("mono", 12))
        self.card_romaja.pack(fill="x", padx=10)
        self.card_answer = self.replier(ctk.CTkLabel(carte, text="", font=theme.font("body", 14),
                                        wraplength=300, justify="center",
                                        text_color=C["text"]))
        self.card_answer.pack(fill="x", padx=10, pady=(6, 14))

        self.btn_reveal = theme.primary_button(f, "Révéler", self._reveal)
        self.btn_reveal.pack(fill="x", pady=(0, 6))
        grade = ctk.CTkFrame(f, fg_color="transparent")
        grade.pack(fill="x")
        ctk.CTkButton(grade, text="Pas su", fg_color="#5a2740",
                      hover_color="#7a3b3b", font=theme.font("head", 13, "bold"),
                      command=lambda: self._grade(False)).pack(
            side="left", expand=True, fill="x", padx=(0, 4))
        ctk.CTkButton(grade, text="Su", fg_color="#1f6b48", hover_color="#2e7d4f",
                      font=theme.font("head", 13, "bold"),
                      command=lambda: self._grade(True)).pack(
            side="left", expand=True, fill="x", padx=(4, 0))
        self.session_info = ctk.CTkLabel(f, text="", text_color=C["dim"],
                                         font=theme.font("body", 11))
        self.session_info.pack(fill="x", pady=(6, 6))
        ctk.CTkButton(f, text="Lancer une révision", command=self.start_session,
                      font=theme.font("head", 12, "bold")).pack(fill="x")

        # --- exercice du jour ---
        f = self._section("Exercice du jour")
        self.lbl_exo = self.replier(ctk.CTkLabel(f, text="—", anchor="w", justify="left",
                                    wraplength=300,
                                    font=theme.font("body", 13, "bold"),
                                    text_color=C["text"]))
        self.lbl_exo.pack(fill="x", pady=(0, 6))
        self.zone_exo = ctk.CTkFrame(f, fg_color="transparent")
        self.zone_exo.pack(fill="x")
        ctk.CTkButton(f, text="Générer / rejouer l'exercice",
                      command=self._charger_exercice,
                      font=theme.font("head", 12, "bold")).pack(fill="x",
                                                                pady=(6, 0))

        # --- dialogues ---
        f = self._section("Dialogues de la semaine")
        self.zone_dialogues = ctk.CTkFrame(f, fg_color="transparent")
        self.zone_dialogues.pack(fill="x")

        # --- deck ---
        f = self._section("Deck")
        self.lbl_stats = ctk.CTkLabel(f, text="", anchor="w",
                                      font=theme.font("mono", 11),
                                      text_color=C["accent_lt2"])
        self.lbl_stats.pack(fill="x", pady=(0, 6))
        impexp = ctk.CTkFrame(f, fg_color="transparent")
        impexp.pack(fill="x", pady=(0, 6))
        for txt, kind, fn in (("Imp. CSV", "csv", self._import),
                              ("Imp. JSON", "json", self._import),
                              ("Exp. CSV", "csv", self._export),
                              ("Exp. JSON", "json", self._export)):
            ctk.CTkButton(impexp, text=txt, width=78,
                          font=theme.font("head", 11, "bold"),
                          command=lambda k=kind, f=fn: f(k)).pack(side="left",
                                                                  padx=2)

        addrow = ctk.CTkFrame(f, fg_color="transparent")
        addrow.pack(fill="x", pady=(0, 6))
        self.add_kr = ctk.CTkEntry(addrow, placeholder_text="한국어", width=80,
                                   font=theme.font("body", 13))
        self.add_kr.pack(side="left", padx=2)
        self.add_romaja = ctk.CTkEntry(addrow, placeholder_text="romaja", width=78,
                                       font=theme.font("body", 12))
        self.add_romaja.pack(side="left", padx=2)
        self.add_fr = ctk.CTkEntry(addrow, placeholder_text="français",
                                   font=theme.font("body", 12))
        self.add_fr.pack(side="left", fill="x", expand=True, padx=2)
        ctk.CTkButton(addrow, text="+", width=32, command=self._add_card,
                      fg_color=C["accent"], hover_color=C["accent_dk"],
                      text_color="#f6f2ff", border_width=0,
                      font=theme.font("head", 13, "bold")).pack(side="left",
                                                                padx=2)

        filtre = ctk.CTkFrame(f, fg_color="transparent")
        filtre.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(filtre, text="Afficher", font=theme.font("body", 11),
                     text_color=C["muted"]).pack(side="left")
        self.filtre_semaine = ctk.CTkOptionMenu(
            filtre, values=["Semaine en cours", "Vocabulaire libre", "Tout"],
            command=lambda _=None: self._render_deck(),
            font=theme.font("body", 11), fg_color=C["inset"],
            button_color=C["accent"], button_hover_color=C["accent_dk"])
        self.filtre_semaine.pack(side="right")

        self.deck_list = ctk.CTkFrame(f, fg_color="transparent")
        self.deck_list.pack(fill="x")

        self._render_semaine()
        self._render_deck()
        self._render_dialogues()

    # -------------------------------------------------------------- rendu
    def _render_semaine(self):
        sem = jour.semaine_coreen()
        if not sem:
            self.lbl_semaine.configure(text="Programme non initialisé.")
            return
        self.lbl_semaine.configure(
            text=f"Semaine {sem['numero']} · {sem['theme']}")
        try:
            objectifs = json.loads(sem["objectifs_json"] or "[]")
        except ValueError:
            objectifs = []
        self.lbl_objectifs.configure(
            text=f"{sem['date_debut']} → {sem['date_fin']}\n"
                 + " · ".join(objectifs))
        self.lbl_culture.configure(text=sem["note_culture"] or "")
        exo = jour.exercice_coreen_du_jour(jour.jour_courant())
        if exo:
            self._exo_courant = exo
            self.lbl_exo.configure(
                text=exo["titre"] or LIBELLE_EXO.get(exo["type"], exo["type"]))

    def _render_dialogues(self):
        for w in self.zone_dialogues.winfo_children():
            w.destroy()
        sem = jour.semaine_coreen()
        if not sem:
            return
        dialogues = [i for i in korean.items(sem["id"]) if i["type"] == "dialogue"]
        if not dialogues:
            ctk.CTkLabel(self.zone_dialogues, text="Aucun dialogue cette semaine.",
                         text_color=C["dim"], font=theme.font("body", 11)).pack(
                fill="x")
            return
        for d in dialogues:
            titre = d["exemple_kr"] or "Dialogue"
            bloc = ctk.CTkFrame(self.zone_dialogues, fg_color=C["inset"],
                                corner_radius=8, border_width=1,
                                border_color=C["inset_border"])
            bloc.pack(fill="x", pady=(0, 6))
            ctk.CTkLabel(bloc, text=titre, anchor="w",
                         font=theme.font("head", 11, "bold"),
                         text_color=C["accent_lt"]).pack(fill="x", padx=10,
                                                         pady=(7, 2))
            kr = (d["kr"] or "").split("\n")
            fr = (d["fr"] or "").split("\n")
            for i, ligne in enumerate(kr):
                self.replier(ctk.CTkLabel(bloc, text=ligne, anchor="w", justify="left",
                             wraplength=290, font=theme.font("body", 12),
                             text_color=C["accent_lt2"])).pack(fill="x", padx=10)
                if i < len(fr):
                    self.replier(ctk.CTkLabel(bloc, text=fr[i], anchor="w", justify="left",
                                 wraplength=290, font=theme.font("body", 10),
                                 text_color=C["muted"])).pack(fill="x", padx=10,
                                                             pady=(0, 4))
            ctk.CTkLabel(bloc, text="", height=4).pack()

    # ------------------------------------------------------------ session
    def start_session(self):
        self._queue = list(korean.cartes_dues(limite=None))
        self._next_card()

    def _next_card(self):
        self.session_info.configure(
            text=f"{len(self._queue)} carte(s) en file")
        if not self._queue:
            self._current = None
            self.card_dir.configure(text="")
            self.card_kr.configure(text="✓", text_color=C["green"])
            self.card_romaja.configure(text="")
            self.card_answer.configure(text="Rien à réviser pour l'instant.")
            self.btn_reveal.configure(state="disabled")
            return
        self.btn_reveal.configure(state="normal")
        self._current = self._queue[0]
        self._debut_carte = time.time()
        vers_fr = self._current["direction"] == "kr_fr"
        self.card_dir.configure(
            text=LIBELLE_DIRECTION.get(self._current["direction"], ""))
        self.card_kr.configure(
            text=self._current["kr"] if vers_fr else self._current["fr"],
            text_color=C["accent_lt2"])
        self.card_romaja.configure(text="")
        self.card_answer.configure(text="")

    def _reveal(self):
        c = self._current
        if not c:
            return
        vers_fr = c["direction"] == "kr_fr"
        self.card_romaja.configure(text=c["romaja"] or "")
        reponse = c["fr"] if vers_fr else c["kr"]
        if c["exemple_kr"]:
            reponse += f"\n\n{c['exemple_kr']}"
            if c["exemple_fr"]:
                reponse += f"\n{c['exemple_fr']}"
        self.card_answer.configure(text=reponse)

    def _grade(self, su):
        c = self._current
        if not c:
            return
        resultat = korean.noter(
            c["id"], su, temps_ms=int((time.time() - self._debut_carte) * 1000),
            source="pc")
        if resultat.get("debloquee_fr_kr"):
            self.app.show_banner(
                f"« {c['kr']} » : 3 réussites — la carte FR→KR est débloquée.")
        self._queue.pop(0)
        if not su:
            self._queue.append(c)      # pas su : on la revoit en fin de file
        self._next_card()
        self._render_stats()

    # ---------------------------------------------------------- exercice
    def _charger_exercice(self):
        for w in self.zone_exo.winfo_children():
            w.destroy()
        self._reponses = {}
        if not self._exo_courant:
            ctk.CTkLabel(self.zone_exo, text="Pas d'exercice pour aujourd'hui.",
                         text_color=C["dim"], font=theme.font("body", 11)).pack(
                fill="x")
            return
        contenu = korean.contenu_exercice(self._exo_courant["id"]) or {}
        typ = contenu.get("type")

        if typ == "roleplay":
            self._rendre_roleplay(contenu)
        elif typ == "trous":
            self._rendre_trous(contenu)
        elif contenu.get("questions"):
            self._rendre_qcm(contenu)
        else:
            ctk.CTkLabel(self.zone_exo, text="Contenu indisponible.",
                         text_color=C["dim"], font=theme.font("body", 11)).pack(
                fill="x")

    def _rendre_qcm(self, contenu):
        for i, q in enumerate(contenu["questions"][:6]):
            bloc = ctk.CTkFrame(self.zone_exo, fg_color=C["inset"],
                                corner_radius=8, border_width=1,
                                border_color=C["inset_border"])
            bloc.pack(fill="x", pady=(0, 6))
            self.replier(ctk.CTkLabel(bloc, text=q["enonce"], anchor="w", justify="left",
                         wraplength=290, font=theme.font("body", 14, "bold"),
                         text_color=C["accent_lt2"])).pack(fill="x", padx=10,
                                                          pady=(8, 0))
            if q.get("romaja"):
                ctk.CTkLabel(bloc, text=q["romaja"], anchor="w",
                             font=theme.font("mono", 10),
                             text_color=C["dim"]).pack(fill="x", padx=10)
            choix = list(q["choix"])
            random.shuffle(choix)
            for c in choix:
                b = ctk.CTkButton(
                    bloc, text=c, anchor="w", font=theme.font("body", 12),
                    fg_color=C["card"], hover_color=C["accent_dk"],
                    text_color=C["text_norm"])
                b.configure(command=lambda b=b, c=c, bon=q["bonne"]:
                            self._repondre(b, c == bon))
                b.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(bloc, text="", height=4).pack()

    def _rendre_trous(self, contenu):
        for p in contenu.get("phrases", []):
            bloc = ctk.CTkFrame(self.zone_exo, fg_color=C["inset"],
                                corner_radius=8, border_width=1,
                                border_color=C["inset_border"])
            bloc.pack(fill="x", pady=(0, 6))
            self.replier(ctk.CTkLabel(bloc, text=p["phrase"], anchor="w", justify="left",
                         wraplength=290, font=theme.font("body", 15),
                         text_color=C["accent_lt2"])).pack(fill="x", padx=10,
                                                          pady=(8, 0))
            ctk.CTkLabel(bloc, text=p.get("indice", ""), anchor="w",
                         font=theme.font("body", 10),
                         text_color=C["dim"]).pack(fill="x", padx=10)
            ligne = ctk.CTkFrame(bloc, fg_color="transparent")
            ligne.pack(fill="x", padx=10, pady=(4, 8))
            champ = ctk.CTkEntry(ligne, font=theme.font("body", 13))
            champ.pack(side="left", fill="x", expand=True, padx=(0, 4))
            resultat = ctk.CTkLabel(ligne, text="", width=70,
                                    font=theme.font("body", 11))
            resultat.pack(side="left")
            ctk.CTkButton(
                ligne, text="OK", width=40, font=theme.font("head", 11, "bold"),
                command=lambda c=champ, r=resultat, bon=p["reponse"]:
                self._verifier_trou(c, r, bon)).pack(side="left", padx=(4, 0))

    def _verifier_trou(self, champ, resultat, bon):
        juste = champ.get().strip() == bon.strip()
        resultat.configure(text="✓" if juste else f"→ {bon}",
                           text_color=C["green"] if juste else C["red"])

    def _rendre_roleplay(self, contenu):
        ctk.CTkLabel(self.zone_exo,
                     text=f"Rôle de l'app : {contenu.get('role_app', '—')}",
                     anchor="w", font=theme.font("body", 11),
                     text_color=C["muted"]).pack(fill="x", pady=(0, 6))
        for scene in contenu.get("scenes", []):
            bloc = ctk.CTkFrame(self.zone_exo, fg_color=C["inset"],
                                corner_radius=8, border_width=1,
                                border_color=C["inset_border"])
            bloc.pack(fill="x", pady=(0, 6))
            self.replier(ctk.CTkLabel(bloc, text=scene["app"], anchor="w", justify="left",
                         wraplength=290, font=theme.font("body", 14, "bold"),
                         text_color=C["accent_lt2"])).pack(fill="x", padx=10,
                                                          pady=(8, 0))
            self.replier(ctk.CTkLabel(bloc, text=scene.get("app_fr", ""), anchor="w",
                         justify="left", wraplength=290,
                         font=theme.font("body", 10),
                         text_color=C["dim"])).pack(fill="x", padx=10)
            choix = list(scene.get("choix", []))
            bonne = choix[0] if choix else None
            random.shuffle(choix)
            for c in choix:
                b = ctk.CTkButton(bloc, text=c, anchor="w",
                                  font=theme.font("body", 12),
                                  fg_color=C["card"], hover_color=C["accent_dk"],
                                  text_color=C["text_norm"])
                b.configure(command=lambda b=b, c=c: self._repondre(b, c == bonne))
                b.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(bloc, text="", height=4).pack()

    def _repondre(self, bouton, juste):
        bouton.configure(fg_color="#1f6b48" if juste else "#5a2740")

    # -------------------------------------------------------------- deck
    def _render_stats(self):
        st = korean.stats()
        self.lbl_stats.configure(
            text=f"{st['items']} items · {st['cartes']} cartes · "
                 f"{st['apprises']} apprises · {st['matures']} matures · "
                 f"{st['dues']} dues")

    def _add_card(self):
        kr = self.add_kr.get().strip()
        if not kr:
            return
        korean.ajouter_item(kr, self.add_romaja.get(), self.add_fr.get())
        for e in (self.add_kr, self.add_romaja, self.add_fr):
            e.delete(0, "end")
        self._render_deck()

    def _render_deck(self):
        for w in self.deck_list.winfo_children():
            w.destroy()
        self._render_stats()
        choix = self.filtre_semaine.get() if hasattr(self, "filtre_semaine") \
            else "Semaine en cours"
        if choix == "Vocabulaire libre":
            items = [i for i in korean.items() if i["source"] in ("libre", "legacy")]
        elif choix == "Tout":
            items = korean.items(limite=250)
        else:
            sem = jour.semaine_coreen()
            items = korean.items(sem["id"]) if sem else []
        if not items:
            ctk.CTkLabel(self.deck_list, text="(rien à afficher)",
                         text_color=C["dim"], font=theme.font("body", 11)).pack(
                fill="x")
            return
        for item in items[:200]:
            ligne = ctk.CTkFrame(self.deck_list, fg_color="transparent")
            ligne.pack(fill="x", pady=1)
            marque = {"structure": "◆", "dialogue": "▸", "phrase": "·"}.get(
                item["type"], "")
            ctk.CTkLabel(ligne, text=f"{marque} {item['kr'][:24]}   {(item['fr'] or '')[:24]}",
                         anchor="w", font=theme.font("body", 11),
                         text_color=C["text_norm"]).pack(side="left", fill="x",
                                                         expand=True)
            ctk.CTkButton(ligne, text="✕", width=24, fg_color="#5a2740",
                          hover_color="#7a3b3b",
                          font=theme.font("head", 10, "bold"),
                          command=lambda i=item["id"]: self._del_item(i)).pack(
                side="left")

    def _del_item(self, item_id):
        korean.supprimer_item(item_id)
        self._render_deck()

    # ------------------------------------------------------ import/export
    def _export(self, kind):
        ext = "csv" if kind == "csv" else "json"
        path = filedialog.asksaveasfilename(defaultextension=f".{ext}",
                                            filetypes=[(ext.upper(), f"*.{ext}")])
        if not path:
            return
        try:
            data = korean.export_csv() if kind == "csv" else korean.export_json()
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(data)
        except Exception as e:
            messagebox.showerror("Export", str(e))

    def _import(self, kind):
        ext = "csv" if kind == "csv" else "json"
        path = filedialog.askopenfilename(filetypes=[(ext.upper(), f"*.{ext}")])
        if not path:
            return
        replace = messagebox.askyesno(
            "Import", "Remplacer le vocabulaire libre existant ?\n"
                      "(Non = ajouter. Le programme 9 semaines n'est jamais "
                      "touché.)")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                texte = fh.read()
            n = (korean.import_csv(texte, replace=replace) if kind == "csv"
                 else korean.import_json(texte, replace=replace))
            self.app.show_banner(f"{n} item(s) importé(s).")
        except Exception as e:
            messagebox.showerror("Import", str(e))
        self._render_deck()

    def refresh(self, snap=None):
        pass
