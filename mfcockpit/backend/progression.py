"""Moteur de progression — charges, variantes, plyométrie, course, douleur.

Tout se déduit du **journal réel** (`serie`), jamais du modèle : la charge
proposée vient toujours de la dernière séance réalisée pour cet exercice.

Trois moteurs :

- **double progression** (salle, exercices chargeables) : on monte de 2,5 kg
  quand toute la fourchette haute est atteinte avec 1-2 reps en réserve, on
  redescend d'un cran après deux séances sous le bas de la fourchette ;
- **échelle de variantes** (maison, plafond 12 kg) : quand le haut de la
  fourchette est tenu sur toutes les séries **deux séances d'affilée**, on
  propose le palier suivant de `exercice.variantes_json` ;
- **règle douleur** codée en dur : au-delà de 3/10 sur le genou ou la hanche,
  course et plyométrie sont remplacées par du vélo.
"""
import datetime as _dt
import json

from . import db

# RPE renvoyé par les 3 boutons du téléphone.
RPE_FACILE, RPE_JUSTE, RPE_ECHEC = 6, 8, 10

PAS_CHARGE_DEFAUT = 2.5      # kg, salle (cran de pile)
PLAFOND_MAISON_KG = 24.0     # 2 kettlebells de 12 kg
SEUIL_DOULEUR = 3            # au-delà : adaptation automatique
CONTACTS_MAX = 60            # plyométrie, par séance
DELOAD_TOUTES_LES_N_SEMAINES = 6
DELOAD_REDUCTION = 0.40      # -40 % de volume, charges inchangées

# --- plyométrie : montée en charge sur 9 semaines -------------------------
# semaine -> (codes autorisés, libellé affiché)
PLYO_PLAN = {
    1: (["drop_landing", "pogo_hops"], "Reprise : drop landings + pogos"),
    2: (["drop_landing", "pogo_hops"], "Reprise : drop landings + pogos"),
    3: (["pogo_hops", "squat_jump", "broad_jump"], "Squat jumps + broad jumps"),
    4: (["pogo_hops", "squat_jump", "broad_jump"], "Squat jumps + broad jumps"),
    5: (["pogo_hops", "squat_jump", "broad_jump", "fente_sautee",
         "bond_une_jambe"], "+ fentes sautées et bonds sur une jambe"),
    6: (["pogo_hops", "squat_jump", "broad_jump", "fente_sautee",
         "bond_une_jambe"], "+ fentes sautées et bonds sur une jambe"),
    7: (["pogo_hops", "squat_jump", "depth_jump", "saut_elan"],
        "Depth jumps (marche basse) + saut avec élan"),
    8: (["pogo_hops", "squat_jump", "depth_jump", "saut_elan"],
        "Depth jumps (marche basse) + saut avec élan"),
    9: (["pogo_hops", "squat_jump", "depth_jump", "saut_elan"],
        "Depth jumps (marche basse) + saut avec élan"),
}

# --- course 5 km : plan du samedi -----------------------------------------
COURSE_PLAN = {
    1: "5 × (3 min course / 1 min marche)",
    2: "5 × (4 min course / 1 min marche)",
    3: "4 × (6 min course / 1 min marche)",
    4: "3 × (9 min course / 1 min marche)",
    5: "2 × (14 min course / 1 min marche)",
    6: "30 min en continu",
    7: "5 km chrono (référence)",
    8: "5 km + 4 × 30 s d'accélération",
    9: "5 km chrono",
}


# ------------------------------------------------------------- calendrier

def date_debut_programme():
    row = db.q1("SELECT date_debut FROM programme WHERE actif = 1 "
                "ORDER BY id LIMIT 1")
    if not row or not row.get("date_debut"):
        return None
    try:
        return _dt.date.fromisoformat(row["date_debut"])
    except ValueError:
        return None


