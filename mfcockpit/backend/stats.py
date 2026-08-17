"""Statistiques — **tout se calcule en SQL**, rien en Python.

Chaque fonction renvoie des listes de dicts prêtes à tracer. Aucune n'est
appelée quand l'onglet Stats n'est pas visible : c'est l'UI qui décide, comme
pour tous les autres onglets.

Le graphe qui sert le plus est `douleur_vs_volume_jambes()` : la courbe des
douleurs genou/hanche superposée au volume de travail des jambes. C'est ce qui
permet de voir *avant* que ça casse.
"""
import datetime as _dt

from . import db

GROUPES_JAMBES = ("quadriceps", "ischios", "fessiers", "mollets")
OBJECTIF_SEANCES_SEMAINE = 6
JOURS_MATURE = 21


# --------------------------------------------------------------- sport

def volume_hebdo(semaines=12) -> list:
    """Volume total (kg × reps) par semaine ISO."""
    return db.q(
        "SELECT strftime('%Y-%W', s.date) AS semaine, "
        "       MIN(s.date) AS debut, "
        "       ROUND(SUM(COALESCE(r.charge_kg, 0) * COALESCE(r.reps, 0))) AS volume, "
        "       COUNT(DISTINCT s.id) AS seances "
        "FROM seance s JOIN serie r ON r.seance_id = s.id "
        "WHERE s.statut IN ('fait', 'partiel') "
        "GROUP BY semaine ORDER BY semaine DESC LIMIT ?", (semaines,))[::-1]


def volume_par_groupe(semaines=8) -> list:
    return db.q(
        "SELECT e.groupe, "
        "       ROUND(SUM(COALESCE(r.charge_kg, 0) * COALESCE(r.reps, 0))) AS volume, "
        "       COUNT(*) AS series "
        "FROM serie r JOIN seance s ON s.id = r.seance_id "
        "JOIN exercice e ON e.id = r.exercice_id "
        "WHERE s.statut IN ('fait', 'partiel') "
        "AND s.date > date('now', ?) "
        "GROUP BY e.groupe HAVING volume > 0 ORDER BY volume DESC",
        (f"-{int(semaines) * 7} day",))


def progression_exercice(exercice_id, limite=40) -> list:
    """Charge max et 1RM estimé (Epley) séance après séance."""
    return db.q(
        "SELECT s.date, MAX(r.charge_kg) AS charge_max, "
        "       ROUND(MAX(r.charge_kg * (1 + r.reps / 30.0)), 1) AS rm_estime, "
        "       ROUND(SUM(COALESCE(r.charge_kg,0) * COALESCE(r.reps,0))) AS volume "
        "FROM serie r JOIN seance s ON s.id = r.seance_id "
        "WHERE r.exercice_id = ? AND s.statut IN ('fait', 'partiel') "
        "AND r.charge_kg > 0 "
        "GROUP BY s.date ORDER BY s.date DESC LIMIT ?",
        (exercice_id, limite))[::-1]


def exercices_suivis(limite=25) -> list:
    """Exercices chargeables réellement travaillés, les plus fréquents d'abord."""
    return db.q(
        "SELECT e.id, e.nom, e.groupe, COUNT(DISTINCT s.id) AS seances "
        "FROM serie r JOIN exercice e ON e.id = r.exercice_id "
        "JOIN seance s ON s.id = r.seance_id "
        "WHERE e.chargeable = 1 AND r.charge_kg > 0 "
        "AND s.statut IN ('fait', 'partiel') "
        "GROUP BY e.id ORDER BY seances DESC, e.nom LIMIT ?", (limite,))


def records(limite=20) -> list:
    return db.q(
        "SELECT e.nom, r.type, MAX(r.valeur) AS valeur, r.unite, r.date "
        "FROM record r JOIN exercice e ON e.id = r.exercice_id "
        "GROUP BY r.exercice_id, r.type ORDER BY r.date DESC LIMIT ?", (limite,))


