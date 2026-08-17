"""La journée : matérialisation des tâches, validation, streaks.

Règles métier (elles sont volontairement sèches) :

- le **changement de jour se fait à 4 h du matin** : une séance à 1 h compte
  pour la veille ;
- les tâches du jour sont **matérialisées** une fois pour toutes dans
  `tache_jour` — l'historique survit à une modification du programme, et le
  téléphone reçoit exactement la même liste que le PC ;
- **deux streaks totalement indépendants** (sport et coréen), aucun joker :
  une journée non validée casse la série ;
- une séance **manquée reste manquée** : elle ne glisse pas au lendemain et ne
  décale pas la semaine.
"""
import datetime as _dt
import json
import time
import uuid as _uuid

from . import db, progression

BASCULE_H = 4          # heure de changement de journée
DOMAINES_SPORT = ("sport", "core", "cardio", "prehab")
DOMAINE_COREEN = "coreen"

JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi",
            "dimanche"]
MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]

# Type de séance -> domaine de tâche.
DOMAINE_PAR_TYPE = {"force": "sport", "mixte": "sport", "core": "core",
                    "cardio": "cardio", "prehab": "prehab"}

# Plyométrie injectée hors modèle (montée en charge sur 9 semaines).
PLYO_DEFAUT = {"series": 3, "reps": 5, "repos": 90}

CHECKLIST_COREEN = [
    "Réviser les cartes dues",
    "5 nouveaux items de la semaine",
    "1 exercice du jour",
    "Lire le dialogue de la semaine à voix haute",
]
CHECKLIST_COREEN_DIMANCHE = [
    "Réviser les cartes dues",
    "Bilan de la semaine (taux de réussite, bêtes noires)",
]


# --------------------------------------------------------------- dates

def jour_courant(ts=None) -> str:
    """Date de la « journée » en cours — bascule à 4 h du matin."""
    moment = _dt.datetime.fromtimestamp(ts) if ts else _dt.datetime.now()
    return (moment - _dt.timedelta(hours=BASCULE_H)).date().isoformat()


def libelle_date(date_str: str) -> str:
    try:
        d = _dt.date.fromisoformat(date_str)
    except ValueError:
        return date_str
    return f"{JOURS_FR[d.weekday()].capitalize()} {d.day} {MOIS_FR[d.month - 1]}"


def jour_semaine(date_str: str) -> int:
    """1 = lundi … 7 = dimanche."""
    return _dt.date.fromisoformat(date_str).weekday() + 1


def _decale(date_str: str, jours: int) -> str:
    return (_dt.date.fromisoformat(date_str) + _dt.timedelta(days=jours)
            ).isoformat()


# --------------------------------------------------------- matérialisation

def programme_actif():
    return db.q1("SELECT * FROM programme WHERE actif = 1 ORDER BY id LIMIT 1")


def _index_rotation_core(date_str: str) -> int:
    """Rotation A/B/C : compte les jours hors samedi depuis le début."""
    debut = progression.date_debut_programme() or _dt.date.fromisoformat(date_str)
    d = _dt.date.fromisoformat(date_str)
    if d < debut:
        return 0
    n = 0
    cur = debut
    while cur < d:
        if cur.weekday() != 5:      # on saute le samedi (full abdos)
            n += 1
        cur += _dt.timedelta(days=1)
    return n % 3


def _cible(exo: dict, mexo: dict, series: int) -> str:
    """« 4 × 10-15 », « 3 × 40 s », « 4 × 45 s (circuit) »…"""
    unite = exo.get("unite") or "reps"
    rmin, rmax = mexo.get("reps_min"), mexo.get("reps_max")
    if (mexo.get("superset_group") == "circuit" and mexo.get("tempo")
            and "/" in str(mexo["tempo"])):
        effort = str(mexo["tempo"]).split("/")[0]
        return f"{series} × {effort} s"
    if rmin is None:
        return f"{series} × max"
    suffixe = {"secondes": " s", "metres": " m", "contacts": ""}.get(unite, "")
    if rmax and rmax != rmin:
        return f"{series} × {rmin}-{rmax}{suffixe}"
    return f"{series} × {rmin}{suffixe}"