def semaine_programme(date_str: str) -> int:
    """Numéro de semaine du programme (1-based). 1 si le début est inconnu."""
    debut = date_debut_programme()
    if debut is None:
        return 1
    try:
        d = _dt.date.fromisoformat(date_str)
    except ValueError:
        return 1
    # On aligne sur le lundi de la semaine de départ.
    debut -= _dt.timedelta(days=debut.weekday())
    delta = (d - debut).days
    return max(1, delta // 7 + 1)


def est_semaine_allegee(date_str: str) -> bool:
    """Toutes les 6 semaines : -40 % de volume, charges inchangées."""
    return semaine_programme(date_str) % DELOAD_TOUTES_LES_N_SEMAINES == 0


def est_reprise(date_str: str) -> bool:
    """Semaines 1-2 : une série de moins, 2-3 reps en réserve, pas de plyo."""
    return semaine_programme(date_str) <= 2


def plyo_semaine(date_str: str):
    """(codes autorisés, libellé) pour la semaine de cette date."""
    return PLYO_PLAN.get(min(9, semaine_programme(date_str)), PLYO_PLAN[1])


def course_semaine(date_str: str) -> str:
    return COURSE_PLAN.get(min(9, semaine_programme(date_str)), COURSE_PLAN[9])


def series_ajustees(series_cible: int, date_str: str) -> int:
    """Applique reprise (-1 série) et semaine allégée (-40 %)."""
    n = int(series_cible or 0)
    if n <= 0:
        return n
    if est_reprise(date_str):
        n -= 1
    if est_semaine_allegee(date_str):
        n = int(round(n * (1 - DELOAD_REDUCTION)))
    return max(1, n)


# ------------------------------------------------------- 1RM & historique

def epley(charge_kg: float, reps: int) -> float:
    """1RM estimé (Epley). 0 si la saisie n'a pas de sens."""
    try:
        charge_kg = float(charge_kg or 0)
        reps = int(reps or 0)
    except (TypeError, ValueError):
        return 0.0
    if charge_kg <= 0 or reps <= 0:
        return 0.0
    return round(charge_kg * (1 + reps / 30.0), 1)


def dernieres_seances_exo(exercice_id: int, limite: int = 3) -> list:
    """Les N dernières séances *faites* contenant cet exercice, récentes d'abord.

    Chaque entrée : {seance_id, date, series: [{reps, charge_kg, rpe, variante}]}.
    """
    seances = db.q(
        "SELECT s.id, s.date FROM seance s "
        "JOIN serie r ON r.seance_id = s.id "
        "WHERE r.exercice_id = ? AND s.statut IN ('fait', 'partiel') "
        "GROUP BY s.id ORDER BY s.date DESC, s.id DESC LIMIT ?",
        (exercice_id, limite))
    out = []
    for s in seances:
        series = db.q(
            "SELECT reps, charge_kg, rpe, variante, duree_s FROM serie "
            "WHERE seance_id = ? AND exercice_id = ? ORDER BY index_serie",
            (s["id"], exercice_id))
        out.append({"seance_id": s["id"], "date": s["date"], "series": series})
    return out


def derniere_charge(exercice_id: int):
    """Charge de la dernière séance réalisée (jamais celle du modèle)."""
    row = db.q1(
        "SELECT r.charge_kg FROM serie r JOIN seance s ON s.id = r.seance_id "
        "WHERE r.exercice_id = ? AND r.charge_kg IS NOT NULL AND r.charge_kg > 0 "
        "AND s.statut IN ('fait', 'partiel') "
        "ORDER BY s.date DESC, r.ts DESC LIMIT 1", (exercice_id,))
    return row["charge_kg"] if row else None


def derniere_variante(exercice_id: int):
    row = db.q1(
        "SELECT r.variante FROM serie r JOIN seance s ON s.id = r.seance_id "
        "WHERE r.exercice_id = ? AND r.variante IS NOT NULL AND r.variante <> '' "
        "AND s.statut IN ('fait', 'partiel') "
        "ORDER BY s.date DESC, r.ts DESC LIMIT 1", (exercice_id,))
    return row["variante"] if row else None


# ---------------------------------------------------------- double progression

def _seance_au_sommet(series, reps_max, reserve=True) -> bool:
    """Toutes les séries au plafond de la fourchette, avec du rab si demandé."""
    if not series or not reps_max:
        return False
    for s in series:
        if (s.get("reps") or 0) < reps_max:
            return False
        if reserve and (s.get("rpe") or 0) >= RPE_ECHEC:
            return False   # série menée à l'échec : pas de réserve, on ne monte pas
    return True


def _seance_sous_le_plancher(series, reps_min) -> bool:
    if not series or not reps_min:
        return False
    return min((s.get("reps") or 0) for s in series) < reps_min


def evaluer(exercice: dict, modele_exo: dict, date_str=None) -> dict:
    """Que proposer à la prochaine séance pour cet exercice ?

    Renvoie ``{action, charge, variante, raison}`` où *action* vaut
    ``monter`` | ``tenir`` | ``descendre`` | ``variante``.
    """
    exo_id = exercice["id"]
    reps_min = modele_exo.get("reps_min")
    reps_max = modele_exo.get("reps_max")
    chargeable = bool(exercice.get("chargeable"))
    pas = float(db.reglage("sport.pas_charge_kg", PAS_CHARGE_DEFAUT) or
                PAS_CHARGE_DEFAUT)

    hist = dernieres_seances_exo(exo_id, limite=2)
    charge = derniere_charge(exo_id)
    if charge is None:
        charge = modele_exo.get("charge_depart")
    variante = derniere_variante(exo_id)
    variantes = _variantes(exercice)
    if variante is None and variantes:
        variante = variantes[0]

    base = {"action": "tenir", "charge": charge, "variante": variante,
            "raison": "Première séance : cale-toi sur des séries propres."
                      if not hist else "On garde, la fourchette n'est pas bouclée."}
    if not hist:
        return base

    derniere = hist[0]["series"]
    au_sommet = _seance_au_sommet(derniere, reps_max)

    # --- maison : plafond de charge atteint -> échelle de variantes ---
    plafond = chargeable and charge is not None and charge >= PLAFOND_MAISON_KG
    maison = (exercice.get("lieu") == "maison") or not chargeable
    if (maison or plafond) and variantes:
        deux_fois = (au_sommet and len(hist) > 1
                     and _seance_au_sommet(hist[1]["series"], reps_max))
        if deux_fois:
            suivante = _variante_suivante(variantes, variante)
            if suivante:
                return {"action": "variante", "charge": charge,
                        "variante": suivante,
                        "raison": f"Haut de fourchette tenu deux séances : "
                                  f"passe à « {suivante} »."}
        if au_sommet:
            return {"action": "tenir", "charge": charge, "variante": variante,
                    "raison": "Haut de fourchette atteint — refais-le une fois "
                              "pour valider le palier."}

    # --- salle : double progression sur la charge ---
    if chargeable and charge:
        if au_sommet:
            return {"action": "monter", "charge": round(charge + pas, 1),
                    "variante": variante,
                    "raison": f"Toutes les séries à {reps_max} avec de la "
                              f"réserve : +{pas:g} kg, on repart à {reps_min}."}
        sous = _seance_sous_le_plancher(derniere, reps_min)
        sous_avant = (len(hist) > 1
                      and _seance_sous_le_plancher(hist[1]["series"], reps_min))
        if sous and sous_avant:
            return {"action": "descendre",
                    "charge": max(0.0, round(charge - pas, 1)),
                    "variante": variante,
                    "raison": f"Deux séances sous {reps_min} reps : redescends "
                              f"d'un cran pour reconstruire."}
    return base


def _variantes(exercice: dict) -> list:
    try:
        val = json.loads(exercice.get("variantes_json") or "[]")
        return [str(v) for v in val] if isinstance(val, list) else []
    except (TypeError, ValueError):
        return []


def _variante_suivante(variantes: list, courante):
    if not variantes:
        return None
    if courante in variantes:
        i = variantes.index(courante)
        return variantes[i + 1] if i + 1 < len(variantes) else None
    return variantes[0]


# ------------------------------------------------------------- records

def maj_records(seance_id: int) -> list:
    """Met à jour la table `record` après une séance. Renvoie les records battus."""
    seance = db.q1("SELECT id, date FROM seance WHERE id = ?", (seance_id,))
    if not seance:
        return []
    battus = []
    exos = db.q("SELECT DISTINCT exercice_id FROM serie WHERE seance_id = ?",
                (seance_id,))
    for e in exos:
        exo_id = e["exercice_id"]
        if exo_id is None:
            continue
        nom = db.scalar("SELECT nom FROM exercice WHERE id = ?", (exo_id,),
                        default="?")
        series = db.q(
            "SELECT id, reps, charge_kg FROM serie "
            "WHERE seance_id = ? AND exercice_id = ?", (seance_id, exo_id))
        candidats = []
        charges = [(s["charge_kg"] or 0, s["id"]) for s in series]
        if charges:
            v, sid = max(charges)
            if v > 0:
                candidats.append(("charge_max", v, "kg", sid))
        reps = [(s["reps"] or 0, s["id"]) for s in series]
        if reps:
            v, sid = max(reps)
            if v > 0:
                candidats.append(("reps_max", v, "reps", sid))
        volume = sum((s["charge_kg"] or 0) * (s["reps"] or 0) for s in series)
        if volume > 0:
            candidats.append(("volume_seance", round(volume, 1), "kg", None))
        rms = [(epley(s["charge_kg"], s["reps"]), s["id"]) for s in series]
        if rms:
            v, sid = max(rms)
            if v > 0:
                candidats.append(("1rm_estime", v, "kg", sid))

        for typ, valeur, unite, sid in candidats:
            ancien = db.scalar(
                "SELECT MAX(valeur) FROM record WHERE exercice_id = ? "
                "AND type = ?", (exo_id, typ), default=None)
            if ancien is not None and valeur <= ancien:
                continue
            db.execute(
                "INSERT INTO record(exercice_id, type, valeur, unite, date, "
                "serie_id) VALUES (?,?,?,?,?,?)",
                (exo_id, typ, valeur, unite, seance["date"], sid))
            battus.append({"exercice": nom, "type": typ, "valeur": valeur,
                           "unite": unite, "ancien": ancien})
    return battus


# ------------------------------------------------------------- douleur

def alerte_douleur(date_str=None) -> dict:
    """Règle douleur codée en dur (genou droit / hanche droite).

    - une valeur > 3/10 pendant ou le lendemain -> course et plyométrie
      remplacées par du vélo à la séance suivante ;
    - moyenne 7 jours en hausse trois semaines de suite -> on renvoie vers un
      professionnel plutôt que vers un ajustement de programme.
    """
    date_str = date_str or _dt.date.today().isoformat()
    recentes = db.q(
        "SELECT date, douleur_genou, douleur_hanche FROM seance "
        "WHERE date <= ? AND date >= date(?, '-1 day') "
        "AND (douleur_genou IS NOT NULL OR douleur_hanche IS NOT NULL) "
        "ORDER BY date DESC", (date_str, date_str))
    pic = 0
    for r in recentes:
        pic = max(pic, r["douleur_genou"] or 0, r["douleur_hanche"] or 0)

    # Moyennes glissantes 7 jours, sur 3 fenêtres consécutives.
    moyennes = []
    for i in range(3):
        fin = f"-{i * 7} day"
        debut = f"-{i * 7 + 7} day"
        val = db.scalar(
            "SELECT AVG(MAX(COALESCE(douleur_genou, 0), "
            "            COALESCE(douleur_hanche, 0))) FROM seance "
            "WHERE date > date(?, ?) AND date <= date(?, ?) "
            "AND (douleur_genou IS NOT NULL OR douleur_hanche IS NOT NULL)",
            (date_str, debut, date_str, fin), default=None)
        moyennes.append(val)

    hausse_3_semaines = (
        all(m is not None for m in moyennes)
        and moyennes[0] > moyennes[1] > moyennes[2]
    )

    if hausse_3_semaines:
        return {"niveau": "medical", "pic": pic, "moyennes": moyennes,
                "adapter": True,
                "message": "Douleur en hausse depuis 3 semaines — un avis "
                           "kiné/médecin serait plus utile qu'un ajustement "
                           "de programme."}
    if pic > SEUIL_DOULEUR:
        return {"niveau": "adaptation", "pic": pic, "moyennes": moyennes,
                "adapter": True,
                "message": f"Douleur relevée à {pic}/10 : course et plyométrie "
                           f"remplacées par du vélo à la prochaine séance."}
    return {"niveau": "ok", "pic": pic, "moyennes": moyennes, "adapter": False,
            "message": ""}


def foot_salle_ce_jour(date_str: str) -> bool:
    return bool(db.scalar(
        "SELECT COUNT(*) FROM cardio WHERE date = ? AND type = 'foot_salle'",
        (date_str,), default=0))


def conseils(date_str: str) -> list:
    """Encarts à afficher sur l'onglet Aujourd'hui (et dans le bundle mobile)."""
    out = []
    douleur = alerte_douleur(date_str)
    if douleur["message"]:
        out.append({"type": "douleur", "niveau": douleur["niveau"],
                    "texte": douleur["message"]})
    if est_semaine_allegee(date_str):
        out.append({"type": "deload", "niveau": "info",
                    "texte": "Semaine allégée : volume réduit de 40 %, charges "
                             "inchangées. C'est prévu, pas un relâchement."})
    if est_reprise(date_str):
        out.append({"type": "reprise", "niveau": "info",
                    "texte": "Phase de reprise : une série de moins, 2-3 reps "
                             "en réserve, pas de plyométrie réelle."})
    if foot_salle_ce_jour(date_str):
        out.append({"type": "foot", "niveau": "info",
                    "texte": "Foot en salle enregistré aujourd'hui : enlève une "
                             "série sur les exercices 1 et 4 et saute la "
                             "plyométrie."})
    return out
