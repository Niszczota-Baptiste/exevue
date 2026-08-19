# -*- coding: utf-8 -*-
"""Agrégats de l'onglet [Sport] — la vue d'ensemble du programme et du réel.

Tout est calculé ici, en SQL ; l'onglet ne fait que dessiner, comme pour
`stats.py`. Une règle guide tout le module :

- le **passé** vient du journal (`seance`, `serie`) — ce qui a vraiment été fait ;
- le **futur** vient du programme (`seance_modele`) — ce qui est prévu ;
- **aujourd'hui** est le seul jour où les deux se superposent, et c'est
  exactement ce qu'on veut montrer.

Les jours à venir sont lus avec `etat_jour(materialise=False)` : consulter la
semaine ne doit **rien** écrire en base, sinon regarder jeudi le mardi
créerait ses tâches et fausserait les streaks.
"""
import datetime as _dt

from . import db, jour, progression

# Ordre d'affichage des groupes : la priorité du programme d'abord.
ORDRE_GROUPES = ["bras", "dos", "abdos", "pectoraux", "epaules",
                 "quadriceps", "ischios", "fessiers", "mollets",
                 "adducteurs", "tout"]

LIBELLE_GROUPE = {
    "bras": "Bras", "dos": "Dos", "abdos": "Abdos", "pectoraux": "Pectoraux",
    "epaules": "Épaules", "quadriceps": "Quadriceps", "ischios": "Ischios",
    "fessiers": "Fessiers", "mollets": "Mollets", "adducteurs": "Adducteurs",
    "tout": "Corps entier",
}

LIBELLE_JOUR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi",
                "Dimanche"]
LETTRES = "LMMJVSD"


def _rang_groupe(groupe: str) -> int:
    try:
        return ORDRE_GROUPES.index(groupe or "")
    except ValueError:
        return len(ORDRE_GROUPES)


def _lundi(date_str: str) -> _dt.date:
    d = _dt.date.fromisoformat(date_str)
    return d - _dt.timedelta(days=d.weekday())


# --------------------------------------------------------------- aperçu

def apercu(date_str=None) -> dict:
    """Les chiffres d'en-tête : programme, semaine, ce qui reste à faire."""
    date_str = date_str or jour.jour_courant()
    prog = jour.programme_actif()
    lundi = _lundi(date_str)
    dimanche = lundi + _dt.timedelta(days=6)

    faites = db.scalar(
        "SELECT COUNT(*) FROM seance WHERE date BETWEEN ? AND ? "
        "AND statut = 'fait'", (lundi.isoformat(), dimanche.isoformat()),
        default=0)
    manquees = db.scalar(
        "SELECT COUNT(*) FROM seance WHERE date BETWEEN ? AND ? "
        "AND statut = 'manque'", (lundi.isoformat(), dimanche.isoformat()),
        default=0)
    ligne = db.q1(
        "SELECT COUNT(*) AS series, "
        "       COALESCE(SUM(COALESCE(charge_kg, 0) * COALESCE(reps, 0)), 0) AS volume "
        "FROM serie r JOIN seance s ON s.id = r.seance_id "
        "WHERE s.date BETWEEN ? AND ?",
        (lundi.isoformat(), dimanche.isoformat())) or {}

    return {
        "programme": (prog or {}).get("nom"),
        "note": (prog or {}).get("note"),
        "date_debut": (prog or {}).get("date_debut"),
        "semaine_programme": progression.semaine_programme(date_str),
        "reprise": progression.est_reprise(date_str),
        "allegee": progression.est_semaine_allegee(date_str),
        "lundi": lundi.isoformat(),
        "dimanche": dimanche.isoformat(),
        "seances_faites": faites,
        "seances_manquees": manquees,
        "series": ligne.get("series") or 0,
        "volume": ligne.get("volume") or 0.0,
        "streaks": jour.streaks(),
    }


