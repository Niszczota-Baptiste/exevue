# -*- coding: utf-8 -*-
"""Tests du domaine sport / coréen — aucune dépendance, `unittest` suffit.

    python -m unittest discover -s tests -v

Ils couvrent ce qui casse silencieusement si on n'y prend pas garde :

- migrations **rejouées deux fois** (idempotence du schéma et des seeds) ;
- **sync idempotente** : rejouer la file du téléphone ne duplique rien ;
- moteur de progression : montée, stagnation, descente, échelle de variantes ;
- calcul des **streaks autour du seuil de 4 h du matin** ;
- matérialisation d'un jour **sans programme actif**.

Chaque test travaille sur une base temporaire : rien ne touche `cockpit.db`.
"""
import datetime as _dt
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mfcockpit.backend import (api, db, jour, korean, progression,  # noqa: E402
                               rappels, seed_coreen, sport, stats)


def _decale_jour(date_str, jours):
    return (_dt.date.fromisoformat(date_str) + _dt.timedelta(days=jours)).isoformat()


def _premier(date_debut, jour_cible):
    """Le premier `jour_cible` (1 = lundi … 7 = dimanche) à partir du début.

    Les tests qui parlent de « lundi » ou de « mercredi » se calaient sur
    `date_debut_programme() + n jours`, ce qui ne vaut que si le programme a
    démarré un lundi — donc un jour sur sept. Ils échouaient les six autres.
    """
    d = date_debut
    while d.weekday() + 1 != jour_cible:
        d += _dt.timedelta(days=1)
    return d.isoformat()


class BaseTemporaire(unittest.TestCase):
    """Une base neuve, migrée, par test."""

    def setUp(self):
        self._fd, self._chemin = tempfile.mkstemp(suffix=".db")
        os.close(self._fd)
        os.unlink(self._chemin)
        db.set_path(self._chemin)
        db.migrate()

    def tearDown(self):
        db.close()
        for suffixe in ("", "-wal", "-shm"):
            try:
                os.unlink(self._chemin + suffixe)
            except OSError:
                pass

    # --- utilitaires partagés ---
    def _seance_du_jour(self, date_str):
        etat = jour.etat_jour(date_str)
        return etat, (etat["seances"][0] if etat["seances"] else None)

    def _valider_journee(self, date_str):
        jour.materialiser(date_str)
        for domaine in jour.DOMAINES_SPORT + (jour.DOMAINE_COREEN,):
            jour.cocher_domaine(date_str, domaine, fait=True)


# =====================================================================
class TestMigrations(BaseTemporaire):

    def test_migrations_rejouees_deux_fois(self):
        """`migrate()` doit être idempotent : rien ne double, rien ne casse."""
        derniere = max(v for v, _l, _f in db.MIGRATIONS)
        avant = {t: db.scalar(f"SELECT COUNT(*) FROM {t}", default=0)
                 for t in ("exercice", "programme", "seance_modele",
                           "seance_modele_exo", "kr_semaine", "kr_item",
                           "kr_carte", "kr_exercice")}
        self.assertEqual(db.migrate(), derniere)
        self.assertEqual(db.migrate(), derniere)   # et une troisième pour la route
        apres = {t: db.scalar(f"SELECT COUNT(*) FROM {t}", default=0)
                 for t in avant}
        self.assertEqual(avant, apres)

    def test_seed_coherent(self):
        self.assertGreater(db.scalar("SELECT COUNT(*) FROM exercice"), 50)
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM kr_semaine"), 9)
        # 20-25 items utiles par semaine, dialogues en plus
        for numero in range(1, 10):
            n = db.scalar(
                "SELECT COUNT(*) FROM kr_item i JOIN kr_semaine s "
                "ON s.id = i.semaine_id WHERE s.numero = ? "
                "AND i.type IN ('vocab', 'phrase')", (numero,))
            self.assertGreaterEqual(n, 20, f"semaine {numero} : {n} items")
        # chaque item cartable porte bien deux cartes, la seconde verrouillée
        orphelins = db.scalar(
            "SELECT COUNT(*) FROM kr_item i WHERE i.type <> 'dialogue' "
            "AND (SELECT COUNT(*) FROM kr_carte c WHERE c.item_id = i.id) <> 2")
        self.assertEqual(orphelins, 0)
        self.assertGreater(
            db.scalar("SELECT COUNT(*) FROM kr_carte "
                      "WHERE direction = 'fr_kr' AND suspendu = 1"), 0)

    def test_migration_deck_legacy(self):
        """Le deck JSON historique est repris **sans perdre les échéances**."""
        echeance = time.time() + 12345.0

        class ConfigFactice:
            def get(self, cle, defaut=None):
                if cle != "korean.deck":
                    return defaut
                return [{"kr": "고양이", "romaja": "goyangi", "fr": "chat",
                         "example": "고양이가 귀여워요.", "due": echeance,
                         "interval": 86400.0, "ease": 2.7, "reps": 4,
                         "history": [{"t": 1700000000, "knew": True}]}]

        importes = db.migrer_deck_legacy(ConfigFactice())
        self.assertEqual(importes, 1)
        carte = db.q1(
            "SELECT c.* FROM kr_carte c JOIN kr_item i ON i.id = c.item_id "
            "WHERE i.kr = ? AND c.direction = 'kr_fr'", ("고양이",))
        self.assertAlmostEqual(carte["due"], echeance, places=3)
        self.assertEqual(carte["reps"], 4)
        self.assertAlmostEqual(carte["ease"], 2.7, places=3)
        # 4 réussites >= 3 : la direction inverse est déjà ouverte
        inverse = db.q1(
            "SELECT c.suspendu FROM kr_carte c JOIN kr_item i ON i.id = c.item_id "
            "WHERE i.kr = ? AND c.direction = 'fr_kr'", ("고양이",))
        self.assertEqual(inverse["suspendu"], 0)
        # rejouée, la migration ne réimporte rien
        self.assertEqual(db.migrer_deck_legacy(ConfigFactice()), 0)
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM kr_item "
                                   "WHERE source = 'legacy'"), 1)