def seances_par_semaine(semaines=12) -> list:
    return db.q(
        "SELECT strftime('%Y-%W', date) AS semaine, MIN(date) AS debut, "
        "       COUNT(*) AS faites, ? AS objectif "
        "FROM seance WHERE statut IN ('fait', 'partiel') "
        "GROUP BY semaine ORDER BY semaine DESC LIMIT ?",
        (OBJECTIF_SEANCES_SEMAINE, semaines))[::-1]


def assiduite_mensuelle(mois=12) -> list:
    """Part des séances planifiées effectivement faites, par mois."""
    return db.q(
        "SELECT strftime('%Y-%m', date) AS mois, COUNT(*) AS planifiees, "
        "       SUM(CASE WHEN statut IN ('fait','partiel') THEN 1 ELSE 0 END) AS faites, "
        "       ROUND(100.0 * SUM(CASE WHEN statut IN ('fait','partiel') THEN 1 ELSE 0 END) "
        "             / COUNT(*), 1) AS taux "
        "FROM seance WHERE date < date('now') "
        "GROUP BY mois ORDER BY mois DESC LIMIT ?", (mois,))[::-1]


def duree_moyenne() -> dict:
    row = db.q1(
        "SELECT ROUND(AVG(duree_s) / 60.0, 1) AS moyenne_min, "
        "       ROUND(MAX(duree_s) / 60.0, 1) AS max_min, COUNT(*) AS n "
        "FROM seance WHERE duree_s > 0 AND statut IN ('fait', 'partiel')")
    return row or {"moyenne_min": None, "max_min": None, "n": 0}


def repartition_lieu() -> list:
    return db.q(
        "SELECT COALESCE(m.lieu, 'inconnu') AS lieu, COUNT(*) AS n "
        "FROM seance s LEFT JOIN seance_modele m ON m.id = s.seance_modele_id "
        "WHERE s.statut IN ('fait', 'partiel') GROUP BY lieu ORDER BY n DESC")


def repartition_source() -> list:
    """PC vs téléphone — on doit pouvoir distinguer les deux."""
    return db.q(
        "SELECT source, COUNT(*) AS n FROM serie GROUP BY source ORDER BY n DESC")


def contacts_plyo_hebdo(semaines=12) -> list:
    return db.q(
        "SELECT strftime('%Y-%W', s.date) AS semaine, MIN(s.date) AS debut, "
        "       SUM(COALESCE(r.reps, 0)) AS contacts "
        "FROM serie r JOIN seance s ON s.id = r.seance_id "
        "JOIN exercice e ON e.id = r.exercice_id "
        "WHERE e.categorie = 'plyo' AND s.statut IN ('fait', 'partiel') "
        "GROUP BY semaine ORDER BY semaine DESC LIMIT ?", (semaines,))[::-1]


def douleur_vs_volume_jambes(jours=90) -> list:
    """LE graphe : douleurs relevées vs volume jambes, jour par jour.

    Les jours sans séance rendent `douleur = NULL` (la courbe se coupe) plutôt
    que zéro — un jour sans mesure n'est pas un jour sans douleur.
    """
    marques = ",".join("?" * len(GROUPES_JAMBES))
    return db.q(
        f"WITH jours AS ("
        f"  SELECT DISTINCT date FROM seance WHERE date > date('now', ?)"
        f") "
        f"SELECT j.date, "
        f"  (SELECT MAX(COALESCE(s.douleur_genou, 0)) FROM seance s "
        f"     WHERE s.date = j.date AND s.douleur_genou IS NOT NULL) AS genou, "
        f"  (SELECT MAX(COALESCE(s.douleur_hanche, 0)) FROM seance s "
        f"     WHERE s.date = j.date AND s.douleur_hanche IS NOT NULL) AS hanche, "
        f"  (SELECT ROUND(SUM(COALESCE(r.charge_kg,0) * COALESCE(r.reps,0))) "
        f"     FROM serie r JOIN seance s2 ON s2.id = r.seance_id "
        f"     JOIN exercice e ON e.id = r.exercice_id "
        f"     WHERE s2.date = j.date AND e.groupe IN ({marques})) AS volume_jambes "
        f"FROM jours j ORDER BY j.date",
        (f"-{int(jours)} day", *GROUPES_JAMBES))