# ------------------------------------------------------- semaine détaillée

def _toutes_les_seances(etat: dict) -> list:
    """Les trois paniers d'`etat_jour` remis bout à bout.

    `etat_jour` sépare `seances` (muscu, prehab), `core` (le bloc du soir) et
    `cardio` — pratique pour l'onglet Aujourd'hui, trompeur ici : oublier un
    panier fait disparaître la course du samedi de la vue d'ensemble.
    """
    out = list(etat.get("seances") or [])
    for cle in ("cardio", "core"):
        if etat.get(cle):
            out.append(etat[cle])
    return out


def _volume_du_jour(date_str: str) -> dict:
    ligne = db.q1(
        "SELECT COUNT(*) AS series, "
        "       COALESCE(SUM(COALESCE(charge_kg, 0) * COALESCE(reps, 0)), 0) AS volume "
        "FROM serie r JOIN seance s ON s.id = r.seance_id WHERE s.date = ?",
        (date_str,)) or {}
    return {"series": ligne.get("series") or 0,
            "volume": ligne.get("volume") or 0.0}


def semaine_detaillee(date_str=None, decalage=0) -> list:
    """Les 7 jours de la semaine, séances comprises — passé, présent, futur.

    `decalage` en semaines permet de reculer ou d'avancer sans rien écrire.
    """
    date_str = date_str or jour.jour_courant()
    lundi = _lundi(date_str) + _dt.timedelta(weeks=decalage)
    aujourdhui = jour.jour_courant()

    out = []
    for i in range(7):
        d = (lundi + _dt.timedelta(days=i)).isoformat()
        # `materialise=False` : consulter n'écrit rien. Sans ça, ouvrir
        # l'onglet créerait les tâches des jours à venir.
        etat = jour.etat_jour(d, materialise=(d == aujourdhui))
        seances = _toutes_les_seances(etat)
        reel = _volume_du_jour(d)
        out.append({
            "date": d,
            "lettre": LETTRES[i],
            "jour": LIBELLE_JOUR[i],
            "libelle": jour.libelle_date(d),
            "position": ("aujourdhui" if d == aujourdhui
                         else "futur" if d > aujourdhui else "passe"),
            "seances": seances,
            "series": reel["series"],
            "volume": reel["volume"],
            "conseils": etat.get("conseils") or [],
        })
    return out


# ------------------------------------------------------ programme complet

def programme_complet() -> dict:
    """Toutes les séances-modèles du programme actif, exercices compris.

    C'est le programme « sur le papier », indépendamment de ce qui a été fait :
    les 7 jours plus les blocs du soir en rotation (`jour_semaine = 0`).
    """
    prog = jour.programme_actif()
    if not prog:
        return {}
    modeles = db.q(
        "SELECT * FROM seance_modele WHERE programme_id = ? "
        "ORDER BY CASE WHEN jour_semaine = 0 THEN 8 ELSE jour_semaine END, "
        "ordre_affichage", (prog["id"],))
    for m in modeles:
        m["jour_nom"] = (LIBELLE_JOUR[m["jour_semaine"] - 1]
                         if 1 <= (m["jour_semaine"] or 0) <= 7 else "Tous les soirs")
        m["exos"] = db.q(
            "SELECT sme.*, e.nom, e.code, e.groupe, e.categorie, e.unite, "
            "       e.equipement, e.lieu, e.chargeable "
            "FROM seance_modele_exo sme JOIN exercice e ON e.id = sme.exercice_id "
            "WHERE sme.seance_modele_id = ? ORDER BY sme.ordre", (m["id"],))
        m["series_total"] = sum(x["series_cible"] or 0 for x in m["exos"])
    return {"nom": prog["nom"], "note": prog["note"],
            "date_debut": prog["date_debut"], "modeles": modeles}