# =====================================================================
class TestSyncIdempotente(BaseTemporaire):

    def test_rejeu_de_la_file_ne_duplique_rien(self):
        date_str = jour.jour_courant()
        etat, seance = self._seance_du_jour(date_str)
        self.assertIsNotNone(seance)
        exo = seance["exos"][-1]

        ops = [
            {"uuid": "op-serie", "table": "serie", "ts": int(time.time()),
             "payload": {"seance_id": seance["seance_id"],
                         "exercice_id": exo["exercice_id"], "index_serie": 1,
                         "reps": 10, "charge_kg": 12.0, "rpe": 8}},
            {"uuid": "op-cardio", "table": "cardio", "ts": int(time.time()),
             "payload": {"date": date_str, "type": "foot_salle",
                         "duree_s": 3600, "ressenti": 7}},
            {"uuid": "op-tache", "table": "tache_jour", "ts": int(time.time()),
             "payload": {"id": etat["coreen"]["checklist"][0]["id"],
                         "fait": True}},
        ]
        premier = api.sync(ops)
        self.assertEqual(premier["appliquees"], 3)
        self.assertEqual(premier["erreurs"], [])

        for _ in range(3):                      # « synchroniser » en boucle
            suivant = api.sync(ops)
            self.assertEqual(suivant["appliquees"], 0)
            self.assertEqual(suivant["ignorees"], 3)

        self.assertEqual(db.scalar("SELECT COUNT(*) FROM serie"), 1)
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM cardio"), 1)
        self.assertEqual(db.scalar("SELECT source FROM serie"), "tel")

    def test_conflit_sur_la_meme_place_le_plus_recent_gagne(self):
        """(séance, exercice, index) déjà pris : c'est le `ts` qui tranche."""
        date_str = jour.jour_courant()
        _etat, seance = self._seance_du_jour(date_str)
        exo = seance["exos"][-1]
        base = time.time()

        jour.enregistrer_serie(seance["seance_id"], exo["exercice_id"], 1,
                               reps=8, charge_kg=10.0, ts=base, uid="a")
        # plus récent : il écrase
        jour.enregistrer_serie(seance["seance_id"], exo["exercice_id"], 1,
                               reps=12, charge_kg=14.0, ts=base + 60, uid="b")
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM serie"), 1)
        self.assertEqual(db.scalar("SELECT reps FROM serie"), 12)
        # plus ancien : il est ignoré
        jour.enregistrer_serie(seance["seance_id"], exo["exercice_id"], 1,
                               reps=3, charge_kg=5.0, ts=base - 60, uid="c")
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM serie"), 1)
        self.assertEqual(db.scalar("SELECT reps FROM serie"), 12)

    def test_table_refusee(self):
        rep = api.sync([{"uuid": "x", "table": "exercice", "payload": {}}])
        self.assertEqual(rep["appliquees"], 0)
        self.assertEqual(len(rep["erreurs"]), 1)

    def test_revue_coreen_idempotente(self):
        carte = korean.cartes_dues(limite=1)[0]
        korean.noter(carte["id"], True, uid="revue-1")
        korean.noter(carte["id"], True, uid="revue-1")
        korean.noter(carte["id"], True, uid="revue-1")
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM kr_revue "
                                   "WHERE uuid = 'revue-1'"), 1)
        self.assertEqual(db.scalar("SELECT reps FROM kr_carte WHERE id = ?",
                                   (carte["id"],)), 1)


# =====================================================================
class TestProgression(BaseTemporaire):

    def _exo_et_modele(self, code):
        exo = db.q1("SELECT * FROM exercice WHERE code = ?", (code,))
        modele = db.q1(
            "SELECT * FROM seance_modele_exo WHERE exercice_id = ? LIMIT 1",
            (exo["id"],))
        return exo, modele

    def _seance_factice(self, date_str, exercice_id, series, statut="fait"):
        uid = f"test-{date_str}-{exercice_id}"
        db.execute("INSERT INTO seance(uuid, date, statut) VALUES (?,?,?)",
                   (uid, date_str, statut))
        seance_id = db.scalar("SELECT id FROM seance WHERE uuid = ?", (uid,))
        for i, (reps, charge, rpe) in enumerate(series, start=1):
            jour.enregistrer_serie(seance_id, exercice_id, i, reps=reps,
                                   charge_kg=charge, rpe=rpe,
                                   ts=time.mktime(_dt.date.fromisoformat(
                                       date_str).timetuple()))
        return seance_id

    def test_montee_quand_la_fourchette_haute_est_bouclee(self):
        exo, modele = self._exo_et_modele("chest_press")   # 8-12, chargeable
        self._seance_factice("2026-01-05", exo["id"],
                             [(12, 30.0, 8), (12, 30.0, 8), (12, 30.0, 8)])
        reco = progression.evaluer(exo, modele)
        self.assertEqual(reco["action"], "monter")
        self.assertAlmostEqual(reco["charge"], 32.5)

    def test_pas_de_montee_si_la_derniere_serie_part_a_l_echec(self):
        """« 1 à 2 reps en réserve » : à l'échec, on ne monte pas."""
        exo, modele = self._exo_et_modele("chest_press")
        self._seance_factice("2026-01-05", exo["id"],
                             [(12, 30.0, 8), (12, 30.0, 8), (12, 30.0, 10)])
        reco = progression.evaluer(exo, modele)
        self.assertEqual(reco["action"], "tenir")
        self.assertAlmostEqual(reco["charge"], 30.0)

    def test_stagnation_dans_la_fourchette(self):
        exo, modele = self._exo_et_modele("chest_press")
        self._seance_factice("2026-01-05", exo["id"],
                             [(10, 30.0, 8), (10, 30.0, 8), (9, 30.0, 8)])
        reco = progression.evaluer(exo, modele)
        self.assertEqual(reco["action"], "tenir")
        self.assertAlmostEqual(reco["charge"], 30.0)

    def test_descente_apres_deux_seances_sous_le_plancher(self):
        exo, modele = self._exo_et_modele("chest_press")   # plancher 8
        self._seance_factice("2026-01-05", exo["id"],
                             [(7, 30.0, 9), (6, 30.0, 9)])
        self._seance_factice("2026-01-12", exo["id"],
                             [(6, 30.0, 9), (5, 30.0, 9)])
        reco = progression.evaluer(exo, modele)
        self.assertEqual(reco["action"], "descendre")
        self.assertAlmostEqual(reco["charge"], 27.5)

    def test_echelle_de_variantes_a_la_maison(self):
        """Plafond des kettlebells : c'est la variante qui progresse."""
        exo, modele = self._exo_et_modele("pompes")        # non chargeable
        variantes = progression._variantes(exo)
        self.assertIn("Standard", variantes)
        haut = modele["reps_max"]
        # une seule séance au sommet : on consolide
        self._seance_factice("2026-01-05", exo["id"],
                             [(haut, None, 8)] * 3)
        self.assertEqual(progression.evaluer(exo, modele)["action"], "tenir")
        # deux d'affilée : palier suivant
        self._seance_factice("2026-01-12", exo["id"],
                             [(haut, None, 8)] * 3)
        reco = progression.evaluer(exo, modele)
        self.assertEqual(reco["action"], "variante")
        self.assertEqual(reco["variante"], variantes[1])

    def test_charge_proposee_vient_de_la_derniere_seance_pas_du_modele(self):
        exo, modele = self._exo_et_modele("goblet_squat")   # charge_depart 12
        self.assertEqual(modele["charge_depart"], 12)
        self._seance_factice("2026-01-05", exo["id"], [(10, 16.0, 8)])
        self.assertEqual(progression.derniere_charge(exo["id"]), 16.0)
        self.assertEqual(progression.evaluer(exo, modele)["charge"], 16.0)

    def test_epley(self):
        self.assertAlmostEqual(progression.epley(100, 0), 0.0)
        self.assertAlmostEqual(progression.epley(60, 10), 80.0)
        self.assertAlmostEqual(progression.epley(0, 10), 0.0)

    def test_regle_douleur(self):
        db.execute("INSERT INTO seance(uuid, date, statut, douleur_genou, "
                   "douleur_hanche) VALUES ('d1', ?, 'fait', 5, 1)",
                   (jour.jour_courant(),))
        alerte = progression.alerte_douleur()
        self.assertTrue(alerte["adapter"])
        self.assertIn("vélo", alerte["message"])

    def test_plafond_de_contacts_plyo(self):
        """60 contacts par séance, quelle que soit la semaine du programme."""
        debut = progression.date_debut_programme()
        vu = 0
        for semaine in range(0, 9):
            for jsem in range(7):
                d = (debut + _dt.timedelta(weeks=semaine, days=jsem)).isoformat()
                etat = jour.etat_jour(d, materialise=False)
                for seance in etat["seances"]:
                    if seance["contacts_plyo"]:
                        vu += 1
                    self.assertLessEqual(
                        seance["contacts_plyo"], progression.CONTACTS_MAX,
                        f"{d} : {seance['contacts_plyo']} contacts")
        self.assertGreater(vu, 0, "aucune séance plyo trouvée dans le programme")

    def test_reprise_et_semaine_allegee(self):
        debut = progression.date_debut_programme()
        s1 = debut.isoformat()
        s6 = (debut + _dt.timedelta(weeks=5)).isoformat()
        self.assertTrue(progression.est_reprise(s1))
        self.assertFalse(progression.est_reprise(s6))
        self.assertTrue(progression.est_semaine_allegee(s6))
        self.assertLess(progression.series_ajustees(4, s6),
                        progression.series_ajustees(4, s1) + 1)


