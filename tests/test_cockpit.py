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
                               rappels, seed_coreen, stats)


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
        avant = {t: db.scalar(f"SELECT COUNT(*) FROM {t}", default=0)
                 for t in ("exercice", "programme", "seance_modele",
                           "seance_modele_exo", "kr_semaine", "kr_item",
                           "kr_carte", "kr_exercice")}
        self.assertEqual(db.migrate(), 4)
        self.assertEqual(db.migrate(), 4)      # et une troisième pour la route
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
        for semaine in range(0, 9):
            lundi = (debut + _dt.timedelta(weeks=semaine)).isoformat()
            etat = jour.etat_jour(lundi, materialise=False)
            for seance in etat["seances"]:
                self.assertLessEqual(
                    seance["contacts_plyo"], progression.CONTACTS_MAX,
                    f"semaine {semaine + 1} : {seance['contacts_plyo']} contacts")

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
        debut = progression.date_debut_programme()
        mercredi = (debut + _dt.timedelta(days=2)).isoformat()
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
        date_str = progression.date_debut_programme().isoformat()   # un lundi
        jour.materialiser(date_str)
        titre, detail = rappels.texte_sport(date_str)
        self.assertIn("Lundi", titre)
        self.assertIn("Bas du corps", titre)
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

    def _get(self, chemin, jeton=None, cookie=None):
        import urllib.error
        import urllib.request
        url = self.base + chemin
        if jeton:
            url += ("&" if "?" in chemin else "?") + "t=" + jeton
        requete = urllib.request.Request(url)
        if cookie:
            requete.add_header("Cookie", f"cockpit_token={cookie}")
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
        _s, entetes, _c = self._get("/style.css", jeton=self.jeton)
        self.assertIn("max-age", entetes["Cache-Control"])
        _s, entetes, _c = self._get("/", jeton=self.jeton)
        self.assertEqual(entetes["Cache-Control"], "no-store")

    def test_arret_propre(self):
        self.assertTrue(self.web.actif())
        self.web.arreter()
        self.assertFalse(self.web.actif())
        etat = self.web.etat()
        self.assertFalse(etat["actif"])
        self.assertIsNone(etat["url"])
        # le reste de l'app continue de fonctionner sans serveur
        self.assertIsInstance(jour.etat_jour(), dict)


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