def programmes_archives() -> list:
    """Les programmes précédents, gardés pour que l'historique reste lisible."""
    return db.q(
        "SELECT p.id, p.nom, p.date_debut, "
        "  (SELECT COUNT(*) FROM seance_modele m WHERE m.programme_id = p.id) AS modeles, "
        "  (SELECT COUNT(*) FROM seance s JOIN seance_modele m2 "
        "     ON m2.id = s.seance_modele_id WHERE m2.programme_id = p.id) AS seances "
        "FROM programme p WHERE p.actif = 0 ORDER BY p.date_debut DESC, p.id DESC")


# --------------------------------------------- exercices de la semaine

def exercices_semaine_par_groupe() -> list:
    """Tous les exercices du programme, **groupés par groupe musculaire**.

    C'est la vue d'ensemble : pour chaque exercice, les jours où il tombe, le
    volume hebdomadaire prévu, et ce que le journal en dit (dernière charge,
    record, nombre de séries déjà faites).
    """
    prog = jour.programme_actif()
    if not prog:
        return []

    lignes = db.q(
        "SELECT e.id, e.nom, e.code, e.groupe, e.categorie, e.unite, "
        "       e.equipement, e.lieu, e.chargeable, e.consignes, "
        "       e.erreurs_frequentes, "
        "       m.jour_semaine, m.nom AS seance, m.lieu AS seance_lieu, "
        "       sme.series_cible, sme.reps_min, sme.reps_max, sme.repos_sec, "
        "       sme.charge_depart, sme.bloc, sme.tempo, sme.note "
        "FROM seance_modele_exo sme "
        "JOIN seance_modele m ON m.id = sme.seance_modele_id "
        "JOIN exercice e ON e.id = sme.exercice_id "
        "WHERE m.programme_id = ? ORDER BY e.groupe, e.nom, m.jour_semaine",
        (prog["id"],))

    # Journal : une seule requête pour tout le monde, pas une par exercice.
    faits = {r["exercice_id"]: r for r in db.q(
        "SELECT r.exercice_id, COUNT(*) AS series, "
        "       MAX(r.charge_kg) AS charge_max, "
        "       COALESCE(SUM(COALESCE(r.charge_kg,0) * COALESCE(r.reps,0)), 0) AS volume, "
        "       MAX(s.date) AS derniere_date, "
        "       COUNT(DISTINCT s.id) AS seances "
        "FROM serie r JOIN seance s ON s.id = r.seance_id "
        "GROUP BY r.exercice_id")}
    records = {}
    for r in db.q("SELECT exercice_id, type, MAX(valeur) AS valeur, unite "
                  "FROM record GROUP BY exercice_id, type"):
        records.setdefault(r["exercice_id"], {})[r["type"]] = r

    par_exo = {}
    for l in lignes:
        e = par_exo.setdefault(l["id"], {
            "id": l["id"], "nom": l["nom"], "code": l["code"],
            "groupe": l["groupe"], "categorie": l["categorie"],
            "unite": l["unite"], "equipement": l["equipement"],
            "lieu": l["lieu"], "chargeable": bool(l["chargeable"]),
            "consignes": l["consignes"], "erreurs": l["erreurs_frequentes"],
            "occurrences": [], "series_semaine": 0,
        })
        e["occurrences"].append({
            "jour_semaine": l["jour_semaine"],
            "jour": (LETTRES[l["jour_semaine"] - 1]
                     if 1 <= (l["jour_semaine"] or 0) <= 7 else "soir"),
            "seance": l["seance"], "seance_lieu": l["seance_lieu"],
            "series": l["series_cible"], "reps_min": l["reps_min"],
            "reps_max": l["reps_max"], "repos": l["repos_sec"],
            "charge_depart": l["charge_depart"], "bloc": l["bloc"],
            "tempo": l["tempo"], "note": l["note"],
        })
        # Un bloc du soir tombe 6 fois par semaine sur 3 rotations : 2 passages.
        e["series_semaine"] += (l["series_cible"] or 0) * (
            2 if (l["jour_semaine"] or 0) == 0 else 1)

    for e in par_exo.values():
        journal = faits.get(e["id"]) or {}
        e["series_faites"] = journal.get("series") or 0
        e["seances_faites"] = journal.get("seances") or 0
        e["volume_fait"] = journal.get("volume") or 0.0
        e["derniere_date"] = journal.get("derniere_date")
        e["derniere_charge"] = progression.derniere_charge(e["id"])
        rec = records.get(e["id"]) or {}
        e["record_charge"] = (rec.get("charge_max") or {}).get("valeur")
        e["record_1rm"] = (rec.get("1rm_estime") or {}).get("valeur")

    groupes = {}
    for e in par_exo.values():
        groupes.setdefault(e["groupe"] or "autre", []).append(e)

    out = []
    for groupe, exos in groupes.items():
        exos.sort(key=lambda x: (-x["series_semaine"], x["nom"]))
        out.append({
            "groupe": groupe,
            "libelle": LIBELLE_GROUPE.get(groupe, (groupe or "autre").capitalize()),
            "exercices": exos,
            "series_semaine": sum(x["series_semaine"] for x in exos),
            "series_faites": sum(x["series_faites"] for x in exos),
        })
    out.sort(key=lambda g: (_rang_groupe(g["groupe"]), g["libelle"]))
    return out