# =====================================================================
class TestStreaks(BaseTemporaire):

    def test_bascule_a_quatre_heures_du_matin(self):
        """Une séance à 1 h du matin compte pour la veille."""
        def horodatage(jour_, heure, minute=0):
            return time.mktime(_dt.datetime(2026, 3, jour_, heure, minute)
                               .timetuple())

        self.assertEqual(jour.jour_courant(horodatage(10, 23, 59)), "2026-03-10")
        self.assertEqual(jour.jour_courant(horodatage(11, 0, 30)), "2026-03-10")
        self.assertEqual(jour.jour_courant(horodatage(11, 3, 59)), "2026-03-10")
        self.assertEqual(jour.jour_courant(horodatage(11, 4, 0)), "2026-03-11")
        self.assertEqual(jour.jour_courant(horodatage(11, 4, 1)), "2026-03-11")

    def test_streaks_independants(self):
        jours = ["2026-03-09", "2026-03-10", "2026-03-11"]
        for d in jours:
            self._valider_journee(d)
        etat = jour.recalc_streaks(jours[-1])
        self.assertEqual(etat["sport"]["courant"], 3)
        self.assertEqual(etat["coreen"]["courant"], 3)

        # on casse UNIQUEMENT le sport au milieu : le coréen n'y touche pas
        jour.cocher_domaine(jours[1], "sport", fait=False)
        etat = jour.recalc_streaks(jours[-1])
        self.assertEqual(etat["sport"]["courant"], 1)
        self.assertEqual(etat["sport"]["record"], 3)     # le record survit
        self.assertEqual(etat["coreen"]["courant"], 3)

    def test_le_jour_meme_n_est_jamais_marque_manque(self):
        """Une journée commencée est « en cours », pas ratée."""
        aujourdhui = jour.jour_courant()
        jour.materialiser(aujourdhui)
        cellule = next(c for c in jour.semaine(aujourdhui)
                       if c["date"] == aujourdhui)
        self.assertTrue(cellule["aujourdhui"])
        self.assertEqual(cellule["sport"], "encours")
        self.assertEqual(cellule["coreen"], "encours")
        # une seule tâche cochée -> partiel, toujours pas manqué
        jour.cocher(db.q1("SELECT id FROM tache_jour WHERE date = ? "
                          "AND domaine = 'coreen'", (aujourdhui,))["id"], True)
        cellule = next(c for c in jour.semaine(aujourdhui)
                       if c["date"] == aujourdhui)
        self.assertEqual(cellule["coreen"], "partiel")
        # en revanche, une journée passée non faite reste bien manquée
        hier = _decale_jour(aujourdhui, -1)
        jour.materialiser(hier)
        cellule = next((c for c in jour.semaine(hier) if c["date"] == hier), None)
        if cellule:                       # hier peut tomber sur la semaine d'avant
            self.assertEqual(cellule["sport"], "manque")

    def test_journee_en_cours_ne_casse_pas_la_serie(self):
        """Tant que la journée n'est pas finie, elle ne compte pas contre toi."""
        self._valider_journee("2026-03-09")
        self._valider_journee("2026-03-10")
        jour.materialiser("2026-03-11")          # aujourd'hui, rien de coché
        etat = jour.recalc_streaks("2026-03-11")
        self.assertEqual(etat["sport"]["courant"], 2)

    def test_seance_manquee_reste_manquee(self):
        date_str = "2026-03-12"
        etat = jour.etat_jour(date_str)
        seance = etat["seances"][0]
        jour.marquer_manquee(seance["seance_id"])
        self.assertEqual(
            db.scalar("SELECT statut FROM seance WHERE id = ?",
                      (seance["seance_id"],)), "manque")
        # rien n'est replanifié le lendemain
        lendemain = jour.etat_jour("2026-03-13")
        self.assertTrue(all(s["statut"] != "manque"
                            for s in lendemain["seances"]))
        self.assertFalse(jour.domaine_valide("sport", date_str))

    def test_jour_de_repos_valide_par_le_bloc_prehab(self):
        """Mercredi : pas de muscu, le sport se valide sur prehab + core."""
        mercredi = _premier(progression.date_debut_programme(), 3)
        etat = jour.etat_jour(mercredi)
        domaines = {t["domaine"] for t in
                    db.q("SELECT DISTINCT domaine FROM tache_jour WHERE date = ?",
                         (mercredi,))}
        self.assertIn("prehab", domaines)
        self.assertNotIn("sport", domaines)
        for domaine in jour.DOMAINES_SPORT:
            jour.cocher_domaine(mercredi, domaine, fait=True)
        self.assertTrue(jour.domaine_valide("sport", mercredi))


