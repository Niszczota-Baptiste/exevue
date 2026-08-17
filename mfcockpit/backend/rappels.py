"""Rappels sport / coréen — deux fils totalement indépendants.

Point de départ = **l'ouverture du cockpit** (donc l'allumage du PC, puisque
l'app peut démarrer avec Windows). Rappel à T+2 h, puis toutes les 2 h.

Le fil sport s'arrête dès que le domaine sport du jour est validé, le fil coréen
pareil, chacun de son côté. Les deux validés : plus rien jusqu'à demain.

Aucun thread supplémentaire : `tick()` est appelée par le poller existant. La
trace en base (`rappel`) évite les doublons après un redémarrage — si le PC
redémarre à 15 h, on ne repart pas de zéro.
"""
import datetime as _dt
import time

from . import db, jour, notify

DOMAINES = ("sport", "coreen")

# Ouverture du cockpit : sert de point de départ au premier rappel.
_ouverture_ts = None


def demarrer(maintenant=None):
    """À appeler une fois, au lancement de l'app."""
    global _ouverture_ts
    _ouverture_ts = maintenant if maintenant is not None else time.time()


def actif() -> bool:
    return db.reglage_bool("rappels.actif", True)


def _intervalle_s() -> float:
    return max(0.25, float(db.reglage_int("rappels.intervalle_h", 2))) * 3600.0


def _dans_la_plage(moment: _dt.datetime) -> bool:
    debut = db.reglage_int("rappels.debut_h", 9)
    fin = db.reglage_int("rappels.fin_h", 22)
    return debut <= moment.hour < fin


def _domaine_arme(domaine: str) -> bool:
    return db.reglage_bool(f"rappels.{domaine}", True)


def _dernier_envoi(domaine: str, date_str: str):
    return db.scalar(
        "SELECT MAX(ts) FROM rappel WHERE domaine = ? AND date = ? AND envoye = 1",
        (domaine, date_str), default=None)


# --------------------------------------------------------------- textes

def texte_sport(date_str: str):
    """« Jeudi · Haut du corps maison — 8 exos, 45 min ». Jamais générique."""
    etat = jour.etat_jour(date_str)
    seances = etat["seances"] or ([etat["core"]] if etat["core"] else [])
    if not seances:
        return None
    s = seances[0]
    if s["statut"] == "manque":
        return None                      # marquée manquée : on ne harcèle pas
    reste = s["total"] - s["faits"]
    jour_nom = jour.JOURS_FR[etat["jour_semaine"] - 1].capitalize()
    lieu = {"maison": "maison", "salle": "salle",
            "exterieur": "extérieur"}.get(s["lieu"], s["lieu"] or "")
    titre = f"{jour_nom} · {s['nom']} {lieu}".strip()
    detail = f"{reste} exo{'s' if reste > 1 else ''} restant" \
             f"{'s' if reste > 1 else ''}, {s['duree_cible_min']} min"
    if etat["allegee"]:
        detail += " · semaine allégée"
    return titre, detail


def texte_coreen(date_str: str):
    """« Coréen S3 · Restaurant — 14 cartes dues »."""
    etat = jour.etat_jour(date_str)
    kr = etat["coreen"]
    if not kr.get("semaine"):
        return None
    reste = sum(1 for t in kr["checklist"] if not t["fait"])
    titre = f"Coréen S{kr['semaine']} · {kr['theme']}"
    detail = f"{kr['cartes_dues']} carte{'s' if kr['cartes_dues'] > 1 else ''} due" \
             f"{'s' if kr['cartes_dues'] > 1 else ''}"
    if reste:
        detail += f", {reste} case{'s' if reste > 1 else ''} à cocher"
    return titre, detail


_TEXTES = {"sport": texte_sport, "coreen": texte_coreen}


# ----------------------------------------------------------------- tick

def tick(maintenant=None) -> list:
    """Envoie les rappels dus. Appelée par le poller, jamais bloquante.

    Renvoie la liste des domaines notifiés (utile aux tests).
    """
    if not actif():
        return []
    maintenant = maintenant if maintenant is not None else time.time()
    moment = _dt.datetime.fromtimestamp(maintenant)
    if not _dans_la_plage(moment):
        return []                        # hors plage horaire : silence

    date_str = jour.jour_courant(maintenant)
    depart = _ouverture_ts if _ouverture_ts is not None else maintenant
    intervalle = _intervalle_s()
    envoyes = []

    for domaine in DOMAINES:
        if not _domaine_arme(domaine):
            continue
        if jour.domaine_valide(domaine, date_str):
            continue                     # ce fil-là est éteint pour la journée

        dernier = _dernier_envoi(domaine, date_str)
        reference = max(dernier or 0, depart)
        if maintenant - reference < intervalle:
            continue

        try:
            contenu = _TEXTES[domaine](date_str)
        except Exception:
            contenu = None
        if not contenu:
            continue
        titre, detail = contenu

        db.execute(
            "INSERT INTO rappel(date, ts, domaine, envoye, ouvert) "
            "VALUES (?, ?, ?, 1, 0)", (date_str, int(maintenant), domaine))
        notify.notify(titre, detail, ouvrir_cockpit=True)
        envoyes.append(domaine)
    return envoyes


def marquer_ouvert(domaine=None):
    """Trace le clic sur une notification (statistique d'usage)."""
    date_str = jour.jour_courant()
    if domaine:
        db.execute("UPDATE rappel SET ouvert = 1 WHERE date = ? AND domaine = ? "
                   "AND ouvert = 0", (date_str, domaine))
    else:
        db.execute("UPDATE rappel SET ouvert = 1 WHERE date = ? AND ouvert = 0",
                   (date_str,))


def historique(jours=7) -> list:
    return db.q(
        "SELECT date, domaine, COUNT(*) AS envoyes, SUM(ouvert) AS ouverts "
        "FROM rappel WHERE date > date('now', ?) "
        "GROUP BY date, domaine ORDER BY date DESC",
        (f"-{int(jours)} day",))
