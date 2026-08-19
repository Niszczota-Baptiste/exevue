# -*- coding: utf-8 -*-
"""Onglet [Sport] — la vue d'ensemble : programme, semaine, exos, historique.

Là où [Aujourd'hui] montre *ce qu'il faut faire maintenant* et [Stats] *ce que
les chiffres disent sur la durée*, cet onglet répond à « montre-moi tout » :
les quatre vues couvrent le passé, le présent, le futur et le référentiel.

Aucun calcul ici — `backend/sport.py` renvoie des lignes déjà agrégées.
Comme pour [Stats], le rendu n'est refait qu'à l'ouverture ou sur demande :
parcourir 4 semaines de programme n'a aucune raison d'être recalculé à chaque
tick d'une seconde.
"""
import customtkinter as ctk

from ..backend import sport
from . import theme
from .base import ThemedScroll
from .theme import C
from .widgets import BarChart

VUES = [("Semaine", "semaine"), ("Exos", "exos"), ("Plan", "programme"),
        ("Passé", "historique")]

COULEUR_STATUT = {
    "fait": C["green"], "partiel": C["orange"], "manque": C["red"],
    "en_cours": C["accent_lt"], "planifie": C["dim"],
}
LIBELLE_STATUT = {
    "fait": "fait", "partiel": "partiel", "manque": "manquée",
    "en_cours": "en cours", "planifie": "prévu",
}
COULEUR_BLOC = {
    "echauffement": C["blue"], "explosif": C["orange"],
    "principal": C["text_norm"], "finisher": C["pink"],
}


def _kg(valeur) -> str:
    if not valeur:
        return "—"
    arrondi = round(float(valeur), 1)
    entier = int(arrondi)
    return f"{entier} kg" if arrondi == entier else f"{arrondi} kg"


def _volume(valeur) -> str:
    if not valeur:
        return "—"
    return f"{float(valeur):,.0f} kg".replace(",", " ")


def _mmss(secondes) -> str:
    if not secondes:
        return "—"
    secondes = int(secondes)
    return f"{secondes // 60} min" if secondes >= 60 else f"{secondes} s"