# =====================================================================
class TestProgrammeV2(BaseTemporaire):
    """La v2 recentre sur bras / abdos / dos ; les jambes servent foot-basket."""

    def _modeles(self):
        prog = jour.programme_actif()
        return db.q("SELECT * FROM seance_modele WHERE programme_id = ? "
                    "ORDER BY jour_semaine, ordre_affichage", (prog["id"],))

    def test_programme_v2_est_actif_et_ancien_archive(self):
        self.assertEqual(jour.programme_actif()["nom"], "Haut du corps & abdos")
        # un seul programme actif à la fois, mais l'ancien reste en base pour
        # que les séances déjà faites gardent leur modèle
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM programme WHERE actif = 1"), 1)
        self.assertGreaterEqual(db.scalar("SELECT COUNT(*) FROM programme"), 2)

    def test_le_haut_du_corps_domine_le_volume(self):
        """Bras + dos + épaules + pecs doivent peser plus que les jambes."""
        volume = {}
        for m in self._modeles():
            for l in db.q(
                    "SELECT e.groupe, sme.series_cible FROM seance_modele_exo sme "
                    "JOIN exercice e ON e.id = sme.exercice_id "
                    "WHERE sme.seance_modele_id = ? AND e.categorie = 'force'",
                    (m["id"],)):
                volume[l["groupe"]] = volume.get(l["groupe"], 0) + (l["series_cible"] or 0)
        haut = sum(volume.get(g, 0) for g in ("bras", "dos", "epaules", "pectoraux"))
        jambes = sum(volume.get(g, 0)
                     for g in ("quadriceps", "ischios", "fessiers", "mollets"))
        self.assertGreater(haut, jambes,
                           f"haut={haut} séries vs jambes={jambes} séries")
        self.assertGreater(volume.get("bras", 0), 0)

    def test_bloc_du_soir_que_des_abdos(self):
        blocs = [m for m in self._modeles() if m["jour_semaine"] == 0]
        self.assertEqual(len(blocs), 3, "rotation A/B/C attendue")
        for bloc in blocs:
            self.assertEqual(bloc["duree_cible_min"], 15)
            groupes = db.q(
                "SELECT DISTINCT e.groupe FROM seance_modele_exo sme "
                "JOIN exercice e ON e.id = sme.exercice_id "
                "WHERE sme.seance_modele_id = ?", (bloc["id"],))
            self.assertEqual({g["groupe"] for g in groupes}, {"abdos"},
                             f"{bloc['nom']} contient autre chose que des abdos")
            n = db.scalar("SELECT COUNT(*) FROM seance_modele_exo "
                          "WHERE seance_modele_id = ?", (bloc["id"],))
            self.assertGreaterEqual(n, 5, f"{bloc['nom']} : {n} exercices")

    def test_version_courte_garde_trois_exercices(self):
        """Les soirs de grosse journée, 15 min d'abdos ne tombent pas à un exo."""
        debut = progression.date_debut_programme()
        lundi = _premier(debut, 1)                     # jour lourd
        mercredi = _premier(debut, 3)                  # jour léger
        court = jour.etat_jour(lundi)["core"]
        complet = jour.etat_jour(mercredi)["core"]
        self.assertTrue(court["version_courte"])
        self.assertEqual(court["total"], 3)
        self.assertFalse(complet["version_courte"])
        self.assertGreaterEqual(complet["total"], 5)

    def test_les_lieux_imposes_sont_respectes(self):
        """Maison lundi/jeudi, salle mardi/vendredi : contrainte d'agenda."""
        attendu = {1: "maison", 2: "salle", 4: "maison", 5: "salle"}
        lieux = {m["jour_semaine"]: m["lieu"] for m in self._modeles()
                 if m["jour_semaine"] in attendu and m["type"] != "core"}
        self.assertEqual(lieux, attendu)

    def test_les_jours_maison_ne_demandent_aucune_machine(self):
        """Un lieu « maison » qui réclame une poulie serait un lieu faux."""
        for m in self._modeles():
            if m["lieu"] != "maison":
                continue
            salle = db.q(
                "SELECT e.nom FROM seance_modele_exo sme "
                "JOIN exercice e ON e.id = sme.exercice_id "
                "WHERE sme.seance_modele_id = ? AND e.lieu = 'salle'",
                (m["id"],))
            self.assertEqual(
                [], [r["nom"] for r in salle],
                f"{m['nom']} est à la maison mais demande du matériel de salle")

    def test_la_plyometrie_reste_en_tete_de_seance(self):
        for m in self._modeles():
            lignes = db.q(
                "SELECT sme.bloc, e.categorie FROM seance_modele_exo sme "
                "JOIN exercice e ON e.id = sme.exercice_id "
                "WHERE sme.seance_modele_id = ? ORDER BY sme.ordre", (m["id"],))
            blocs = [l["bloc"] for l in lignes]
            for i, l in enumerate(lignes):
                if l["categorie"] == "plyo":
                    self.assertEqual(l["bloc"], "explosif", m["nom"])
                    # rien de « principal » ne doit précéder un exo explosif
                    self.assertNotIn("principal", blocs[:i], m["nom"])


class TestMigration6SurBaseExistante(unittest.TestCase):
    """Le cas qui compte : une base **déjà installée**, pas une base neuve.

    `seed()` s'arrête si le programme existe déjà. Une base à jour du schéma v5
    doit donc être réalignée par la migration 6, sinon seule une réinstallation
    verrait les nouveaux lieux — et le test sur base neuve passerait au vert
    sans rien prouver.
    """

    ANCIENS_EXOS_JEUDI = [
        "velo", "rowing_kb_uni", "tirage_vertical", "curl_poulie_basse",
        "extension_triceps_poulie", "curl_inverse", "kickback_triceps",
        "elevations_lat_poulie", "suitcase_carry",
    ]

    def setUp(self):
        self._fd, self._chemin = tempfile.mkstemp(suffix=".db")
        os.close(self._fd)
        os.unlink(self._chemin)
        db.set_path(self._chemin)
        # migrations 1 à 5 seulement : l'état d'une installation existante
        c = db.conn()
        c.executescript("CREATE TABLE IF NOT EXISTS schema_version ("
                        "version INTEGER PRIMARY KEY, applique_ts INTEGER);")
        c.commit()
        for version, _label, fn in db.MIGRATIONS:
            if version > 5:
                break
            with db.tx() as cx:
                fn(cx)
            db._mark(version)
        self._remettre_ancienne_semaine()

    def tearDown(self):
        db.close()
        for suffixe in ("", "-wal", "-shm"):
            try:
                os.unlink(self._chemin + suffixe)
            except OSError:
                pass

    def _remettre_ancienne_semaine(self):
        """Recrée la semaine v5 telle qu'elle est en base chez l'utilisateur.

        Le seed lit `SEANCES`, qui porte déjà la nouvelle semaine : sans cette
        remise en arrière, on migrerait une base déjà correcte.
        """
        db.execute("UPDATE seance_modele SET jour_semaine = 1, lieu = 'salle' "
                   "WHERE nom = 'Dos & biceps'")
        db.execute("UPDATE seance_modele SET jour_semaine = 2 "
                   "WHERE nom = 'Pecs, épaules & triceps'")
        db.execute("UPDATE seance_modele SET lieu = 'salle' "
                   "WHERE nom = 'Bras (volume) & dos'")
        self.jeudi = db.q("SELECT id FROM seance_modele "
                          "WHERE nom = 'Bras (volume) & dos'")[0]["id"]
        db.execute("DELETE FROM seance_modele_exo WHERE seance_modele_id = ?",
                   (self.jeudi,))
        for ordre, code in enumerate(self.ANCIENS_EXOS_JEUDI, start=1):
            db.execute(
                "INSERT INTO seance_modele_exo(seance_modele_id, exercice_id, "
                "ordre, bloc, series_cible) "
                "SELECT ?, id, ?, 'principal', 3 FROM exercice WHERE code = ?",
                (self.jeudi, ordre, code))

    def _semaine(self):
        return {m["jour_semaine"]: (m["nom"], m["lieu"]) for m in db.q(
            "SELECT m.jour_semaine, m.nom, m.lieu FROM seance_modele m "
            "JOIN programme p ON p.id = m.programme_id "
            "WHERE p.actif = 1 AND m.jour_semaine BETWEEN 1 AND 5")}

    def test_la_semaine_est_bien_dans_l_ancien_etat_avant_migration(self):
        """Garde-fou : sans lui, les assertions d'après ne prouvent rien."""
        self.assertEqual(self._semaine()[1], ("Dos & biceps", "salle"))
        self.assertEqual(self._semaine()[4], ("Bras (volume) & dos", "salle"))

    def test_la_migration_replace_les_seances(self):
        self.assertEqual(db.migrate(), max(v for v, _l, _f in db.MIGRATIONS))
        semaine = self._semaine()
        self.assertEqual(semaine[1], ("Pecs, épaules & triceps", "maison"))
        self.assertEqual(semaine[2], ("Dos & biceps", "salle"))
        self.assertEqual(semaine[4], ("Bras (volume) & dos", "maison"))
        self.assertEqual(semaine[5], ("Jambes & explosivité", "salle"))

    def test_le_jeudi_perd_tout_son_materiel_de_salle(self):
        db.migrate()
        self.assertEqual(0, db.scalar(
            "SELECT COUNT(*) FROM seance_modele_exo sme "
            "JOIN exercice e ON e.id = sme.exercice_id "
            "WHERE sme.seance_modele_id = ? AND e.lieu = 'salle'",
            (self.jeudi,)))
        self.assertGreaterEqual(db.scalar(
            "SELECT COUNT(*) FROM seance_modele_exo "
            "WHERE seance_modele_id = ?", (self.jeudi,)), 8)

    def test_les_seances_deja_faites_gardent_leur_modele(self):
        """Les modèles sont modifiés sur place : l'historique doit survivre."""
        db.execute("INSERT INTO seance(uuid, seance_modele_id, date, statut) "
                   "VALUES ('deja-fait', ?, '2026-08-13', 'fait')",
                   (self.jeudi,))
        db.migrate()
        ligne = db.q("SELECT s.seance_modele_id, m.nom FROM seance s "
                     "JOIN seance_modele m ON m.id = s.seance_modele_id "
                     "WHERE s.uuid = 'deja-fait'")
        self.assertEqual(len(ligne), 1)
        self.assertEqual(ligne[0]["seance_modele_id"], self.jeudi)
        self.assertEqual(ligne[0]["nom"], "Bras (volume) & dos")

    def test_migration_rejouee_ne_duplique_pas_les_seances(self):
        db.migrate()
        avant = db.scalar("SELECT COUNT(*) FROM seance_modele")
        exos = db.scalar("SELECT COUNT(*) FROM seance_modele_exo")
        with db.tx() as cx:                 # rejeu direct, hors garde de version
            from mfcockpit.backend import seed_sport_v2
            seed_sport_v2.resynchroniser(cx)
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM seance_modele"), avant)
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM seance_modele_exo"),
                         exos)


