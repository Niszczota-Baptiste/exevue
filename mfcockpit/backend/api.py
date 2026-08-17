"""API JSON du cockpit — la logique, sans le transport.

`webserver.py` ne fait qu'appeler `traiter()` : ça garde le serveur HTTP tout
bête et rend l'API testable sans ouvrir de socket.

Routes :

    GET  /api/jour?date=YYYY-MM-DD   état complet d'une journée
    GET  /api/bundle                 tout ce qu'il faut pour tenir hors ligne
    POST /api/sync                   file d'opérations du téléphone (idempotente)
    GET  /api/media/<code>.<ext>     média d'exercice (ou schéma SVG de secours)
    GET  /api/etat                   heure serveur, version du bundle, file

**Idempotence** : chaque opération venue du téléphone porte un `uuid` généré
côté client. On journalise l'opération dans `sync_op` et on refuse de la
rejouer. Appuyer deux fois sur « synchroniser » ne duplique rien.
"""
import datetime as _dt
import hashlib
import json
import os
import time

from . import db, jour, korean, paths, progression

TABLES_SYNC = ("serie", "seance", "cardio", "tache_jour", "kr_revue",
               "kr_seance", "mesure")

EXTENSIONS_MEDIA = (".gif", ".png", ".jpg", ".jpeg", ".webp", ".mp4", ".svg")
MIME_MEDIA = {".gif": "image/gif", ".png": "image/png", ".jpg": "image/jpeg",
              ".jpeg": "image/jpeg", ".webp": "image/webp",
              ".mp4": "video/mp4", ".svg": "image/svg+xml"}

JOURS_BUNDLE = 28          # 4 semaines de séances à venir


# --------------------------------------------------------------- version

def version_bundle() -> str:
    """Empreinte courte : change dès que le contenu servi change."""
    morceaux = []
    for table in ("exercice", "seance_modele", "seance_modele_exo",
                  "tache_jour", "seance", "serie", "kr_item", "kr_carte"):
        morceaux.append(str(db.scalar(f"SELECT COUNT(*) FROM {table}",
                                      default=0)))
    morceaux.append(str(int(db.scalar("SELECT MAX(fait_ts) FROM tache_jour",
                                      default=0) or 0)))
    morceaux.append(str(int(db.scalar("SELECT MAX(ts) FROM serie",
                                      default=0) or 0)))
    morceaux.append(jour.jour_courant())
    return hashlib.sha1("|".join(morceaux).encode()).hexdigest()[:12]


def ops_en_attente() -> int:
    return int(db.scalar("SELECT COUNT(*) FROM sync_op WHERE applique = 0",
                         default=0))


# ------------------------------------------------------------------ /jour

def etat_du_jour(date_str=None) -> dict:
    return jour.etat_jour(date_str or jour.jour_courant())


# ---------------------------------------------------------------- /bundle

def _exercices_bundle() -> list:
    out = []
    for exo in db.q("SELECT * FROM exercice WHERE actif = 1 ORDER BY id"):
        out.append({
            "id": exo["id"], "code": exo["code"], "nom": exo["nom"],
            "categorie": exo["categorie"], "groupe": exo["groupe"],
            "unite": exo["unite"], "chargeable": bool(exo["chargeable"]),
            "lieu": exo["lieu"], "equipement": exo["equipement"],
            "consignes": exo["consignes"],
            "erreurs_frequentes": exo["erreurs_frequentes"],
            "video_url": exo["video_url"],
            "variantes": json.loads(exo["variantes_json"] or "[]"),
            "media": f"/api/media/{exo['code']}{_extension_media(exo['code'])}",
            "derniere_charge": progression.derniere_charge(exo["id"]),
            "derniere_variante": progression.derniere_variante(exo["id"]),
        })
    return out


def _programme_bundle() -> dict:
    prog = jour.programme_actif()
    if not prog:
        return {}
    modeles = db.q("SELECT * FROM seance_modele WHERE programme_id = ? "
                   "ORDER BY jour_semaine, ordre_affichage", (prog["id"],))
    for m in modeles:
        m["exos"] = db.q(
            "SELECT sme.*, e.code FROM seance_modele_exo sme "
            "JOIN exercice e ON e.id = sme.exercice_id "
            "WHERE sme.seance_modele_id = ? ORDER BY sme.ordre", (m["id"],))
    return {"id": prog["id"], "nom": prog["nom"], "note": prog["note"],
            "date_debut": prog["date_debut"], "modeles": modeles}