def _libelle_tache(ligne: dict, series: int) -> str:
    """`ligne` = jointure seance_modele_exo × exercice (les deux à plat)."""
    txt = f"{ligne['nom']} — {_cible(ligne, ligne, series)}"
    if ligne.get("note"):
        txt += f" ({ligne['note']})"
    return txt


def _seance_du_modele(modele: dict, date_str: str) -> dict:
    """Récupère (ou crée) la ligne `seance` du jour pour ce modèle."""
    ident = f"seance-{date_str}-{modele['id']}"
    row = db.q1("SELECT * FROM seance WHERE uuid = ?", (ident,))
    if row:
        return row
    db.execute(
        "INSERT OR IGNORE INTO seance(uuid, seance_modele_id, date, statut, "
        "source) VALUES (?, ?, ?, 'planifie', 'pc')",
        (ident, modele["id"], date_str))
    return db.q1("SELECT * FROM seance WHERE uuid = ?", (ident,))


def _cap_plyo(lignes: list, date_str: str) -> list:
    """Plafonne la plyométrie à 60 contacts par séance.

    On sert d'abord **une série à chacun** (dans l'ordre de priorité : le
    palier de la semaine avant les accessoires), puis on complète jusqu'à la
    cible tant qu'il reste de la place. Un exercice qui ne rentre même pas pour
    une série est retiré — mieux vaut trois paliers travaillés qu'un seul saturé.
    """
    plyo = [l for l in lignes if l["categorie"] == "plyo"
            and (l["reps_min"] or 0) > 0]
    if not plyo:
        return lignes

    restant = progression.CONTACTS_MAX
    retenu = {}
    for ligne in plyo:                                   # 1 série chacun
        reps = ligne["reps_min"]
        if reps <= restant:
            retenu[id(ligne)] = 1
            restant -= reps
    for ligne in plyo:                                   # puis on complète
        if id(ligne) not in retenu:
            continue
        reps = ligne["reps_min"]
        rab = min(ligne["series_calc"] - 1, restant // reps)
        if rab > 0:
            retenu[id(ligne)] += rab
            restant -= rab * reps

    garde = []
    for ligne in lignes:
        if ligne["categorie"] != "plyo" or (ligne["reps_min"] or 0) <= 0:
            garde.append(ligne)
        elif id(ligne) in retenu:
            ligne["series_calc"] = retenu[id(ligne)]
            garde.append(ligne)
    return garde


def _exos_du_modele(modele_id: int, date_str: str, court=False) -> list:
    """Exos du modèle, plyométrie filtrée/complétée/plafonnée selon la semaine.

    Chaque ligne repart avec un `series_calc` : le nombre de séries réellement
    prévu ce jour-là (reprise, semaine allégée, version courte, plafond plyo).
    """
    lignes = db.q(
        "SELECT sme.*, e.code, e.nom, e.unite, e.categorie, e.chargeable, "
        "       e.groupe, e.lieu AS exo_lieu "
        "FROM seance_modele_exo sme JOIN exercice e ON e.id = sme.exercice_id "
        "WHERE sme.seance_modele_id = ? ORDER BY sme.ordre", (modele_id,))
    autorises, _label = progression.plyo_semaine(date_str)

    out = []
    presents_plyo = set()
    for ligne in lignes:
        if ligne["categorie"] == "plyo":
            if ligne["code"] not in autorises:
                continue        # pas encore (ou plus) au programme cette semaine
            presents_plyo.add(ligne["code"])
        out.append(ligne)

    # Paliers plyo prévus cette semaine mais absents du modèle : on les ajoute.
    if any(l["categorie"] == "plyo" for l in lignes):
        manquants = [c for c in autorises if c not in presents_plyo]
        for code in manquants:
            exo = db.q1("SELECT * FROM exercice WHERE code = ?", (code,))
            if not exo:
                continue
            out.append({
                "id": None, "seance_modele_id": modele_id,
                "exercice_id": exo["id"], "ordre": 0, "bloc": "explosif",
                "series_cible": PLYO_DEFAUT["series"],
                "reps_min": PLYO_DEFAUT["reps"],
                "reps_max": PLYO_DEFAUT["reps"],
                "repos_sec": PLYO_DEFAUT["repos"], "tempo": None,
                "charge_depart": None, "superset_group": None,
                "note": "Palier plyo de la semaine",
                "code": exo["code"], "nom": exo["nom"], "unite": exo["unite"],
                "categorie": exo["categorie"], "chargeable": exo["chargeable"],
                "groupe": exo["groupe"], "exo_lieu": exo["lieu"],
            })
        out.sort(key=lambda r: (0 if r["bloc"] == "echauffement" else
                                1 if r["bloc"] == "explosif" else
                                2 if r["bloc"] == "principal" else 3,
                                r["ordre"] or 0))

    if court:
        # Version courte des soirs de grosse journée : on garde les trois
        # premiers exercices du bloc plutôt qu'un seul — 15 min d'abdos qui
        # tombent à un exercice, ce n'est plus une séance.
        out = out[:3]
    for ligne in out:
        series = progression.series_ajustees(ligne["series_cible"], date_str)
        ligne["series_calc"] = min(series, 2) if court else series
    return _cap_plyo(out, date_str)


def _ref(ligne: dict):
    """(ref_type, ref_id) — l'exo injecté n'a pas de ligne de modèle."""
    if ligne.get("id"):
        return "seance_modele_exo", ligne["id"]
    return "exercice", ligne["exercice_id"]


def materialiser(date_str=None) -> str:
    """Crée les tâches du jour si elles n'existent pas. Idempotent."""
    date_str = date_str or jour_courant()
    prog = programme_actif()

    # --- coréen : toujours, même sans programme sport actif ---
    checklist = (CHECKLIST_COREEN_DIMANCHE if jour_semaine(date_str) == 7
                 else CHECKLIST_COREEN)
    if db.scalar("SELECT COUNT(*) FROM kr_semaine", default=0):
        for i, libelle in enumerate(checklist):
            db.execute(
                "INSERT OR IGNORE INTO tache_jour(date, domaine, ref_type, "
                "ref_id, libelle, ordre, fait) "
                "VALUES (?, 'coreen', 'checklist', ?, ?, ?, 0)",
                (date_str, i, libelle, i))

    if not prog:
        return date_str      # pas de programme sport : rien d'autre à poser

    jsem = jour_semaine(date_str)
    modeles = db.q(
        "SELECT * FROM seance_modele WHERE programme_id = ? AND jour_semaine = ? "
        "ORDER BY ordre_affichage", (prog["id"], jsem))

    # --- bloc core du soir : rotation A/B/C, sauf le samedi ---
    if jsem != 6:
        rotation = db.q(
            "SELECT * FROM seance_modele WHERE programme_id = ? "
            "AND jour_semaine = 0 ORDER BY ordre_affichage", (prog["id"],))
        if rotation:
            modeles = modeles + [rotation[_index_rotation_core(date_str)
                                          % len(rotation)]]

    jour_lourd = jsem in (1, 2, 4, 5)
    for modele in modeles:
        seance = _seance_du_modele(modele, date_str)
        domaine = DOMAINE_PAR_TYPE.get(modele["type"], "sport")
        # Jour lourd : le core du soir passe en version courte (1 exo, 2 séries).
        court = (modele["type"] == "core" and modele["jour_semaine"] == 0
                 and jour_lourd)
        lignes = _exos_du_modele(modele["id"], date_str, court)

        for ordre, ligne in enumerate(lignes, start=1):
            series = ligne["series_calc"]
            ref_type, ref_id = _ref(ligne)
            db.execute(
                "INSERT OR IGNORE INTO tache_jour(date, domaine, ref_type, "
                "ref_id, libelle, ordre, fait) VALUES (?,?,?,?,?,?,0)",
                (date_str, domaine, ref_type, ref_id,
                 _libelle_tache(ligne, series), ordre))
        # Mémorise la séance concernée pour retrouver le lien tâche -> séance.
        db.execute("UPDATE seance SET statut = COALESCE(statut, 'planifie') "
                   "WHERE id = ?", (seance["id"],))
    return date_str


# ------------------------------------------------------------- validation

def _taches(date_str: str, domaines) -> list:
    marques = ",".join("?" * len(domaines))
    return db.q(
        f"SELECT * FROM tache_jour WHERE date = ? AND domaine IN ({marques}) "
        f"ORDER BY domaine, ordre, id", (date_str, *domaines))


def domaine_valide(domaine: str, date_str: str) -> bool:
    """True si **toutes** les tâches obligatoires du domaine sont cochées."""
    cibles = DOMAINES_SPORT if domaine == "sport" else (DOMAINE_COREEN,)
    marques = ",".join("?" * len(cibles))
    row = db.q1(
        f"SELECT COUNT(*) AS total, SUM(fait) AS faits FROM tache_jour "
        f"WHERE date = ? AND domaine IN ({marques})", (date_str, *cibles))
    total = (row or {}).get("total") or 0
    faits = (row or {}).get("faits") or 0
    return total > 0 and faits == total


def cocher(tache_id: int, fait=True, source="pc") -> bool:
    """Coche/décoche une tâche, met à jour les streaks dans la foulée."""
    row = db.q1("SELECT date FROM tache_jour WHERE id = ?", (tache_id,))
    if not row:
        return False
    db.execute(
        "UPDATE tache_jour SET fait = ?, fait_ts = ?, source = ? WHERE id = ?",
        (1 if fait else 0, int(time.time()) if fait else None, source,
         tache_id))
    recalc_streaks(row["date"])
    return True


def cocher_domaine(date_str: str, domaine: str, fait=True, source="pc") -> int:
    """Coche toutes les tâches d'un domaine du jour (bouton « tout cocher »)."""
    n = db.execute_count(
        "UPDATE tache_jour SET fait = ?, fait_ts = ?, source = ? "
        "WHERE date = ? AND domaine = ?",
        (1 if fait else 0, int(time.time()) if fait else None, source,
         date_str, domaine))
    recalc_streaks(date_str)
    return n


# ---------------------------------------------------------------- streaks

def _jours_valides(domaine: str, date_str: str, profondeur=400) -> dict:
    """{date: bool} sur les N derniers jours — une seule requête."""
    cibles = DOMAINES_SPORT if domaine == "sport" else (DOMAINE_COREEN,)
    marques = ",".join("?" * len(cibles))
    rows = db.q(
        f"SELECT date, COUNT(*) AS total, SUM(fait) AS faits "
        f"FROM tache_jour WHERE domaine IN ({marques}) AND date <= ? "
        f"AND date > date(?, ?) GROUP BY date",
        (*cibles, date_str, date_str, f"-{int(profondeur)} day"))
    return {r["date"]: (r["total"] > 0 and (r["faits"] or 0) == r["total"])
            for r in rows}


def calcul_streak(domaine: str, date_str: str) -> int:
    """Jours consécutifs validés. Le jour en cours ne casse rien tant qu'il
    n'est pas fini : s'il n'est pas encore validé, on repart de la veille."""
    valides = _jours_valides(domaine, date_str)
    curseur = date_str
    if not valides.get(curseur):
        curseur = _decale(curseur, -1)
    n = 0
    while valides.get(curseur):
        n += 1
        curseur = _decale(curseur, -1)
    return n


def recalc_streaks(date_str=None) -> dict:
    """Recalcule et persiste les deux streaks. Renvoie leur état."""
    date_str = date_str or jour_courant()
    out = {}
    for domaine in ("sport", "coreen"):
        courant = calcul_streak(domaine, date_str)
        ligne = db.q1("SELECT * FROM streak WHERE domaine = ?", (domaine,))
        record = max(courant, (ligne or {}).get("record") or 0)
        dernier = (ligne or {}).get("dernier_jour_valide")
        if domaine_valide(domaine, date_str):
            dernier = date_str
        db.execute(
            "INSERT INTO streak(domaine, courant, record, dernier_jour_valide) "
            "VALUES (?,?,?,?) ON CONFLICT(domaine) DO UPDATE SET "
            "courant = excluded.courant, record = excluded.record, "
            "dernier_jour_valide = excluded.dernier_jour_valide",
            (domaine, courant, record, dernier))
        out[domaine] = {"courant": courant, "record": record,
                        "dernier": dernier}
    return out


def streaks() -> dict:
    out = {}
    for domaine in ("sport", "coreen"):
        row = db.q1("SELECT * FROM streak WHERE domaine = ?", (domaine,))
        out[domaine] = {"courant": (row or {}).get("courant") or 0,
                        "record": (row or {}).get("record") or 0,
                        "dernier": (row or {}).get("dernier_jour_valide")}
    return out


# ------------------------------------------------------------- la semaine

def semaine(date_str=None) -> list:
    """7 pastilles L→D : statut par domaine pour la semaine de `date_str`."""
    date_str = date_str or jour_courant()
    d = _dt.date.fromisoformat(date_str)
    lundi = d - _dt.timedelta(days=d.weekday())
    aujourdhui = jour_courant()
    out = []
    for i in range(7):
        jour = (lundi + _dt.timedelta(days=i)).isoformat()
        cellule = {"date": jour, "lettre": "LMMJVSD"[i],
                   "aujourdhui": jour == aujourdhui,
                   "futur": jour > aujourdhui}
        for domaine, cibles in (("sport", DOMAINES_SPORT),
                                ("coreen", (DOMAINE_COREEN,))):
            marques = ",".join("?" * len(cibles))
            row = db.q1(
                f"SELECT COUNT(*) AS total, SUM(fait) AS faits "
                f"FROM tache_jour WHERE date = ? AND domaine IN ({marques})",
                (jour, *cibles))
            total = (row or {}).get("total") or 0
            faits = (row or {}).get("faits") or 0
            if jour > aujourdhui or total == 0:
                etat = "avenir" if jour >= aujourdhui else "manque"
            elif faits == total:
                etat = "fait"
            elif jour == aujourdhui:
                # La journée n'est pas finie : elle est « en cours », pas
                # manquée. Afficher du rouge sur le jour même serait faux — et
                # décourageant un lundi matin.
                etat = "partiel" if faits else "encours"
            elif faits > 0:
                etat = "partiel"
            else:
                etat = "manque"
            cellule[domaine] = etat
            cellule[domaine + "_detail"] = f"{faits}/{total}"
        out.append(cellule)
    return out


# ----------------------------------------------------------- état du jour

def _exo_detail(ligne: dict, date_str: str, taches_par_ref: dict) -> dict:
    exo = db.q1("SELECT * FROM exercice WHERE id = ?", (ligne["exercice_id"],))
    if not exo:
        return None
    series = ligne["series_calc"]
    reco = progression.evaluer(exo, ligne, date_str)
    ref_type, ref_id = _ref(ligne)
    tache = taches_par_ref.get((ref_type, ref_id))
    return {
        "tache_id": (tache or {}).get("id"),
        "fait": bool((tache or {}).get("fait")),
        "exercice_id": exo["id"], "code": exo["code"], "nom": exo["nom"],
        "unite": exo["unite"], "groupe": exo["groupe"],
        "categorie": exo["categorie"], "chargeable": bool(exo["chargeable"]),
        "consignes": exo["consignes"],
        "erreurs_frequentes": exo["erreurs_frequentes"],
        "video_url": exo["video_url"],
        "variantes": json.loads(exo["variantes_json"] or "[]"),
        "bloc": ligne["bloc"], "ordre": ligne["ordre"],
        "series": series, "reps_min": ligne["reps_min"],
        "reps_max": ligne["reps_max"], "repos_sec": ligne["repos_sec"],
        "tempo": ligne["tempo"], "superset": ligne["superset_group"],
        "note": ligne["note"], "cible": _cible(exo, ligne, series),
        "charge_proposee": reco["charge"], "variante": reco["variante"],
        "progression": reco["action"], "conseil": reco["raison"],
    }


def _seances_du_jour(date_str: str, taches_par_ref: dict) -> list:
    prog = programme_actif()
    if not prog:
        return []
    jsem = jour_semaine(date_str)
    modeles = db.q(
        "SELECT * FROM seance_modele WHERE programme_id = ? AND jour_semaine = ? "
        "ORDER BY ordre_affichage", (prog["id"], jsem))
    if jsem != 6:
        rotation = db.q(
            "SELECT * FROM seance_modele WHERE programme_id = ? "
            "AND jour_semaine = 0 ORDER BY ordre_affichage", (prog["id"],))
        if rotation:
            modeles = modeles + [rotation[_index_rotation_core(date_str)
                                          % len(rotation)]]

    jour_lourd = jsem in (1, 2, 4, 5)
    out = []
    for modele in modeles:
        seance = db.q1("SELECT * FROM seance WHERE uuid = ?",
                       (f"seance-{date_str}-{modele['id']}",))
        court = (modele["type"] == "core" and modele["jour_semaine"] == 0
                 and jour_lourd)
        lignes = _exos_du_modele(modele["id"], date_str, court)
        exos = [x for x in (_exo_detail(l, date_str, taches_par_ref)
                            for l in lignes) if x]
        contacts = sum((x["series"] or 0) * (x["reps_min"] or 0)
                       for x in exos if x["categorie"] == "plyo")
        out.append({
            "seance_id": (seance or {}).get("id"),
            "modele_id": modele["id"], "nom": modele["nom"],
            "lieu": modele["lieu"], "type": modele["type"],
            "duree_cible_min": modele["duree_cible_min"],
            "domaine": DOMAINE_PAR_TYPE.get(modele["type"], "sport"),
            "statut": (seance or {}).get("statut") or "planifie",
            "debut_ts": (seance or {}).get("debut_ts"),
            "version_courte": court,
            "plyo_libelle": progression.plyo_semaine(date_str)[1],
            "contacts_plyo": contacts,
            "contacts_max": progression.CONTACTS_MAX,
            "plan_course": (progression.course_semaine(date_str)
                            if modele["type"] == "cardio" else None),
            "exos": exos,
            "total": len(exos),
            "faits": sum(1 for x in exos if x["fait"]),
        })
    return out


def semaine_coreen(date_str=None):
    """La semaine de coréen en cours (ou la plus proche si hors programme)."""
    date_str = date_str or jour_courant()
    row = db.q1("SELECT * FROM kr_semaine WHERE date_debut <= ? "
                "AND date_fin >= ? ORDER BY numero LIMIT 1",
                (date_str, date_str))
    if row:
        return row
    row = db.q1("SELECT * FROM kr_semaine WHERE date_debut > ? "
                "ORDER BY numero LIMIT 1", (date_str,))
    return row or db.q1("SELECT * FROM kr_semaine ORDER BY numero DESC LIMIT 1")


def cartes_dues(now=None) -> int:
    now = now if now is not None else time.time()
    return int(db.scalar("SELECT COUNT(*) FROM kr_carte "
                         "WHERE suspendu = 0 AND due <= ?", (now,), default=0))


def exercice_coreen_du_jour(date_str: str):
    """Rotation reco → prod → trous → roleplay → écoute, un par jour."""
    sem = semaine_coreen(date_str)
    if not sem:
        return None
    from .seed_coreen import ROTATION_EXOS
    ordinal = _dt.date.fromisoformat(date_str).toordinal()
    typ = ROTATION_EXOS[ordinal % len(ROTATION_EXOS)]
    row = db.q1("SELECT * FROM kr_exercice WHERE semaine_id = ? AND type = ? "
                "LIMIT 1", (sem["id"], typ))
    return row or db.q1("SELECT * FROM kr_exercice WHERE semaine_id = ? LIMIT 1",
                        (sem["id"],))


def etat_jour(date_str=None, materialise=True) -> dict:
    """L'état complet d'une journée — sert l'onglet Aujourd'hui ET l'API.

    `materialise=False` donne un **aperçu** : le plan est calculé depuis le
    programme sans rien écrire en base. C'est ce qui sert à embarquer les
    4 semaines à venir dans le bundle mobile sans polluer `tache_jour` avec des
    journées qui n'ont pas encore commencé.
    """
    date_str = date_str or jour_courant()
    if materialise:
        materialiser(date_str)

    taches = _taches(date_str, DOMAINES_SPORT + (DOMAINE_COREEN,))
    par_ref = {(t["ref_type"], t["ref_id"]): t for t in taches}

    seances = _seances_du_jour(date_str, par_ref)
    sem_kr = semaine_coreen(date_str)
    checklist = [t for t in taches if t["domaine"] == DOMAINE_COREEN]
    exo_kr = exercice_coreen_du_jour(date_str)

    return {
        "date": date_str,
        "libelle": libelle_date(date_str),
        "jour_semaine": jour_semaine(date_str),
        "semaine_programme": progression.semaine_programme(date_str),
        "allegee": progression.est_semaine_allegee(date_str),
        "reprise": progression.est_reprise(date_str),
        "streaks": streaks(),
        "valide": {"sport": domaine_valide("sport", date_str),
                   "coreen": domaine_valide("coreen", date_str)},
        "seances": [s for s in seances if s["domaine"] in ("sport", "prehab")],
        "core": next((s for s in seances if s["domaine"] == "core"), None),
        "cardio": next((s for s in seances if s["domaine"] == "cardio"), None),
        "coreen": {
            "semaine": (sem_kr or {}).get("numero"),
            "theme": (sem_kr or {}).get("theme"),
            "note_culture": (sem_kr or {}).get("note_culture"),
            "cartes_dues": cartes_dues(),
            "checklist": [{"id": t["id"], "libelle": t["libelle"],
                           "fait": bool(t["fait"])} for t in checklist],
            "exercice": ({"id": exo_kr["id"], "type": exo_kr["type"],
                          "titre": exo_kr["titre"]} if exo_kr else None),
        },
        "conseils": progression.conseils(date_str),
        "semaine": semaine(date_str),
    }


# ---------------------------------------------------------- vie des séances

def demarrer_seance(seance_id: int, source="pc") -> bool:
    row = db.q1("SELECT id, debut_ts FROM seance WHERE id = ?", (seance_id,))
    if not row:
        return False
    db.execute("UPDATE seance SET statut = 'en_cours', debut_ts = ?, "
               "source = ? WHERE id = ?",
               (row["debut_ts"] or int(time.time()), source, seance_id))
    return True


def terminer_seance(seance_id: int, rpe=None, humeur=None, douleur_genou=None,
                    douleur_hanche=None, note=None, duree_s=None,
                    source="pc") -> dict:
    """Clôture une séance : statut, durée, douleurs, records battus."""
    row = db.q1("SELECT * FROM seance WHERE id = ?", (seance_id,))
    if not row:
        return {"ok": False, "records": []}
    fin = int(time.time())
    if duree_s is None:
        duree_s = max(0, fin - (row["debut_ts"] or fin))

    modele = db.q1("SELECT * FROM seance_modele WHERE id = ?",
                   (row["seance_modele_id"],)) or {}
    domaine = DOMAINE_PAR_TYPE.get(modele.get("type"), "sport")
    reste = db.scalar(
        "SELECT COUNT(*) FROM tache_jour WHERE date = ? AND domaine = ? "
        "AND fait = 0", (row["date"], domaine), default=0)
    statut = "partiel" if reste else "fait"

    db.execute(
        "UPDATE seance SET statut = ?, fin_ts = ?, duree_s = ?, rpe = ?, "
        "humeur = ?, douleur_genou = ?, douleur_hanche = ?, note = ?, "
        "source = ? WHERE id = ?",
        (statut, fin, duree_s, rpe, humeur, douleur_genou, douleur_hanche,
         note, source, seance_id))
    records = progression.maj_records(seance_id)
    recalc_streaks(row["date"])
    return {"ok": True, "statut": statut, "duree_s": duree_s,
            "records": records}


def marquer_manquee(seance_id: int, source="pc") -> bool:
    """Une séance manquée **reste manquée** : pas de report au lendemain."""
    row = db.q1("SELECT date FROM seance WHERE id = ?", (seance_id,))
    if not row:
        return False
    db.execute("UPDATE seance SET statut = 'manque', source = ? WHERE id = ?",
               (source, seance_id))
    recalc_streaks(row["date"])
    return True


def enregistrer_serie(seance_id: int, exercice_id: int, index_serie: int,
                      reps=None, charge_kg=None, duree_s=None, rpe=None,
                      repos_reel_s=None, variante=None, echec=0, note=None,
                      ts=None, source="pc", uid=None) -> int:
    """Écrit une série (idempotent sur l'uuid ET sur le triplet de place).

    Conflit sur une même (séance, exercice, index) : **le plus récent gagne**.
    """
    ts = int(ts or time.time())
    uid = uid or str(_uuid.uuid4())
    with db._lock:                                    # noqa: SLF001 (module ami)
        c = db.conn()
        existant = c.execute("SELECT id, ts FROM serie WHERE uuid = ?",
                             (uid,)).fetchone()
        if existant is None:
            existant = c.execute(
                "SELECT id, ts FROM serie WHERE seance_id = ? "
                "AND exercice_id = ? AND index_serie = ?",
                (seance_id, exercice_id, index_serie)).fetchone()
        champs = (reps, charge_kg, duree_s, rpe, repos_reel_s, variante,
                  int(bool(echec)), note, ts, source)
        if existant is None:
            cur = c.execute(
                "INSERT INTO serie(uuid, seance_id, exercice_id, index_serie, "
                "reps, charge_kg, duree_s, rpe, repos_reel_s, variante, echec, "
                "note, ts, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (uid, seance_id, exercice_id, index_serie, *champs))
            rid = cur.lastrowid
        else:
            rid = existant["id"]
            if ts >= (existant["ts"] or 0):
                c.execute(
                    "UPDATE serie SET reps = ?, charge_kg = ?, duree_s = ?, "
                    "rpe = ?, repos_reel_s = ?, variante = ?, echec = ?, "
                    "note = ?, ts = ?, source = ? WHERE id = ?",
                    (*champs, rid))
        c.commit()
    return rid


def enregistrer_cardio(date_str=None, type_="course", distance_km=None,
                       duree_s=None, fc_moy=None, ressenti=None, note=None,
                       source="pc", uid=None) -> int:
    """Course, vélo, tapis ou **foot en salle** (loggable des deux côtés)."""
    date_str = date_str or jour_courant()
    uid = uid or str(_uuid.uuid4())
    allure = None
    if distance_km and duree_s and float(distance_km) > 0:
        allure = round(float(duree_s) / float(distance_km), 1)
    db.execute(
        "INSERT INTO cardio(uuid, date, type, distance_km, duree_s, "
        "allure_s_km, fc_moy, ressenti, note, source) "
        "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(uuid) DO UPDATE SET "
        "date = excluded.date, type = excluded.type, "
        "distance_km = excluded.distance_km, duree_s = excluded.duree_s, "
        "allure_s_km = excluded.allure_s_km, fc_moy = excluded.fc_moy, "
        "ressenti = excluded.ressenti, note = excluded.note",
        (uid, date_str, type_, distance_km, duree_s, allure, fc_moy, ressenti,
         note, source))
    return int(db.scalar("SELECT id FROM cardio WHERE uuid = ?", (uid,),
                         default=0))


def resume_texte(date_str=None) -> str:
    """Résumé texte d'une journée — filet de sécurité « copier le résumé »."""
    date_str = date_str or jour_courant()
    lignes = [f"MF Cockpit — {libelle_date(date_str)}", ""]
    seances = db.q(
        "SELECT s.id, s.statut, s.duree_s, s.rpe, s.douleur_genou, "
        "s.douleur_hanche, m.nom, m.lieu FROM seance s "
        "LEFT JOIN seance_modele m ON m.id = s.seance_modele_id "
        "WHERE s.date = ? ORDER BY s.id", (date_str,))
    for s in seances:
        duree = f" · {(s['duree_s'] or 0) // 60} min" if s["duree_s"] else ""
        lignes.append(f"[{s['statut']}] {s['nom'] or 'Séance'} "
                      f"({s['lieu'] or '—'}){duree}")
        series = db.q(
            "SELECT e.nom, r.index_serie, r.reps, r.charge_kg, r.duree_s, "
            "r.rpe, r.variante FROM serie r "
            "JOIN exercice e ON e.id = r.exercice_id "
            "WHERE r.seance_id = ? ORDER BY e.nom, r.index_serie", (s["id"],))
        courant = None
        for r in series:
            if r["nom"] != courant:
                courant = r["nom"]
                lignes.append(f"  {courant}")
            morceaux = []
            if r["reps"]:
                morceaux.append(f"{r['reps']} reps")
            if r["charge_kg"]:
                morceaux.append(f"{r['charge_kg']:g} kg")
            if r["duree_s"]:
                morceaux.append(f"{r['duree_s']} s")
            if r["variante"]:
                morceaux.append(r["variante"])
            lignes.append(f"    #{r['index_serie']} " + " · ".join(morceaux))
        if s["douleur_genou"] is not None or s["douleur_hanche"] is not None:
            lignes.append(f"  Douleur genou {s['douleur_genou']}/10 · "
                          f"hanche {s['douleur_hanche']}/10 · "
                          f"RPE {s['rpe'] or '—'}")
    for c in db.q("SELECT * FROM cardio WHERE date = ?", (date_str,)):
        lignes.append(f"[cardio] {c['type']} · {c['distance_km'] or 0:g} km · "
                      f"{(c['duree_s'] or 0) // 60} min")
    etat = {d: domaine_valide(d, date_str) for d in ("sport", "coreen")}
    lignes.append("")
    lignes.append(f"Sport {'validé' if etat['sport'] else 'non validé'} · "
                  f"Coréen {'validé' if etat['coreen'] else 'non validé'}")
    return "\n".join(lignes)