class TestDateDeDebutDuProgramme(unittest.TestCase):
    """Le programme doit démarrer la journée du **cockpit**, pas celle de SQLite.

    `date('now')` est en UTC et ignore la bascule de 4 h du matin. Semé à
    1 h 30, le programme démarrait donc le lendemain de la journée en cours,
    et tout le numéro de semaine glissait d'un jour. Le test fige la journée
    pour ne pas dépendre de l'heure à laquelle il tourne.
    """

    JOUR_FIGE = "2026-08-17"

    def setUp(self):
        self._fd, self._chemin = tempfile.mkstemp(suffix=".db")
        os.close(self._fd)
        os.unlink(self._chemin)
        db.set_path(self._chemin)
        self._vrai = jour.jour_courant
        jour.jour_courant = lambda ts=None: self.JOUR_FIGE

    def tearDown(self):
        jour.jour_courant = self._vrai
        db.close()
        for suffixe in ("", "-wal", "-shm"):
            try:
                os.unlink(self._chemin + suffixe)
            except OSError:
                pass

    def test_le_programme_demarre_la_journee_du_cockpit(self):
        db.migrate()
        for nom in ("Haut du corps & abdos", "Reprise & explosivité"):
            debut = db.scalar("SELECT date_debut FROM programme WHERE nom = ?",
                              (nom,))
            self.assertEqual(debut, self.JOUR_FIGE, nom)
        self.assertEqual(progression.date_debut_programme().isoformat(),
                         self.JOUR_FIGE)

    def test_la_premiere_semaine_commence_bien_le_jour_du_seed(self):
        db.migrate()
        self.assertEqual(progression.semaine_programme(self.JOUR_FIGE), 1)


class TestVueSport(BaseTemporaire):
    """L'onglet [Sport] : vue d'ensemble du programme et du réel."""

    def test_la_semaine_couvre_les_sept_jours(self):
        semaine = sport.semaine_detaillee()
        self.assertEqual(len(semaine), 7)
        self.assertEqual([j["lettre"] for j in semaine], list("LMMJVSD"))
        positions = {j["position"] for j in semaine}
        self.assertIn("aujourdhui", positions)
        self.assertTrue(all(j["seances"] for j in semaine),
                        "aucun jour du programme ne doit être vide")

    def test_la_course_du_samedi_n_est_pas_oubliee(self):
        """`etat_jour` range les séances en trois paniers.

        `seances` (muscu, prehab), `core` (bloc du soir) et `cardio` : n'en
        lire qu'un fait disparaître la course du samedi de la vue d'ensemble.
        """
        samedi = next(j for j in sport.semaine_detaillee() if j["lettre"] == "S")
        noms = [s["nom"] for s in samedi["seances"]]
        self.assertTrue(any("Course" in n for n in noms), noms)
        self.assertTrue(any("abdos" in n.lower() for n in noms), noms)

    def test_consulter_la_semaine_n_ecrit_rien(self):
        """Regarder jeudi un lundi ne doit pas créer les tâches de jeudi.

        Sinon la journée compterait comme commencée, et les streaks
        deviendraient faux pour un simple coup d'œil.
        """
        jour.materialiser(jour.jour_courant())   # aujourd'hui, lui, est écrit
        avant = db.scalar("SELECT COUNT(*) FROM tache_jour", default=0)
        sport.semaine_detaillee(decalage=1)      # semaine prochaine, intacte
        sport.semaine_detaillee(decalage=-1)
        sport.prochaines_seances(10)
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM tache_jour",
                                   default=0), avant)

    def test_exercices_groupes_par_groupe_musculaire(self):
        groupes = sport.exercices_semaine_par_groupe()
        self.assertTrue(groupes)
        noms = [g["groupe"] for g in groupes]
        for attendu in ("bras", "dos", "abdos"):
            self.assertIn(attendu, noms)
        # la priorité du programme dicte l'ordre d'affichage
        self.assertLess(noms.index("bras"), noms.index("quadriceps"))
        for g in groupes:
            self.assertEqual(
                g["series_semaine"],
                sum(e["series_semaine"] for e in g["exercices"]))
            for e in g["exercices"]:
                self.assertTrue(e["occurrences"], e["nom"])

    def test_les_blocs_du_soir_comptent_double(self):
        """Trois rotations pour six soirs : chaque bloc tombe deux fois."""
        groupes = {g["groupe"]: g for g in sport.exercices_semaine_par_groupe()}
        planche = next(e for e in groupes["abdos"]["exercices"]
                       if e["nom"] == "Planche")
        soirs = [o for o in planche["occurrences"] if o["jour"] == "soir"]
        self.assertTrue(soirs)
        attendu = sum((o["series"] or 0) * (2 if o["jour"] == "soir" else 1)
                      for o in planche["occurrences"])
        self.assertEqual(planche["series_semaine"], attendu)

    def test_le_programme_complet_liste_tout(self):
        prog = sport.programme_complet()
        self.assertEqual(prog["nom"], jour.programme_actif()["nom"])
        modeles = prog["modeles"]
        # 7 jours (dont un samedi à deux séances) + 3 blocs du soir
        self.assertGreaterEqual(len(modeles), 10)
        soirs = [m for m in modeles if m["jour_semaine"] == 0]
        self.assertEqual(len(soirs), 3)
        self.assertTrue(all(m["jour_nom"] == "Tous les soirs" for m in soirs))
        # les blocs du soir sont rejetés en fin de liste, après dimanche
        self.assertEqual([m["jour_semaine"] for m in modeles][-3:], [0, 0, 0])
        for m in modeles:
            self.assertTrue(m["exos"], m["nom"])
            self.assertEqual(m["series_total"],
                             sum(e["series_cible"] or 0 for e in m["exos"]))

    def test_l_ancien_programme_reste_consultable(self):
        archives = sport.programmes_archives()
        self.assertTrue(archives)
        self.assertNotIn(jour.programme_actif()["nom"],
                         [p["nom"] for p in archives])

    def test_historique_et_apercu_suivent_le_journal(self):
        date_str = jour.jour_courant()
        jour.materialiser(date_str)
        seance = jour.etat_jour(date_str)["seances"][0]
        exo = seance["exos"][0]
        jour.enregistrer_serie(seance["seance_id"], exo["exercice_id"], 1,
                               reps=10, charge_kg=20.0, uid="vue-sport-1")
        a = sport.apercu()
        self.assertEqual(a["series"], 1)
        self.assertEqual(a["volume"], 200.0)
        histo = sport.historique_seances(40)
        # une séance seulement planifiée n'est pas encore dans l'historique
        jour.demarrer_seance(seance["seance_id"])
        histo = sport.historique_seances(40)
        ligne = next(h for h in histo if h["id"] == seance["seance_id"])
        self.assertEqual(ligne["series"], 1)
        self.assertEqual(ligne["volume"], 200.0)
        detail = sport.detail_seance(seance["seance_id"])
        self.assertEqual(len(detail), 1)
        self.assertEqual(detail[0]["charge_kg"], 20.0)