class SportTab(ThemedScroll):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.vue = "semaine"
        self.decalage = 0            # semaines d'écart, pour naviguer
        self._charge = False
        self._largeur_rendue = 0     # largeur au moment du dernier rendu
        self._report = None          # rendu différé après redimensionnement
        self._build()

    # ------------------------------------------------------------ montage
    def _build(self):
        barre = ctk.CTkFrame(self, fg_color="transparent")
        barre.pack(fill="x", pady=(0, 8))
        self._boutons = {}
        for i, (libelle, cle) in enumerate(VUES):
            b = ctk.CTkButton(barre, text=libelle, width=10,
                              font=theme.font("head", 10, "bold"),
                              command=lambda c=cle: self._changer_vue(c))
            b.grid(row=0, column=i, padx=2, sticky="ew")
            self._boutons[cle] = b
        ctk.CTkButton(barre, text="↻", width=32,
                      font=theme.font("head", 13, "bold"),
                      command=lambda: self.refresh(force=True)
                      ).grid(row=0, column=len(VUES), padx=(6, 0))
        barre.grid_columnconfigure(tuple(range(len(VUES))), weight=1,
                                   uniform="v")

        self.corps = ctk.CTkFrame(self, fg_color="transparent")
        self.corps.pack(fill="both", expand=True)
        self._styler_boutons()

    def _styler_boutons(self):
        for cle, b in self._boutons.items():
            actif = cle == self.vue
            b.configure(fg_color=C["accent"] if actif else C["inset"],
                        text_color="#f6f2ff" if actif else C["muted"])

    def _changer_vue(self, cle):
        self.vue = cle
        if cle != "semaine":
            self.decalage = 0
        self._styler_boutons()
        self.refresh(force=True)

    # -------------------------------------------------------------- rendu
    def refresh(self, snap=None, force=False):
        if self._charge and not force:
            return
        self._charge = True
        self._largeur_rendue = self._derniere_largeur or self.winfo_width() or 0
        for w in self.corps.winfo_children():
            w.destroy()
        try:
            self._entete()
            getattr(self, f"_vue_{self.vue}")()
        except Exception as exc:
            ctk.CTkLabel(self.corps, text=f"Vue sport indisponible :\n{exc}",
                         text_color=C["red"], justify="left",
                         font=theme.font("body", 12)).pack(pady=20)

    def _sur_redimension(self, event=None):
        """Recalcule la troncature quand la fenêtre change vraiment de taille.

        Piège : re-rendre déclenche un nouveau `<Configure>` (la scrollbar
        apparaît ou disparaît selon la hauteur du contenu, ce qui décale la
        largeur d'une quinzaine de pixels) — et on repart en boucle infinie,
        fenêtre figée. D'où les deux garde-fous : un seuil large, très
        au-dessus de ce que vaut une scrollbar, et un report groupé qui
        n'exécute qu'un seul rendu même si dix événements arrivent pendant un
        redimensionnement à la souris.
        """
        super()._sur_redimension(event)
        largeur = self._derniere_largeur
        if not self._charge or largeur <= 1:
            return
        if abs(largeur - self._largeur_rendue) < 40:
            return
        if self._report is not None:
            self.after_cancel(self._report)
        self._report = self.after(200, self._rendre_apres_resize)

    def _rendre_apres_resize(self):
        self._report = None
        self.refresh(force=True)

    def quitter(self):
        self._charge = False

    # ------------------------------------------------------------ briques
    def _largeur_nom(self, reserve=150) -> int:
        """Combien de caractères tiennent à gauche avant la colonne de droite.

        Les labels CTk ne replient pas : ils coupent net au bord de la carte.
        On coupe donc nous-mêmes, avec des points de suspension, d'après la
        largeur réelle — élargir la fenêtre montre vraiment plus de texte.
        """
        largeur = self._derniere_largeur or self.winfo_width() or 322
        return max(12, int((largeur - reserve) / 7.2))

    @staticmethod
    def _court(texte, largeur) -> str:
        texte = texte or ""
        return texte if len(texte) <= largeur else texte[:largeur - 1].rstrip() + "…"

    def _carte(self, titre, sous=None):
        return theme.section(self.corps, titre, sous)

    def _ligne(self, parent, gauche, droite, couleur=None, indent=0,
               mono_droite=True):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", pady=1)
        # La droite d'abord : avec `pack`, le premier posé garde sa place, et
        # c'est la colonne chiffrée qui ne doit jamais être rognée.
        if droite is not None:
            ctk.CTkLabel(
                f, text=str(droite),
                font=theme.font("mono" if mono_droite else "body", 10),
                text_color=C["muted"]).pack(side="right", padx=(8, 0))
        ctk.CTkLabel(f, text=gauche, font=theme.font("body", 12),
                     text_color=couleur or C["text_norm"], justify="left",
                     anchor="w").pack(side="left", padx=(indent, 0))
        return f

    def _note(self, parent, texte, couleur=None):
        self.replier(ctk.CTkLabel(
            parent, text=texte, text_color=couleur or C["dim"],
            font=theme.font("body", 11), justify="left", anchor="w",
            wraplength=320)).pack(fill="x", pady=(2, 4))

    def _puce(self, parent, texte, couleur):
        """Petite étiquette colorée — statut, lieu, bloc."""
        e = ctk.CTkLabel(parent, text=texte, font=theme.font("head", 9, "bold"),
                         text_color=couleur, fg_color=C["inset"],
                         corner_radius=5, padx=6)
        return e

    # ------------------------------------------------------------- entête
    def _entete(self):
        a = sport.apercu()
        if not a.get("programme"):
            f = self._carte("Aucun programme actif")
            self._note(f, "Le programme a été désactivé : les séances déjà "
                          "enregistrées restent lisibles dans l'historique.")
            return
        sous = f"semaine {a['semaine_programme']}"
        if a["reprise"]:
            sous += " · reprise"
        if a["allegee"]:
            sous += " · allégée"
        f = self._carte(a["programme"], sous)
        self._ligne(f, "Séances faites cette semaine",
                    f"{a['seances_faites']}"
                    + (f" · {a['seances_manquees']} manquée(s)"
                       if a["seances_manquees"] else ""),
                    couleur=C["muted"])
        self._ligne(f, "Séries enregistrées", a["series"], couleur=C["muted"])
        self._ligne(f, "Volume de la semaine", _volume(a["volume"]),
                    couleur=C["muted"])
        streaks = a.get("streaks") or {}
        self._ligne(f, "Série de jours",
                    " · ".join(
                        f"{nom} {(streaks.get(nom) or {}).get('courant', 0)} j"
                        for nom in ("sport", "coreen")),
                    couleur=C["muted"])
        if a.get("note"):
            self._note(f, a["note"])

    # ============================================================ SEMAINE
    def _vue_semaine(self):
        barre = ctk.CTkFrame(self.corps, fg_color="transparent")
        barre.pack(fill="x", pady=(0, 4))
        ctk.CTkButton(barre, text="‹ Semaine précédente", width=140,
                      fg_color=C["inset"], text_color=C["muted"],
                      font=theme.font("body", 11),
                      command=lambda: self._bouger_semaine(-1)).pack(side="left")
        if self.decalage:
            ctk.CTkButton(barre, text="Aujourd'hui", width=90,
                          fg_color=C["inset"], text_color=C["accent_lt"],
                          font=theme.font("body", 11),
                          command=lambda: self._bouger_semaine(None)
                          ).pack(side="left", padx=4)
        ctk.CTkButton(barre, text="Suivante ›", width=90,
                      fg_color=C["inset"], text_color=C["muted"],
                      font=theme.font("body", 11),
                      command=lambda: self._bouger_semaine(1)).pack(side="right")

        jours = sport.semaine_detaillee(decalage=self.decalage)
        for j in jours:
            titre = j["libelle"]
            sous = None
            if j["position"] == "aujourdhui":
                sous = "aujourd'hui"
            elif j["position"] == "futur":
                sous = "à venir"
            f = theme.section(self.corps, titre, sous)
            if not j["seances"]:
                self._note(f, "Repos — rien de prévu.")
                continue
            for s in j["seances"]:
                self._seance_dans_la_semaine(f, s, j["position"])
            if j["series"]:
                self._ligne(f, "Réalisé",
                            f"{j['series']} séries · {_volume(j['volume'])}",
                            couleur=C["green"])

    def _bouger_semaine(self, delta):
        self.decalage = 0 if delta is None else self.decalage + delta
        self.refresh(force=True)

    def _seance_dans_la_semaine(self, parent, s, position):
        entete = ctk.CTkFrame(parent, fg_color="transparent")
        entete.pack(fill="x", pady=(6, 0))
        statut = s.get("statut") or "planifie"
        if position == "futur":
            statut = "planifie"
        self._puce(entete, LIBELLE_STATUT.get(statut, statut),
                   COULEUR_STATUT.get(statut, C["dim"])).pack(side="right")
        ctk.CTkLabel(entete,
                     text=self._court(s["nom"], self._largeur_nom(reserve=110)),
                     font=theme.font("head", 13, "bold"),
                     text_color=C["text"], anchor="w").pack(side="left")

        meta = [s.get("lieu") or "—", f"{s.get('duree_cible_min') or 0} min",
                f"{s.get('faits', 0)}/{s.get('total', 0)} exercices"]
        if s.get("version_courte"):
            meta.append("version courte")
        if s.get("contacts_plyo"):
            meta.append(f"{s['contacts_plyo']}/{s['contacts_max']} contacts plyo")
        self.replier(ctk.CTkLabel(
            parent, text=" · ".join(meta), font=theme.font("body", 11),
            text_color=C["dim"], anchor="w", justify="left",
            wraplength=320), marge=60).pack(fill="x")
        if s.get("plan_course"):
            self._note(parent, f"Course : {s['plan_course']}", C["blue"])

        largeur = self._largeur_nom(reserve=190)
        for e in s.get("exos") or []:
            couleur = C["green"] if e.get("fait") else COULEUR_BLOC.get(
                e.get("bloc"), C["text_norm"])
            droite = e.get("cible") or ""
            if e.get("charge_proposee"):
                droite += f" · {_kg(e['charge_proposee'])}"
            self._ligne(parent,
                        ("✓ " if e.get("fait") else "· ")
                        + self._court(e["nom"], largeur),
                        droite, couleur=couleur, indent=6)

    # =============================================================== EXOS
    def _vue_exos(self):
        groupes = sport.exercices_semaine_par_groupe()
        if not groupes:
            f = self._carte("Exercices")
            self._note(f, "Aucun programme actif : rien à lister.")
            return

        f = self._carte("Volume hebdomadaire", "séries · groupe")
        wrap = ctk.CTkFrame(f, fg_color=C["page"], corner_radius=8,
                            border_color=C["card_border"], border_width=1)
        wrap.pack(fill="x", pady=(2, 6))
        bars = BarChart(wrap, width=300, height=130, bg=C["page"],
                        format_valeur=lambda v: str(int(v)))
        bars.pack(fill="x", padx=6, pady=6)
        bars.set_data([(g["libelle"][:4], g["series_semaine"], 0)
                       for g in groupes])
        total = sum(g["series_semaine"] for g in groupes)
        self._note(f, f"{total} séries par semaine, tous groupes confondus. "
                      f"Les blocs du soir comptent double : trois rotations "
                      f"pour six soirs.")

        for g in groupes:
            f = theme.section(
                self.corps, g["libelle"],
                f"{g['series_semaine']} sér. · {len(g['exercices'])} exos")
            for e in g["exercices"]:
                self._exercice(f, e)

    def _exercice(self, parent, e):
        entete = ctk.CTkFrame(parent, fg_color="transparent")
        entete.pack(fill="x", pady=(6, 0))
        # la colonne de droite est posée en premier : avec `expand=True` à
        # gauche, l'ordre de `pack` décide qui cède la place à l'autre.
        ctk.CTkLabel(entete, text=f"{e['series_semaine']} sér./sem",
                     font=theme.font("mono", 11),
                     text_color=C["accent_lt"]).pack(side="right")
        ctk.CTkLabel(entete,
                     text=self._court(e["nom"], self._largeur_nom(reserve=130)),
                     font=theme.font("body", 12, "bold"),
                     text_color=C["text"], anchor="w").pack(side="left")

        jours = " ".join(o["jour"] for o in e["occurrences"])
        cibles = {f"{o['series']}×{o['reps_min']}"
                  + (f"-{o['reps_max']}" if o.get("reps_max")
                     and o["reps_max"] != o["reps_min"] else "")
                  for o in e["occurrences"] if o.get("reps_min")}
        meta = [jours, e.get("equipement") or "—", e.get("lieu") or "—"]
        if cibles:
            meta.append(" / ".join(sorted(cibles)))
        self.replier(ctk.CTkLabel(
            parent, text=" · ".join(meta), font=theme.font("body", 10),
            text_color=C["dim"], anchor="w", justify="left",
            wraplength=320), marge=60).pack(fill="x")

        reel = []
        if e["series_faites"]:
            reel.append(f"{e['series_faites']} séries faites")
        if e.get("derniere_charge"):
            reel.append(f"dernière {_kg(e['derniere_charge'])}")
        if e.get("record_charge"):
            reel.append(f"record {_kg(e['record_charge'])}")
        if e.get("record_1rm"):
            reel.append(f"1RM ~{_kg(e['record_1rm'])}")
        self.replier(ctk.CTkLabel(
            parent, text=" · ".join(reel) if reel else "jamais enregistré",
            font=theme.font("mono", 10), justify="left",
            text_color=C["green"] if reel else C["dimmer"],
            anchor="w", wraplength=320), marge=60).pack(fill="x")

    # ========================================================== PROGRAMME
    def _vue_programme(self):
        prog = sport.programme_complet()
        if not prog:
            f = self._carte("Programme")
            self._note(f, "Aucun programme actif.")
            return
        for m in prog["modeles"]:
            f = theme.section(self.corps, f"{m['jour_nom']} · {m['nom']}")
            self._ligne(f,
                        f"{m['lieu']} · {m['duree_cible_min']} min · "
                        f"{len(m['exos'])} exercices",
                        f"{m['series_total']} séries", couleur=C["muted"])
            largeur = self._largeur_nom(reserve=195)
            for e in m["exos"]:
                cible = f"{e['series_cible'] or 0}×{e['reps_min'] or '—'}"
                if e.get("reps_max") and e["reps_max"] != e["reps_min"]:
                    cible += f"-{e['reps_max']}"
                if e.get("unite") == "secondes":
                    cible += " s"
                detail = [cible]
                if e.get("charge_depart"):
                    detail.append(_kg(e["charge_depart"]))
                if e.get("repos_sec"):
                    detail.append(f"r{e['repos_sec']}")
                self._ligne(f, "· " + self._court(e["nom"], largeur),
                            " · ".join(detail),
                            couleur=COULEUR_BLOC.get(e.get("bloc"),
                                                     C["text_norm"]),
                            indent=6)

        archives = sport.programmes_archives()
        if archives:
            f = self._carte("Programmes archivés", "conservés")
            for p in archives:
                self._ligne(f, p["nom"],
                            f"{p['seances']} séances · depuis {p['date_debut']}",
                            couleur=C["muted"])
            self._note(f, "Un programme remplacé n'est jamais supprimé : les "
                          "séances déjà faites gardent leur modèle et restent "
                          "lisibles.")

    # ========================================================= HISTORIQUE
    def _vue_historique(self):
        lignes = sport.historique_seances(40)
        if not lignes:
            f = self._carte("Historique")
            self._note(f, "Aucune séance enregistrée pour l'instant.")
            return
        f = self._carte("Historique", f"{len(lignes)} séances")
        for s in lignes:
            entete = ctk.CTkFrame(f, fg_color="transparent")
            entete.pack(fill="x", pady=(6, 0))
            statut = s.get("statut") or "planifie"
            self._puce(entete, LIBELLE_STATUT.get(statut, statut),
                       COULEUR_STATUT.get(statut, C["dim"])).pack(side="right")
            titre = f"{s['date']} · {s['nom'] or 'séance'}"
            ctk.CTkLabel(entete,
                         text=self._court(titre, self._largeur_nom(reserve=115)),
                         font=theme.font("body", 12, "bold"),
                         text_color=C["text"], anchor="w").pack(side="left")

            detail = [s.get("lieu") or "—", _mmss(s.get("duree_s")),
                      f"{s['series']} séries"]
            if s.get("volume"):
                detail.append(_volume(s["volume"]))
            if s.get("rpe"):
                detail.append(f"RPE {s['rpe']}")
            if s.get("source"):
                detail.append(s["source"])
            ctk.CTkLabel(f, text=" · ".join(detail),
                         font=theme.font("mono", 10), text_color=C["dim"],
                         anchor="w").pack(fill="x")
            douleurs = []
            if s.get("douleur_genou"):
                douleurs.append(f"genou {s['douleur_genou']}/10")
            if s.get("douleur_hanche"):
                douleurs.append(f"hanche {s['douleur_hanche']}/10")
            if douleurs:
                ctk.CTkLabel(f, text=" · ".join(douleurs),
                             font=theme.font("mono", 10),
                             text_color=C["orange"], anchor="w").pack(fill="x")
            if s.get("note"):
                self._note(f, s["note"], C["muted"])