def heatmap(jours=365) -> list:
    """(date, intensité 0-1 ou None, jour_semaine) sur 12 mois glissants."""
    lignes = db.q(
        "SELECT date, COUNT(*) AS total, SUM(fait) AS faits "
        "FROM tache_jour WHERE date > date('now', ?) AND domaine <> 'coreen' "
        "GROUP BY date", (f"-{int(jours)} day",))
    par_date = {r["date"]: r for r in lignes}
    fin = _dt.date.today()
    debut = fin - _dt.timedelta(days=jours)
    debut -= _dt.timedelta(days=debut.weekday())      # démarre un lundi
    out = []
    curseur = debut
    while curseur <= fin:
        cle = curseur.isoformat()
        ligne = par_date.get(cle)
        if not ligne or not ligne["total"]:
            valeur = None
        else:
            valeur = (ligne["faits"] or 0) / ligne["total"]
        out.append((cle, valeur, curseur.weekday()))
        curseur += _dt.timedelta(days=1)
    return out


# -------------------------------------------------------------- cardio

def cardio_resume() -> dict:
    row = db.q1(
        "SELECT ROUND(SUM(COALESCE(distance_km, 0)), 1) AS distance_totale, "
        "       ROUND(SUM(COALESCE(duree_s, 0)) / 3600.0, 1) AS heures, "
        "       COUNT(*) AS sorties, "
        "       ROUND(AVG(allure_s_km)) AS allure_moyenne, "
        "       MIN(CASE WHEN distance_km >= 4.8 THEN duree_s END) AS meilleur_5k "
        "FROM cardio WHERE type IN ('course', 'tapis')")
    return row or {}


def cardio_progression(limite=40) -> list:
    return db.q(
        "SELECT date, distance_km, duree_s, allure_s_km FROM cardio "
        "WHERE type IN ('course', 'tapis') AND allure_s_km IS NOT NULL "
        "ORDER BY date DESC LIMIT ?", (limite,))[::-1]


def cardio_par_type() -> list:
    return db.q(
        "SELECT type, COUNT(*) AS n, ROUND(SUM(COALESCE(duree_s,0))/3600.0, 1) "
        "AS heures FROM cardio GROUP BY type ORDER BY n DESC")


# ---------------------------------------------------------------- corps

def mesures(limite=120) -> list:
    """Poids + mensurations, avec moyenne glissante 7 jours calculée en SQL."""
    return db.q(
        "SELECT m.date, m.poids_kg, m.tour_taille, m.tour_bras, m.tour_cuisse, "
        "  (SELECT ROUND(AVG(m2.poids_kg), 2) FROM mesure m2 "
        "     WHERE m2.date <= m.date AND m2.date > date(m.date, '-7 day') "
        "     AND m2.poids_kg IS NOT NULL) AS poids_moy7 "
        "FROM mesure m ORDER BY m.date DESC LIMIT ?", (limite,))[::-1]


# --------------------------------------------------------------- coréen

def coreen_etat() -> dict:
    row = db.q1(
        "SELECT COUNT(*) AS cartes, "
        "  SUM(CASE WHEN reps = 0 AND suspendu = 0 THEN 1 ELSE 0 END) AS neuves, "
        "  SUM(CASE WHEN reps > 0 AND interval < ? THEN 1 ELSE 0 END) AS en_cours, "
        "  SUM(CASE WHEN interval >= ? THEN 1 ELSE 0 END) AS matures, "
        "  SUM(suspendu) AS suspendues FROM kr_carte",
        (JOURS_MATURE * 86400.0, JOURS_MATURE * 86400.0))
    return row or {}