class TestSansProgramme(BaseTemporaire):

    def test_materialisation_sans_programme_actif(self):
        """Programme désactivé : le coréen continue, le sport ne plante pas."""
        db.execute("UPDATE programme SET actif = 0")
        date_str = "2026-04-02"
        self.assertEqual(jour.materialiser(date_str), date_str)

        etat = jour.etat_jour(date_str)
        self.assertEqual(etat["seances"], [])
        self.assertIsNone(etat["core"])
        self.assertIsNone(etat["cardio"])
        self.assertTrue(etat["coreen"]["checklist"])          # le coréen tient

        # aucune tâche sport -> le domaine n'est pas « validé » par défaut
        self.assertFalse(jour.domaine_valide("sport", date_str))
        jour.cocher_domaine(date_str, "coreen", fait=True)
        self.assertTrue(jour.domaine_valide("coreen", date_str))
        jour.recalc_streaks(date_str)                          # ne lève pas

    def test_base_vide_de_tout(self):
        """Base sans aucun contenu : l'API répond quand même."""
        for table in ("tache_jour", "seance_modele_exo", "seance_modele",
                      "programme", "kr_carte", "kr_item", "kr_semaine"):
            db.execute(f"DELETE FROM {table}")
        etat = jour.etat_jour("2026-04-03")
        self.assertEqual(etat["seances"], [])
        self.assertEqual(etat["coreen"]["checklist"], [])
        self.assertIsInstance(api.etat(), dict)
        self.assertIsInstance(stats.resume_global(), dict)
        self.assertEqual(stats.volume_hebdo(4), [])


# =====================================================================
class TestBundleEtRappels(BaseTemporaire):

    def test_bundle_contient_de_quoi_tenir_hors_ligne(self):
        b = api.bundle()
        self.assertEqual(len(b["jours"]), api.JOURS_BUNDLE)
        self.assertGreater(len(b["exercices"]), 50)
        self.assertTrue(b["coreen"]["cartes"])
        self.assertTrue(b["programme"]["modeles"])
        self.assertTrue(b["version"])
        # les jours à venir sont des aperçus : ils n'écrivent rien en base
        futur = b["jours"][-1]["date"]
        self.assertEqual(
            db.scalar("SELECT COUNT(*) FROM tache_jour WHERE date = ?",
                      (futur,), default=0), 0)

    def test_version_bundle_change_quand_on_coche(self):
        avant = api.version_bundle()
        etat = jour.etat_jour()
        jour.cocher(etat["coreen"]["checklist"][0]["id"], True)
        self.assertNotEqual(avant, api.version_bundle())

    def test_version_programme_ignore_les_series(self):
        """Le téléphone recharge son plan sur cette empreinte, pas sur l'autre.

        `version_bundle()` bouge à chaque série : s'en servir ferait recharger
        la séance entre deux séries, en pleine salle.
        """
        date_str = jour.jour_courant()
        jour.materialiser(date_str)
        seance = jour.etat_jour(date_str)["seances"][0]
        exo = seance["exos"][0]
        avant_plan = api.version_programme()
        avant_bundle = api.version_bundle()
        jour.enregistrer_serie(seance["seance_id"], exo["exercice_id"],
                               index_serie=1, reps=10, uid="serie-test-1")
        self.assertEqual(avant_plan, api.version_programme(),
                         "une série ne change pas le plan")
        self.assertNotEqual(avant_bundle, api.version_bundle())

    def test_version_programme_change_avec_le_programme(self):
        avant = api.version_programme()
        # on déplace une séance : c'est exactement le cas « lieux imposés »
        db.execute("UPDATE seance_modele SET jour_semaine = 5 "
                   "WHERE nom = 'Dos & biceps'")
        self.assertNotEqual(avant, api.version_programme())

    def test_le_jour_porte_la_version_du_programme(self):
        """Sans ce champ, le téléphone n'a aucun moyen de se savoir périmé."""
        self.assertEqual(api.etat_du_jour()["version_programme"],
                         api.version_programme())
        self.assertEqual(api.bundle()["version_programme"],
                         api.version_programme())

    def test_media_de_secours_toujours_servi(self):
        mime, corps = api.media("goblet_squat.svg")
        self.assertEqual(mime, "image/svg+xml")
        self.assertIn(b"<svg", corps)
        self.assertIsNone(api.media("exercice_inexistant.svg"))

    def test_rappels_deux_fils_independants(self):
        date_str = jour.jour_courant()
        jour.materialiser(date_str)
        # On se place à 10 h, dans la plage horaire, cockpit ouvert depuis 3 h.
        moment = _dt.datetime.combine(_dt.date.fromisoformat(date_str),
                                      _dt.time(10, 0)).timestamp()
        rappels.demarrer(moment - 3 * 3600)

        envoyes = rappels.tick(moment)
        self.assertEqual(set(envoyes), {"sport", "coreen"})

        # tout de suite après : rien, l'intervalle n'est pas écoulé
        self.assertEqual(rappels.tick(moment + 60), [])

        # coréen validé -> son fil s'éteint, celui du sport continue
        jour.cocher_domaine(date_str, "coreen", fait=True)
        self.assertEqual(rappels.tick(moment + 2 * 3600 + 60), ["sport"])

    def test_rappels_silencieux_hors_plage(self):
        date_str = jour.jour_courant()
        jour.materialiser(date_str)
        nuit = _dt.datetime.combine(_dt.date.fromisoformat(date_str),
                                    _dt.time(3, 0)).timestamp()
        rappels.demarrer(nuit - 10 * 3600)     # ouvert depuis longtemps
        self.assertEqual(rappels.tick(nuit), [])

    def test_textes_de_rappel_sont_utiles(self):
        date_str = _premier(progression.date_debut_programme(), 1)   # un lundi
        jour.materialiser(date_str)
        titre, detail = rappels.texte_sport(date_str)
        self.assertIn("Lundi", titre)
        # le nom vient du programme actif : on vérifie qu'il y est vraiment,
        # pas qu'il vaut une chaîne figée
        attendu = jour.etat_jour(date_str)["seances"][0]["nom"]
        self.assertIn(attendu, titre)
        self.assertIn("min", detail)
        titre, detail = rappels.texte_coreen(date_str)
        self.assertTrue(titre.startswith("Coréen S"))
        self.assertIn("carte", detail)


