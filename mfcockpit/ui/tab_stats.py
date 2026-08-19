"""Onglet [Stats] — tout ce que la base sait dire, en graphes maison.

Aucun calcul ici : `backend/stats.py` renvoie des lignes déjà agrégées en SQL,
cet onglet ne fait que les tracer (`BarChart`, `LineChart`, `Heatmap`).

Comme les autres onglets, `refresh()` n'est appelé que lorsqu'il est visible —
et il ne recalcule qu'à l'ouverture ou sur demande explicite, pas à chaque tick :
des agrégats sur 12 mois n'ont aucune raison de bouger toutes les secondes.
"""
import tkinter as tk

import customtkinter as ctk

from ..backend import db, stats
from . import theme
from .base import ThemedScroll
from .theme import C
from .widgets import BarChart, Heatmap, LineChart

VUES = [("Sport", "sport"), ("Corps", "corps"), ("Coréen", "coreen")]


def _kilos(total):
    """Le graphe de volume trace des kilos : sans ça il les lisait en minutes."""
    return f"{int(total / 1000)}t" if total >= 1000 else f"{int(total)}"


def _compte(total):
    return str(int(total))


def _mmss(secondes):
    if not secondes:
        return "—"
    secondes = int(secondes)
    return f"{secondes // 60}:{secondes % 60:02d}"