def _coreen_bundle() -> dict:
    sem = jour.semaine_coreen()
    if not sem:
        return {}
    horizon = time.time() + 7 * 86400
    cartes = db.q(
        "SELECT c.id, c.item_id, c.direction, c.due, c.interval, c.reps, "
        "       i.kr, i.romaja, i.fr, i.exemple_kr, i.exemple_fr, i.type "
        "FROM kr_carte c JOIN kr_item i ON i.id = c.item_id "
        "WHERE c.suspendu = 0 AND c.due <= ? ORDER BY c.due", (horizon,))
    exercices = []
    for exo in korean.exercices_semaine(sem["id"]):
        contenu = korean.contenu_exercice(exo["id"]) or {}
        exercices.append({"id": exo["id"], "type": exo["type"],
                          "titre": exo["titre"],
                          "duree_cible_min": exo["duree_cible_min"],
                          "contenu": contenu})
    return {
        "semaine": {"numero": sem["numero"], "theme": sem["theme"],
                    "date_debut": sem["date_debut"],
                    "date_fin": sem["date_fin"],
                    "note_culture": sem["note_culture"],
                    "objectifs": json.loads(sem["objectifs_json"] or "[]")},
        "items": korean.items(sem["id"]),
        "cartes": cartes,
        "exercices": exercices,
        "checklist": jour.CHECKLIST_COREEN,
    }


def bundle() -> dict:
    """TOUT ce qu'il faut pour dérouler une séance sans réseau."""
    aujourdhui = jour.jour_courant()
    jours = [jour.etat_jour(aujourdhui)]          # aujourd'hui : matérialisé
    for i in range(1, JOURS_BUNDLE):
        date_str = (_dt.date.fromisoformat(aujourdhui)
                    + _dt.timedelta(days=i)).isoformat()
        jours.append(jour.etat_jour(date_str, materialise=False))
    return {
        "version": version_bundle(),
        "genere_ts": int(time.time()),
        "jours": jours,
        "programme": _programme_bundle(),
        "exercices": _exercices_bundle(),
        "coreen": _coreen_bundle(),
        "streaks": jour.streaks(),
        "reglages": {
            "pas_charge_kg": float(db.reglage("sport.pas_charge_kg", 2.5)),
            "saisie_libre_coreen": db.reglage_bool("coreen.saisie_libre", False),
            "contacts_max": progression.CONTACTS_MAX,
        },
    }


# ------------------------------------------------------------------ /sync

def _op_serie(payload, ts, source):
    jour.enregistrer_serie(
        seance_id=payload.get("seance_id"),
        exercice_id=payload.get("exercice_id"),
        index_serie=payload.get("index_serie"),
        reps=payload.get("reps"), charge_kg=payload.get("charge_kg"),
        duree_s=payload.get("duree_s"), rpe=payload.get("rpe"),
        repos_reel_s=payload.get("repos_reel_s"),
        variante=payload.get("variante"), echec=payload.get("echec", 0),
        note=payload.get("note"), ts=ts, source=source,
        uid=payload.get("uuid"))


def _op_seance(payload, ts, source):
    seance_id = payload.get("seance_id") or payload.get("id")
    if not seance_id:
        return
    if payload.get("statut") == "manque":
        jour.marquer_manquee(seance_id, source=source)
        return
    if payload.get("statut") == "en_cours":
        jour.demarrer_seance(seance_id, source=source)
        return
    jour.terminer_seance(
        seance_id, rpe=payload.get("rpe"), humeur=payload.get("humeur"),
        douleur_genou=payload.get("douleur_genou"),
        douleur_hanche=payload.get("douleur_hanche"),
        note=payload.get("note"), duree_s=payload.get("duree_s"),
        source=source)


def _op_cardio(payload, ts, source):
    jour.enregistrer_cardio(
        date_str=payload.get("date"), type_=payload.get("type", "course"),
        distance_km=payload.get("distance_km"),
        duree_s=payload.get("duree_s"), fc_moy=payload.get("fc_moy"),
        ressenti=payload.get("ressenti"), note=payload.get("note"),
        source=source, uid=payload.get("uuid"))


def _op_tache(payload, ts, source):
    tache_id = payload.get("id") or payload.get("tache_id")
    if tache_id:
        jour.cocher(tache_id, bool(payload.get("fait", True)), source=source)