# =====================================================================
class TestCoreen(BaseTemporaire):

    def test_deblocage_de_la_direction_inverse(self):
        """FR→KR s'ouvre après 3 réussites en KR→FR, pas avant."""
        item = db.q1("SELECT id FROM kr_item WHERE type = 'vocab' LIMIT 1")
        carte = db.q1("SELECT id FROM kr_carte WHERE item_id = ? "
                      "AND direction = 'kr_fr'", (item["id"],))

        def suspendu():
            return db.scalar("SELECT suspendu FROM kr_carte WHERE item_id = ? "
                             "AND direction = 'fr_kr'", (item["id"],))

        self.assertEqual(suspendu(), 1)
        for i in range(2):
            korean.noter(carte["id"], True, uid=f"n{i}")
            self.assertEqual(suspendu(), 1)
        korean.noter(carte["id"], True, uid="n3")
        self.assertEqual(suspendu(), 0)

    def test_echec_raccourcit_l_echeance(self):
        carte = korean.cartes_dues(limite=1)[0]
        korean.noter(carte["id"], True, uid="ok")
        apres_reussite = db.q1("SELECT * FROM kr_carte WHERE id = ?",
                               (carte["id"],))
        korean.noter(carte["id"], False, uid="ko")
        apres_echec = db.q1("SELECT * FROM kr_carte WHERE id = ?",
                            (carte["id"],))
        self.assertLess(apres_echec["interval"], apres_reussite["interval"])
        self.assertEqual(apres_echec["reps"], 0)
        self.assertEqual(apres_echec["lapses"], 1)

    def test_facade_deck_retrocompatible(self):
        """L'ancienne API `Deck` continue de fonctionner sur SQLite."""
        deck = korean.Deck(config=None)
        cartes = deck.cards()
        self.assertTrue(cartes)
        self.assertIn("kr", cartes[0])
        self.assertIn("due", cartes[0])
        dues = deck.due_cards(limit=2)
        self.assertLessEqual(len(dues), 2)
        if dues:
            deck.grade(dues[0], True)
            self.assertGreater(
                db.scalar("SELECT reps FROM kr_carte WHERE id = ?",
                          (dues[0]["carte_id"],)), 0)

    def test_exercices_generes(self):
        sem = jour.semaine_coreen()
        types = {e["type"] for e in korean.exercices_semaine(sem["id"])}
        self.assertEqual(types, set(seed_coreen.ROTATION_EXOS))
        for exo in korean.exercices_semaine(sem["id"]):
            contenu = korean.contenu_exercice(exo["id"])
            self.assertIsNotNone(contenu)
            if contenu.get("questions"):
                q = contenu["questions"][0]
                self.assertIn(q["bonne"], q["choix"])

    def test_import_export_csv(self):
        avant = db.scalar("SELECT COUNT(*) FROM kr_item")
        csv = "kr,romaja,fr,example\n반갑다,bangapda,ravi,반갑습니다.\n"
        self.assertEqual(korean.import_csv(csv), 1)
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM kr_item"), avant + 1)
        self.assertIn("반갑다", korean.export_csv())