def coreen_reussite_par_jour(jours=30) -> list:
    return db.q(
        "SELECT date(ts, 'unixepoch', 'localtime') AS jour, COUNT(*) AS vues, "
        "       SUM(su) AS sues, ROUND(100.0 * SUM(su) / COUNT(*), 1) AS taux "
        "FROM kr_revue WHERE ts > strftime('%s', 'now', ?) "
        "GROUP BY jour ORDER BY jour", (f"-{int(jours)} day",))


def coreen_reussite_par_direction() -> list:
    return db.q(
        "SELECT c.direction, COUNT(*) AS vues, SUM(v.su) AS sues, "
        "       ROUND(100.0 * SUM(v.su) / COUNT(*), 1) AS taux "
        "FROM kr_revue v JOIN kr_carte c ON c.id = v.carte_id "
        "GROUP BY c.direction")


def coreen_temps_cumule() -> dict:
    row = db.q1(
        "SELECT COUNT(*) AS revues, "
        "       ROUND(SUM(COALESCE(temps_ms, 0)) / 60000.0, 1) AS minutes "
        "FROM kr_revue")
    return row or {}


def coreen_avancement_semaines() -> list:
    """Barre d'avancement par semaine du programme 9 semaines."""
    return db.q(
        "SELECT s.numero, s.theme, s.date_debut, s.date_fin, "
        "  COUNT(c.id) AS cartes, "
        "  SUM(CASE WHEN c.reps > 0 THEN 1 ELSE 0 END) AS vues, "
        "  SUM(CASE WHEN c.interval >= ? THEN 1 ELSE 0 END) AS matures "
        "FROM kr_semaine s "
        "LEFT JOIN kr_item i ON i.semaine_id = s.id "
        "LEFT JOIN kr_carte c ON c.item_id = i.id "
        "GROUP BY s.id ORDER BY s.numero", (JOURS_MATURE * 86400.0,))


def coreen_betes_noires(limite=10) -> list:
    """Les cartes les plus ratées — celles qu'il faut reprendre à la main."""
    return db.q(
        "SELECT i.kr, i.fr, c.direction, c.lapses, "
        "  COUNT(v.id) AS vues, "
        "  SUM(CASE WHEN v.su = 0 THEN 1 ELSE 0 END) AS ratees, "
        "  ROUND(100.0 * SUM(CASE WHEN v.su = 0 THEN 1 ELSE 0 END) "
        "        / COUNT(v.id), 0) AS taux_echec "
        "FROM kr_carte c JOIN kr_item i ON i.id = c.item_id "
        "JOIN kr_revue v ON v.carte_id = c.id "
        "GROUP BY c.id HAVING vues >= 2 AND ratees > 0 "
        "ORDER BY ratees DESC, taux_echec DESC LIMIT ?", (limite,))


def coreen_previsions(jours=30) -> list:
    """Cartes à échoir par jour sur le mois à venir."""
    return db.q(
        "SELECT date(due, 'unixepoch', 'localtime') AS jour, COUNT(*) AS nb "
        "FROM kr_carte WHERE suspendu = 0 "
        "AND due < strftime('%s', 'now', ?) "
        "GROUP BY jour ORDER BY jour", (f"+{int(jours)} day",))


# ------------------------------------------------------------ transverse

def streaks() -> list:
    return db.q("SELECT * FROM streak ORDER BY domaine")


def resume_global() -> dict:
    return {
        "seances_faites": int(db.scalar(
            "SELECT COUNT(*) FROM seance WHERE statut IN ('fait','partiel')",
            default=0)),
        "seances_manquees": int(db.scalar(
            "SELECT COUNT(*) FROM seance WHERE statut = 'manque'", default=0)),
        "series": int(db.scalar("SELECT COUNT(*) FROM serie", default=0)),
        "volume_total": float(db.scalar(
            "SELECT ROUND(SUM(COALESCE(charge_kg,0) * COALESCE(reps,0))) "
            "FROM serie", default=0) or 0),
        "revues_kr": int(db.scalar("SELECT COUNT(*) FROM kr_revue", default=0)),
    }