def _op_kr_revue(payload, ts, source):
    korean.noter(payload.get("carte_id"), bool(payload.get("su")),
                 temps_ms=payload.get("temps_ms"), source=source,
                 uid=payload.get("uuid"))


def _op_kr_seance(payload, ts, source):
    db.execute(
        "INSERT INTO kr_seance(uuid, date, statut, duree_s, checklist_json, "
        "cartes_vues, cartes_sues, note, source) VALUES (?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(uuid) DO UPDATE SET statut = excluded.statut, "
        "duree_s = excluded.duree_s, checklist_json = excluded.checklist_json, "
        "cartes_vues = excluded.cartes_vues, cartes_sues = excluded.cartes_sues,"
        " note = excluded.note",
        (payload.get("uuid"), payload.get("date") or jour.jour_courant(),
         payload.get("statut", "fait"), payload.get("duree_s"),
         json.dumps(payload.get("checklist") or [], ensure_ascii=False),
         payload.get("cartes_vues", 0), payload.get("cartes_sues", 0),
         payload.get("note"), source))


def _op_mesure(payload, ts, source):
    db.execute(
        "INSERT INTO mesure(date, poids_kg, tour_taille, tour_bras, "
        "tour_cuisse, note) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(date) DO UPDATE SET poids_kg = excluded.poids_kg, "
        "tour_taille = excluded.tour_taille, tour_bras = excluded.tour_bras, "
        "tour_cuisse = excluded.tour_cuisse, note = excluded.note",
        (payload.get("date") or jour.jour_courant(), payload.get("poids_kg"),
         payload.get("tour_taille"), payload.get("tour_bras"),
         payload.get("tour_cuisse"), payload.get("note")))


_APPLICATEURS = {
    "serie": _op_serie, "seance": _op_seance, "cardio": _op_cardio,
    "tache_jour": _op_tache, "kr_revue": _op_kr_revue,
    "kr_seance": _op_kr_seance, "mesure": _op_mesure,
}


def sync(ops, device="tel") -> dict:
    """Applique une file d'opérations. Rejouable sans effet de bord."""
    appliquees = ignorees = 0
    erreurs = []
    for op in ops or []:
        if not isinstance(op, dict):
            ignorees += 1
            continue
        uid = op.get("uuid")
        table = op.get("table")
        if not uid or table not in TABLES_SYNC:
            ignorees += 1
            erreurs.append({"uuid": uid, "erreur": f"table refusée : {table}"})
            continue

        deja = db.q1("SELECT applique FROM sync_op WHERE uuid = ?", (uid,))
        if deja and deja["applique"]:
            ignorees += 1
            continue

        payload = op.get("payload") or {}
        payload.setdefault("uuid", uid)
        ts = int(op.get("ts") or time.time())
        db.execute(
            "INSERT INTO sync_op(uuid, table_cible, payload_json, ts, "
            "applique, device) VALUES (?,?,?,?,0,?) "
            "ON CONFLICT(uuid) DO UPDATE SET payload_json = excluded.payload_json,"
            " ts = excluded.ts",
            (uid, table, json.dumps(payload, ensure_ascii=False), ts, device))
        try:
            _APPLICATEURS[table](payload, ts, "tel")
            db.execute("UPDATE sync_op SET applique = 1 WHERE uuid = ?", (uid,))
            appliquees += 1
        except Exception as exc:                      # une op cassée n'arrête pas la file
            erreurs.append({"uuid": uid, "erreur": str(exc)})
    return {"appliquees": appliquees, "ignorees": ignorees, "erreurs": erreurs,
            "version": version_bundle(), "en_attente": ops_en_attente()}


# ------------------------------------------------------------------ média

def _extension_media(code: str) -> str:
    """Extension du fichier trouvé pour cet exercice, `.svg` par défaut."""
    for dossier in (paths.USER_MEDIA_DIR, paths.MEDIA_DIR):
        for ext in EXTENSIONS_MEDIA:
            if os.path.isfile(os.path.join(dossier, code + ext)):
                return ext
    return ".svg"