# =====================================================================
class TestServeurMobile(BaseTemporaire):
    """Le serveur HTTP réellement en écoute, sur un port de test."""

    def setUp(self):
        super().setUp()
        from mfcockpit.backend import webserver
        self.web = webserver
        db.set_reglage("mobile.port", 8799)
        self.assertTrue(webserver.demarrer(), webserver._derniere_erreur)
        self.base = "http://127.0.0.1:8799"
        self.jeton = webserver.jeton()

    def tearDown(self):
        self.web.arreter()
        super().tearDown()

    def _get(self, chemin, jeton=None, cookie=None, entetes=None):
        import urllib.error
        import urllib.request
        url = self.base + chemin
        if jeton:
            url += ("&" if "?" in chemin else "?") + "t=" + jeton
        requete = urllib.request.Request(url)
        if cookie:
            requete.add_header("Cookie", f"cockpit_token={cookie}")
        for cle, valeur in (entetes or {}).items():
            requete.add_header(cle, valeur)
        try:
            rep = urllib.request.urlopen(requete, timeout=5)
            return rep.status, dict(rep.headers), rep.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def test_jeton_exige_sur_toutes_les_routes(self):
        for chemin in ("/", "/app.js", "/style.css", "/api/jour", "/api/etat"):
            statut, _, _ = self._get(chemin)
            self.assertEqual(statut, 401, chemin)
            statut, _, _ = self._get(chemin, jeton="mauvais-jeton")
            self.assertEqual(statut, 401, chemin)

    def test_le_cookie_debloque_les_assets_relatifs(self):
        """`index.html` appelle `style.css` et `app.js` en relatif : sans
        cookie, le navigateur les demande sans le `?t=` et la page reste nue."""
        statut, entetes, _ = self._get("/", jeton=self.jeton)
        self.assertEqual(statut, 200)
        self.assertIn("cockpit_token=", entetes.get("Set-Cookie", ""))

        for chemin, mime in (("/app.js", "application/javascript"),
                             ("/style.css", "text/css")):
            statut, entetes, corps = self._get(chemin, cookie=self.jeton)
            self.assertEqual(statut, 200, chemin)
            self.assertIn(mime, entetes["Content-Type"])
            self.assertTrue(corps)

    def test_pas_de_traversee_de_repertoire(self):
        for chemin in ("/../mf_cockpit.py", "/../../etc/passwd",
                       "/api/media/../../../etc/passwd"):
            statut, _, _ = self._get(chemin, jeton=self.jeton)
            self.assertEqual(statut, 404, chemin)

    def test_entetes_de_cache(self):
        _s, entetes, _c = self._get("/api/jour", jeton=self.jeton)
        self.assertEqual(entetes["Cache-Control"], "no-store")
        _s, entetes, _c = self._get("/", jeton=self.jeton)
        self.assertEqual(entetes["Cache-Control"], "no-store")

    def test_les_assets_se_revalident_a_chaque_chargement(self):
        """Un correctif doit atteindre l'iPhone au rechargement, pas 7 jours après.

        `app.js` était servi `immutable, max-age=604800` : Safari ne
        redemandait jamais le fichier, donc la page mobile restait figée sur
        l'ancienne version même après mise à jour du cockpit.
        """
        for chemin in ("/app.js", "/style.css"):
            _s, entetes, _c = self._get(chemin, jeton=self.jeton)
            self.assertEqual(entetes["Cache-Control"], "no-cache", chemin)
            self.assertNotIn("immutable", entetes["Cache-Control"], chemin)
            self.assertTrue(entetes.get("ETag"), f"{chemin} sans ETag")

    def test_la_page_estampille_les_assets(self):
        """Sans ça, un téléphone déjà en cache `immutable` reste bloqué.

        Corriger l'en-tête ne suffit pas : un navigateur qui a gardé
        `app.js` sous `Cache-Control: immutable` ne le redemandera jamais.
        Seul un changement d'**URL** force le téléchargement — et la page qui
        porte cette URL est en `no-store`, donc elle arrive toujours fraîche.
        """
        _s, _e, corps = self._get("/", jeton=self.jeton)
        page = corps.decode("utf-8")
        self.assertRegex(page, r'href="style\.css\?v=[0-9a-f]{8}"')
        self.assertRegex(page, r'src="app\.js\?v=[0-9a-f]{8}"')
        # l'empreinte suit le contenu réellement servi
        _s, entetes, appjs = self._get("/app.js", jeton=self.jeton)
        import hashlib
        attendu = hashlib.sha1(appjs).hexdigest()[:8]
        self.assertIn(f'src="app.js?v={attendu}"', page)

    def test_l_estampille_change_avec_le_fichier(self):
        import hashlib
        import os
        from mfcockpit.backend import paths, webserver
        chemin = os.path.join(paths.WEB_DIR, "app.js")
        avant = webserver._empreinte_fichier("app.js")
        with open(chemin, "rb") as fh:
            origine = fh.read()
        try:
            with open(chemin, "ab") as fh:
                fh.write(b"\n// modification de test\n")
            self.assertNotEqual(avant, webserver._empreinte_fichier("app.js"))
        finally:
            with open(chemin, "wb") as fh:
                fh.write(origine)
        self.assertEqual(avant, webserver._empreinte_fichier("app.js"))

    def test_un_asset_inchange_repond_304_sans_corps(self):
        """La revalidation ne doit pas coûter un téléchargement complet."""
        _s, entetes, corps = self._get("/app.js", jeton=self.jeton)
        etag = entetes["ETag"]
        self.assertGreater(len(corps), 1000)
        statut, entetes2, corps2 = self._get(
            "/app.js", jeton=self.jeton, entetes={"If-None-Match": etag})
        self.assertEqual(statut, 304)
        self.assertEqual(corps2, b"")
        self.assertEqual(entetes2["ETag"], etag)

    def test_arret_propre(self):
        self.assertTrue(self.web.actif())
        self.web.arreter()
        self.assertFalse(self.web.actif())
        etat = self.web.etat()
        self.assertFalse(etat["actif"])
        self.assertIsNone(etat["url"])
        # le reste de l'app continue de fonctionner sans serveur
        self.assertIsInstance(jour.etat_jour(), dict)


class TestScrollDesOnglets(unittest.TestCase):
    """Non-régression : le panneau doit rester scrollable.

    `ThemedScroll` pose un bind `<Configure>` pour replier les libellés. Sans
    `add="+"`, ce bind **remplace** celui de `CTkScrollableFrame` qui calcule la
    `scrollregion` : elle reste vide et la molette ne fait plus rien. Le bug est
    invisible à l'œil sur une petite fenêtre — d'où ce test.
    """

    @classmethod
    def setUpClass(cls):
        try:
            import tkinter
            import customtkinter                       # noqa: F401
            cls._racine = tkinter.Tk()
            cls._racine.withdraw()
        except Exception as exc:                       # pas d'affichage : on saute
            raise unittest.SkipTest(f"Tk indisponible ({exc})")

    @classmethod
    def tearDownClass(cls):
        try:
            cls._racine.destroy()
        except Exception:
            pass

    def test_le_bind_de_repli_ne_tue_pas_la_scrollregion(self):
        import customtkinter as ctk

        from mfcockpit.ui.base import ThemedScroll

        class AppFactice:
            config_store = None

        fenetre = ctk.CTkToplevel(self._racine)
        fenetre.geometry("420x360")
        panneau = ThemedScroll(fenetre, AppFactice())
        panneau.pack(fill="both", expand=True)
        for i in range(60):
            panneau.replier(ctk.CTkLabel(panneau, text=f"ligne {i}" * 3,
                                         wraplength=300)).pack(fill="x")
        fenetre.update()
        fenetre.update_idletasks()

        canvas = panneau._parent_canvas                 # noqa: SLF001
        self.assertTrue(canvas.cget("scrollregion"),
                        "scrollregion vide : le scroll est mort")
        depart = canvas.yview()
        self.assertNotEqual(depart, (0.0, 1.0),
                            "le contenu devrait déborder, donc être scrollable")
        canvas.yview_moveto(0.5)
        fenetre.update_idletasks()
        self.assertNotEqual(depart, canvas.yview(), "le panneau ne défile pas")
        fenetre.destroy()


class TestQrCode(unittest.TestCase):
    """Le QR est un secours d'ergonomie : il ne doit jamais faire tomber l'UI."""

    def test_tailles_de_version(self):
        from mfcockpit.backend import qr
        for texte, cote in (("a" * 14, 21), ("b" * 26, 25), ("c" * 42, 29),
                            ("d" * 62, 33), ("e" * 84, 37), ("f" * 106, 41)):
            self.assertEqual(len(qr.matrice(texte, marge=0)), cote)

    def test_motifs_de_reperage(self):
        from mfcockpit.backend import qr
        m = qr.matrice("http://192.168.1.42:8790/?t=AbCdEfGh", marge=0)
        n = len(m)
        for r0, c0 in ((0, 0), (0, n - 7), (n - 7, 0)):
            self.assertTrue(all(m[r0][c0 + i] for i in range(7)))
            self.assertTrue(all(m[r0 + i][c0] for i in range(7)))
            self.assertFalse(m[r0 + 1][c0 + 1])
            self.assertTrue(m[r0 + 3][c0 + 3])
        self.assertTrue(m[n - 8][8])          # module sombre

    def test_depassement_de_capacite(self):
        from mfcockpit.backend import qr
        with self.assertRaises(ValueError):
            qr.matrice("z" * 107)


if __name__ == "__main__":
    unittest.main(verbosity=2)