# ------------------------------------------------------------ historique

def historique_seances(limite=40) -> list:
    """Séances passées, du plus récent au plus ancien, avec leur réel."""
    return db.q(
        "SELECT s.id, s.date, s.statut, s.duree_s, s.rpe, s.humeur, "
        "       s.douleur_genou, s.douleur_hanche, s.note, s.source, "
        "       m.nom, m.lieu, m.type, m.duree_cible_min, "
        "       (SELECT COUNT(*) FROM serie r WHERE r.seance_id = s.id) AS series, "
        "       (SELECT COALESCE(SUM(COALESCE(r.charge_kg,0) * COALESCE(r.reps,0)), 0) "
        "          FROM serie r WHERE r.seance_id = s.id) AS volume "
        "FROM seance s LEFT JOIN seance_modele m ON m.id = s.seance_modele_id "
        "WHERE s.statut IN ('fait', 'partiel', 'manque', 'en_cours') "
        "ORDER BY s.date DESC, s.id DESC LIMIT ?", (limite,))


def detail_seance(seance_id: int) -> list:
    """Les séries réellement enregistrées d'une séance, par exercice."""
    return db.q(
        "SELECT e.nom, e.unite, r.index_serie, r.reps, r.charge_kg, r.duree_s, "
        "       r.rpe, r.variante, r.echec, r.source "
        "FROM serie r JOIN exercice e ON e.id = r.exercice_id "
        "WHERE r.seance_id = ? ORDER BY e.nom, r.index_serie", (seance_id,))


def prochaines_seances(nb=10, date_str=None) -> list:
    """Ce qui arrive : aujourd'hui d'abord, puis les jours suivants."""
    date_str = date_str or jour.jour_courant()
    depart = _dt.date.fromisoformat(date_str)
    out = []
    for i in range(0, 21):
        d = (depart + _dt.timedelta(days=i)).isoformat()
        etat = jour.etat_jour(d, materialise=(i == 0))
        for s in _toutes_les_seances(etat):
            if s.get("statut") in ("fait", "manque") and i == 0:
                continue
            out.append({**s, "date": d, "dans": i,
                        "libelle": jour.libelle_date(d)})
            if len(out) >= nb:
                return out
    return out


def volume_prevu_par_groupe() -> list:
    """Séries hebdomadaires prévues par groupe — le squelette du programme."""
    return [{"groupe": g["groupe"], "libelle": g["libelle"],
             "series": g["series_semaine"]}
            for g in exercices_semaine_par_groupe()]