def media(nom_fichier: str):
    """(mime, octets) — le fichier posé, sinon un schéma SVG généré."""
    code, ext = os.path.splitext(os.path.basename(nom_fichier))
    if ext.lower() not in EXTENSIONS_MEDIA:
        return None
    for dossier in (paths.USER_MEDIA_DIR, paths.MEDIA_DIR):
        chemin = os.path.join(dossier, code + ext)
        if os.path.isfile(chemin):
            try:
                with open(chemin, "rb") as fh:
                    return MIME_MEDIA.get(ext.lower(),
                                          "application/octet-stream"), fh.read()
            except OSError:
                break
    exo = db.q1("SELECT * FROM exercice WHERE code = ?", (code,))
    if not exo:
        return None
    return "image/svg+xml", svg_secours(exo).encode("utf-8")


# Silhouette très simple + flèche de mouvement, orientée par groupe musculaire.
_FLECHES = {
    "quadriceps": (100, 150, 100, 95), "ischios": (100, 150, 100, 95),
    "fessiers": (100, 150, 100, 95), "mollets": (100, 165, 100, 130),
    "pectoraux": (100, 95, 158, 95), "dos": (158, 95, 100, 95),
    "epaules": (100, 95, 100, 42), "bras": (100, 120, 100, 82),
    "abdos": (100, 130, 100, 92), "tout": (100, 150, 100, 60),
}


def svg_secours(exo: dict) -> str:
    """Schéma maison (aucun média récupéré sur le web : question de droits)."""
    x1, y1, x2, y2 = _FLECHES.get(exo["groupe"], _FLECHES["tout"])
    nom = (exo["nom"] or "").replace("&", "et").replace("<", "").replace(">", "")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"
     width="200" height="200" role="img" aria-label="{nom}">
  <rect width="200" height="200" fill="#13101d"/>
  <g stroke="#a78bfa" stroke-width="3" fill="none"
     stroke-linecap="round" stroke-linejoin="round">
    <circle cx="100" cy="42" r="13"/>
    <path d="M100 55 V115"/>
    <path d="M100 68 L72 95 M100 68 L128 95"/>
    <path d="M100 115 L80 165 M100 115 L120 165"/>
    <path d="M80 165 L70 170 M120 165 L130 170"/>
  </g>
  <defs>
    <marker id="p" markerWidth="8" markerHeight="8" refX="5" refY="4"
            orient="auto"><path d="M0 0 L8 4 L0 8 z" fill="#f0a0b8"/></marker>
  </defs>
  <path d="M{x1} {y1} L{x2} {y2}" stroke="#f0a0b8" stroke-width="3"
        fill="none" marker-end="url(#p)" stroke-dasharray="6 4"/>
  <text x="100" y="190" fill="#8b85a0" font-size="11" text-anchor="middle"
        font-family="system-ui, sans-serif">{nom[:28]}</text>
</svg>"""


# ------------------------------------------------------------------- /etat

def etat() -> dict:
    return {
        "heure_serveur": int(time.time()),
        "date": jour.jour_courant(),
        "version": version_bundle(),
        "en_attente": ops_en_attente(),
        "streaks": jour.streaks(),
    }


# --------------------------------------------------------------- routage

def traiter(chemin: str, params: dict, corps=None, methode="GET"):
    """(statut, mime, octets). `webserver.py` n'a plus qu'à poster ça."""
    def json_reponse(donnees, statut=200):
        return (statut, "application/json; charset=utf-8",
                json.dumps(donnees, ensure_ascii=False,
                           default=str).encode("utf-8"))

    if chemin == "/api/etat":
        return json_reponse(etat())
    if chemin == "/api/jour":
        return json_reponse(etat_du_jour(params.get("date")))
    if chemin == "/api/bundle":
        return json_reponse(bundle())
    if chemin == "/api/resume":
        return (200, "text/plain; charset=utf-8",
                jour.resume_texte(params.get("date")).encode("utf-8"))
    if chemin.startswith("/api/media/"):
        trouve = media(chemin[len("/api/media/"):])
        if trouve is None:
            return json_reponse({"erreur": "média introuvable"}, 404)
        return (200, trouve[0], trouve[1])
    if chemin == "/api/sync":
        if methode != "POST":
            return json_reponse({"erreur": "POST attendu"}, 405)
        try:
            charge = json.loads((corps or b"{}").decode("utf-8"))
        except ValueError:
            return json_reponse({"erreur": "JSON invalide"}, 400)
        ops = charge.get("ops") if isinstance(charge, dict) else charge
        return json_reponse(sync(ops, device=(charge.get("device", "tel")
                                              if isinstance(charge, dict)
                                              else "tel")))
    return json_reponse({"erreur": "route inconnue"}, 404)