class StatsTab(ThemedScroll):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.vue = "sport"
        self._charge = False
        self._build()

    # ------------------------------------------------------------ montage
    def _build(self):
        barre = ctk.CTkFrame(self, fg_color="transparent")
        barre.pack(fill="x", pady=(0, 8))
        self._boutons = {}
        for i, (libelle, cle) in enumerate(VUES):
            b = ctk.CTkButton(barre, text=libelle, width=70,
                              font=theme.font("head", 11, "bold"),
                              command=lambda c=cle: self._changer_vue(c))
            b.grid(row=0, column=i, padx=2, sticky="ew")
            self._boutons[cle] = b
        ctk.CTkButton(barre, text="↻", width=34, command=lambda: self.refresh(force=True),
                      font=theme.font("head", 13, "bold")).grid(row=0, column=len(VUES),
                                                                padx=(6, 0))
        barre.grid_columnconfigure(tuple(range(len(VUES))), weight=1, uniform="v")

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
        self._styler_boutons()
        self.refresh(force=True)

    # -------------------------------------------------------------- rendu
    def refresh(self, snap=None, force=False):
        # Les agrégats coûtent cher : on ne recalcule qu'à l'ouverture de
        # l'onglet ou sur clic explicite, jamais à chaque tick d'une seconde.
        if self._charge and not force:
            return
        self._charge = True
        for w in self.corps.winfo_children():
            w.destroy()
        try:
            getattr(self, f"_vue_{self.vue}")()
        except Exception as exc:
            ctk.CTkLabel(self.corps, text=f"Statistiques indisponibles :\n{exc}",
                         text_color=C["red"], justify="left",
                         font=theme.font("body", 12)).pack(pady=20)

    def quitter(self):
        """Appelé quand on change d'onglet : la prochaine ouverture recalcule."""
        self._charge = False

    # ------------------------------------------------------------ briques
    def _carte(self, titre, sous=None):
        return theme.section(self.corps, titre, sous)

    def _lignes(self, parent, paires):
        for cle, valeur in paires:
            ligne = ctk.CTkFrame(parent, fg_color="transparent")
            ligne.pack(fill="x", pady=1)
            ctk.CTkLabel(ligne, text=cle, font=theme.font("body", 12),
                         text_color=C["muted"]).pack(side="left")
            ctk.CTkLabel(ligne, text=str(valeur), font=theme.font("mono", 12),
                         text_color=C["text_norm"]).pack(side="right")

    def _cadre_graphe(self, parent, hauteur=140):
        wrap = ctk.CTkFrame(parent, fg_color=C["page"], corner_radius=8,
                            border_color=C["card_border"], border_width=1)
        wrap.pack(fill="x", pady=(2, 6))
        return wrap

    def _vide(self, parent, texte):
        self.replier(ctk.CTkLabel(parent, text=texte, text_color=C["dim"],
                     font=theme.font("body", 11), justify="left",
                     anchor="w", wraplength=300)).pack(fill="x", pady=4)

    # ============================================================== SPORT
    def _vue_sport(self):
        resume = stats.resume_global()
        duree = stats.duree_moyenne()
        f = self._carte("Vue d'ensemble")
        self._lignes(f, [
            ("Séances faites", resume["seances_faites"]),
            ("Séances manquées", resume["seances_manquees"]),
            ("Séries enregistrées", resume["series"]),
            ("Volume total", f"{resume['volume_total']:,.0f} kg".replace(",", " ")),
            ("Durée moyenne", f"{duree['moyenne_min'] or 0:g} min"),
        ])
        for s in stats.streaks():
            self._lignes(f, [(f"Streak {s['domaine']}",
                              f"{s['courant']} j (record {s['record']})")])

        # --- LE graphe : douleurs vs volume jambes ---
        f = self._carte("Douleurs vs volume jambes", "90 j")
        lignes = stats.douleur_vs_volume_jambes(90)
        if not lignes:
            self._vide(f, "Renseigne genou/hanche en fin de séance : la courbe "
                          "se construit toute seule et prévient avant que ça casse.")
        else:
            wrap = self._cadre_graphe(f)
            graphe = LineChart(wrap, width=360, height=160, bg=C["page"])
            graphe.pack(fill="x", padx=6, pady=6)
            volumes = [r["volume_jambes"] or 0 for r in lignes]
            vmax = max(volumes) or 1
            graphe.set_series([
                ("genou", C["red"], [r["genou"] for r in lignes]),
                ("hanche", C["orange"], [r["hanche"] for r in lignes]),
                # volume ramené sur l'échelle 0-10 des douleurs pour superposer
                ("volume jambes", C["accent_lt"],
                 [round(10.0 * v / vmax, 2) for v in volumes]),
            ], labels=[r["date"][5:] for r in lignes], y_min=0, y_max=10)
            self._vide(f, f"Douleurs sur 0-10. Volume jambes normalisé "
                          f"(100 % = {vmax:,.0f} kg).".replace(",", " "))

        # --- volume hebdo ---
        f = self._carte("Volume hebdomadaire", "kg × reps")
        hebdo = stats.volume_hebdo(12)
        if not hebdo:
            self._vide(f, "Pas encore de séance enregistrée.")
        else:
            wrap = self._cadre_graphe(f)
            bars = BarChart(wrap, width=360, height=120, bg=C["page"],
                            format_valeur=_kilos)
            bars.pack(fill="x", padx=6, pady=6)
            bars.set_data([(r["debut"][5:], r["volume"] or 0, 0) for r in hebdo])

        # --- séances / semaine vs objectif ---
        f = self._carte("Séances par semaine", f"objectif {stats.OBJECTIF_SEANCES_SEMAINE}")
        par_sem = stats.seances_par_semaine(12)
        if not par_sem:
            self._vide(f, "Rien à compter pour l'instant.")
        else:
            wrap = self._cadre_graphe(f)
            graphe = LineChart(wrap, width=360, height=130, bg=C["page"])
            graphe.pack(fill="x", padx=6, pady=6)
            graphe.set_series([
                ("faites", C["green"], [r["faites"] for r in par_sem]),
                ("objectif", C["dim"],
                 [stats.OBJECTIF_SEANCES_SEMAINE] * len(par_sem)),
            ], labels=[r["debut"][5:] for r in par_sem], y_min=0)

        # --- volume par groupe ---
        f = self._carte("Volume par groupe", "8 sem.")
        groupes = stats.volume_par_groupe(8)
        if not groupes:
            self._vide(f, "Pas encore de volume chargé.")
        else:
            self._lignes(f, [(g["groupe"] or "—",
                              f"{g['volume']:,.0f} kg · {g['series']} séries"
                              .replace(",", " ")) for g in groupes])

        # --- progression par exercice ---
        f = self._carte("Charge & 1RM", "Epley")
        suivis = stats.exercices_suivis(12)
        if not suivis:
            self._vide(f, "Enregistre des séries chargées pour voir la "
                          "progression exercice par exercice.")
        else:
            self._exo_choisi = suivis[0]["id"]
            noms = [e["nom"] for e in suivis]
            self._exos_map = {e["nom"]: e["id"] for e in suivis}
            menu = ctk.CTkOptionMenu(
                f, values=noms, command=self._changer_exo,
                font=theme.font("body", 12), fg_color=C["inset"],
                button_color=C["accent"], button_hover_color=C["accent_dk"])
            menu.pack(fill="x", pady=(0, 6))
            self._wrap_exo = self._cadre_graphe(f)
            self._graphe_exo = LineChart(self._wrap_exo, width=360, height=130,
                                         bg=C["page"])
            self._graphe_exo.pack(fill="x", padx=6, pady=6)
            self._tracer_exo(suivis[0]["id"])

        # --- records ---
        f = self._carte("Records")
        recs = stats.records(12)
        if not recs:
            self._vide(f, "Aucun record enregistré — ils se posent tout seuls "
                          "en fin de séance.")
        else:
            self._lignes(f, [(f"{r['nom']} · {r['type']}",
                              f"{r['valeur']:g} {r['unite']}") for r in recs])

        # --- assiduité + répartition ---
        f = self._carte("Assiduité mensuelle")
        mois = stats.assiduite_mensuelle(12)
        if not mois:
            self._vide(f, "Pas encore d'historique.")
        else:
            self._lignes(f, [(m["mois"], f"{m['taux']:g} % "
                                         f"({m['faites']}/{m['planifiees']})")
                             for m in mois[::-1]])

        f = self._carte("Répartition")
        lieux = stats.repartition_lieu()
        sources = stats.repartition_source()
        if lieux:
            self._lignes(f, [(f"Lieu · {l['lieu']}", l["n"]) for l in lieux])
        if sources:
            self._lignes(f, [(f"Saisie · {'téléphone' if s['source'] == 'tel' else 'PC'}",
                              s["n"]) for s in sources])
        if not lieux and not sources:
            self._vide(f, "Rien à répartir pour l'instant.")

        # --- plyo ---
        f = self._carte("Contacts plyo", "/ semaine")
        plyo = stats.contacts_plyo_hebdo(12)
        if not plyo:
            self._vide(f, "Aucun contact plyo enregistré.")
        else:
            wrap = self._cadre_graphe(f)
            bars = BarChart(wrap, width=360, height=110, bg=C["page"],
                            format_valeur=_compte)
            bars.pack(fill="x", padx=6, pady=6)
            bars.set_data([(r["debut"][5:], r["contacts"] or 0, 0) for r in plyo])

        # --- heatmap 12 mois ---
        f = self._carte("Calendrier", "12 mois")
        wrap = self._cadre_graphe(f)
        heat = Heatmap(wrap, width=360, height=104, bg=C["page"])
        heat.pack(fill="x", padx=6, pady=6)
        heat.set_data(stats.heatmap(365))

        # --- cardio ---
        f = self._carte("Cardio")
        cr = stats.cardio_resume()
        if not cr or not cr.get("sorties"):
            self._vide(f, "Pas encore de sortie enregistrée.")
        else:
            allure = cr.get("allure_moyenne")
            self._lignes(f, [
                ("Sorties", cr["sorties"]),
                ("Distance cumulée", f"{cr['distance_totale'] or 0:g} km"),
                ("Temps total", f"{cr['heures'] or 0:g} h"),
                ("Allure moyenne", f"{_mmss(allure)} /km" if allure else "—"),
                ("Meilleur 5 km", _mmss(cr.get("meilleur_5k"))),
            ])
            prog = stats.cardio_progression(30)
            if len(prog) > 1:
                wrap = self._cadre_graphe(f)
                graphe = LineChart(wrap, width=360, height=120, bg=C["page"])
                graphe.pack(fill="x", padx=6, pady=6)
                graphe.set_series([("allure s/km", C["blue"],
                                    [r["allure_s_km"] for r in prog])],
                                  labels=[r["date"][5:] for r in prog])
            par_type = stats.cardio_par_type()
            if par_type:
                self._lignes(f, [(t["type"], f"{t['n']} · {t['heures']:g} h")
                                 for t in par_type])

    def _changer_exo(self, nom):
        self._tracer_exo(self._exos_map.get(nom))

    def _tracer_exo(self, exercice_id):
        if not exercice_id:
            return
        lignes = stats.progression_exercice(exercice_id, 40)
        self._graphe_exo.set_series([
            ("charge max", C["accent_lt"], [r["charge_max"] for r in lignes]),
            ("1RM Epley", C["green"], [r["rm_estime"] for r in lignes]),
        ], labels=[r["date"][5:] for r in lignes], y_min=0)

    # ============================================================== CORPS
    def _vue_corps(self):
        f = self._carte("Poids & mensurations")
        lignes = stats.mesures(120)
        if not lignes:
            self._vide(f, "Aucune mesure. Ajoute-en une ci-dessous : la courbe "
                          "et la moyenne glissante 7 jours se tracent ensuite "
                          "toutes seules.")
        else:
            wrap = self._cadre_graphe(f)
            graphe = LineChart(wrap, width=360, height=150, bg=C["page"])
            graphe.pack(fill="x", padx=6, pady=6)
            graphe.set_series([
                ("poids", C["accent_lt"], [r["poids_kg"] for r in lignes]),
                ("moy. 7 j", C["green"], [r["poids_moy7"] for r in lignes]),
            ], labels=[r["date"][5:] for r in lignes])
            derniere = lignes[-1]
            self._lignes(f, [
                ("Dernier poids", f"{derniere['poids_kg'] or 0:g} kg"),
                ("Taille", f"{derniere['tour_taille'] or 0:g} cm"),
                ("Bras", f"{derniere['tour_bras'] or 0:g} cm"),
                ("Cuisse", f"{derniere['tour_cuisse'] or 0:g} cm"),
            ])
            wrap2 = self._cadre_graphe(f)
            graphe2 = LineChart(wrap2, width=360, height=130, bg=C["page"])
            graphe2.pack(fill="x", padx=6, pady=6)
            graphe2.set_series([
                ("taille", C["orange"], [r["tour_taille"] for r in lignes]),
                ("bras", C["blue"], [r["tour_bras"] for r in lignes]),
                ("cuisse", C["pink"], [r["tour_cuisse"] for r in lignes]),
            ], labels=[r["date"][5:] for r in lignes])

        f = self._carte("Nouvelle mesure")
        self._champs_mesure = {}
        for cle, libelle in (("poids_kg", "Poids (kg)"),
                             ("tour_taille", "Taille (cm)"),
                             ("tour_bras", "Bras (cm)"),
                             ("tour_cuisse", "Cuisse (cm)")):
            ligne = ctk.CTkFrame(f, fg_color="transparent")
            ligne.pack(fill="x", pady=2)
            ctk.CTkLabel(ligne, text=libelle, font=theme.font("body", 12),
                         text_color=C["muted"]).pack(side="left")
            e = ctk.CTkEntry(ligne, width=76, font=theme.font("mono", 12))
            e.pack(side="right")
            self._champs_mesure[cle] = e
        theme.primary_button(f, "Enregistrer la mesure du jour",
                             self._enregistrer_mesure).pack(fill="x", pady=(8, 0))

    def _enregistrer_mesure(self):
        from ..backend import jour
        valeurs = {}
        for cle, champ in self._champs_mesure.items():
            texte = (champ.get() or "").replace(",", ".").strip()
            try:
                valeurs[cle] = float(texte) if texte else None
            except ValueError:
                valeurs[cle] = None
        if not any(v is not None for v in valeurs.values()):
            return
        db.execute(
            "INSERT INTO mesure(date, poids_kg, tour_taille, tour_bras, "
            "tour_cuisse) VALUES (?,?,?,?,?) "
            "ON CONFLICT(date) DO UPDATE SET poids_kg = excluded.poids_kg, "
            "tour_taille = excluded.tour_taille, tour_bras = excluded.tour_bras, "
            "tour_cuisse = excluded.tour_cuisse",
            (jour.jour_courant(), valeurs["poids_kg"], valeurs["tour_taille"],
             valeurs["tour_bras"], valeurs["tour_cuisse"]))
        self.app.show_banner("Mesure enregistrée.")
        self.refresh(force=True)

    # ============================================================= CORÉEN
    def _vue_coreen(self):
        etat = stats.coreen_etat()
        temps = stats.coreen_temps_cumule()
        f = self._carte("Deck")
        self._lignes(f, [
            ("Cartes", etat.get("cartes") or 0),
            ("Neuves", etat.get("neuves") or 0),
            ("En cours", etat.get("en_cours") or 0),
            ("Matures (≥ 21 j)", etat.get("matures") or 0),
            ("Verrouillées (FR→KR)", etat.get("suspendues") or 0),
            ("Révisions", temps.get("revues") or 0),
            ("Temps cumulé", f"{temps.get('minutes') or 0:g} min"),
        ])

        f = self._carte("Taux de réussite", "30 jours")
        par_jour = stats.coreen_reussite_par_jour(30)
        if not par_jour:
            self._vide(f, "Aucune révision enregistrée.")
        else:
            wrap = self._cadre_graphe(f)
            graphe = LineChart(wrap, width=360, height=130, bg=C["page"])
            graphe.pack(fill="x", padx=6, pady=6)
            graphe.set_series([("% réussite", C["green"],
                                [r["taux"] for r in par_jour])],
                              labels=[r["jour"][5:] for r in par_jour],
                              y_min=0, y_max=100)
        directions = stats.coreen_reussite_par_direction()
        if directions:
            self._lignes(f, [
                ("KR→FR" if d["direction"] == "kr_fr" else "FR→KR",
                 f"{d['taux']:g} % ({d['sues']}/{d['vues']})")
                for d in directions])

        f = self._carte("Programme 9 semaines")
        for s in stats.coreen_avancement_semaines():
            total = s["cartes"] or 0
            vues = s["vues"] or 0
            ligne = ctk.CTkFrame(f, fg_color="transparent")
            ligne.pack(fill="x", pady=2)
            ctk.CTkLabel(ligne, text=f"S{s['numero']} · {(s['theme'] or '')[:22]}",
                         font=theme.font("body", 11), anchor="w",
                         text_color=C["text_norm"]).pack(side="left")
            ctk.CTkLabel(ligne, text=f"{vues}/{total}", font=theme.font("mono", 11),
                         text_color=C["accent_lt2"]).pack(side="right")
            jauge = tk.Canvas(f, height=6, highlightthickness=0, bg=C["card"])
            jauge.pack(fill="x", pady=(0, 4))
            jauge.update_idletasks()
            largeur = max(jauge.winfo_width(), 280)
            jauge.create_rectangle(0, 0, largeur, 6, fill=C["inset"], outline="")
            if total:
                jauge.create_rectangle(0, 0, largeur * vues / total, 6,
                                       fill=C["accent_lt"], outline="")

        f = self._carte("Bêtes noires", "top 10")
        noires = stats.coreen_betes_noires(10)
        if not noires:
            self._vide(f, "Aucune carte problématique — pour l'instant.")
        else:
            self._lignes(f, [
                (f"{n['kr']} → {(n['fr'] or '')[:18]}",
                 f"{n['ratees']}/{n['vues']} ratées") for n in noires])

        f = self._carte("Cartes dues", "30 j")
        prev = stats.coreen_previsions(30)
        if not prev:
            self._vide(f, "Rien de prévu — le deck est peut-être vide.")
        else:
            wrap = self._cadre_graphe(f)
            bars = BarChart(wrap, width=360, height=110, bg=C["page"],
                            format_valeur=_compte)
            bars.pack(fill="x", padx=6, pady=6)
            bars.set_data([(r["jour"][5:], r["nb"], 0) for r in prev])
