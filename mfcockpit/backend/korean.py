"""Coréen — SRS (SM-2 allégé) **au-dessus de SQLite**.

Historiquement le deck vivait dans `config.json` (`korean.deck`). Il est
désormais stocké dans `cockpit.db` (tables `kr_item` / `kr_carte` / `kr_revue`)
et la migration one-shot de `db.migrer_deck_legacy()` reprend l'ancien deck
**sans perdre les échéances**. La clé JSON reste en place en guise de sauvegarde
mais plus rien ne l'écrit.

La classe `Deck` reste exposée avec la même signature qu'avant : l'onglet
Coréen et `ui/app.py` continuent de fonctionner sans rien savoir de SQLite.

Chaque item porte **deux cartes** : `kr_fr` (reconnaissance) et `fr_kr`
(production). La seconde est suspendue tant que la première n'a pas atteint
3 réussites — on ne demande pas de produire ce qu'on ne reconnaît pas encore.
"""
import csv
import io
import json
import time
import uuid as _uuid

from . import db

DAY = 86400.0
FIELDS = ("kr", "romaja", "fr", "example")
SEUIL_DEBLOCAGE = 3       # réussites en kr_fr avant d'ouvrir fr_kr


# --------------------------------------------------------------- lecture

def items(semaine_id=None, limite=None) -> list:
    sql = ("SELECT i.*, s.numero AS semaine_numero, s.theme AS semaine_theme "
           "FROM kr_item i LEFT JOIN kr_semaine s ON s.id = i.semaine_id")
    params = []
    if semaine_id is not None:
        sql += " WHERE i.semaine_id = ?"
        params.append(semaine_id)
    sql += " ORDER BY COALESCE(s.numero, 99), i.ordre, i.id"
    if limite:
        sql += f" LIMIT {int(limite)}"
    return db.q(sql, tuple(params))


def carte_complete(carte_id: int):
    return db.q1(
        "SELECT c.*, i.kr, i.romaja, i.fr, i.exemple_kr, i.exemple_fr, "
        "       i.type AS item_type, i.tags, s.numero AS semaine "
        "FROM kr_carte c JOIN kr_item i ON i.id = c.item_id "
        "LEFT JOIN kr_semaine s ON s.id = i.semaine_id WHERE c.id = ?",
        (carte_id,))


def cartes_dues(limite=None, now=None, direction=None) -> list:
    """Cartes échues, les plus en retard d'abord."""
    now = time.time() if now is None else now
    sql = ("SELECT c.*, i.kr, i.romaja, i.fr, i.exemple_kr, i.exemple_fr, "
           "       i.type AS item_type, s.numero AS semaine "
           "FROM kr_carte c JOIN kr_item i ON i.id = c.item_id "
           "LEFT JOIN kr_semaine s ON s.id = i.semaine_id "
           "WHERE c.suspendu = 0 AND c.due <= ?")
    params = [now]
    if direction:
        sql += " AND c.direction = ?"
        params.append(direction)
    sql += " ORDER BY c.due"
    if limite:
        sql += f" LIMIT {int(limite)}"
    return db.q(sql, tuple(params))


def nb_dues(now=None) -> int:
    now = time.time() if now is None else now
    return int(db.scalar("SELECT COUNT(*) FROM kr_carte "
                         "WHERE suspendu = 0 AND due <= ?", (now,), default=0))


def previsions(jours=30, now=None) -> list:
    """Cartes à échoir par jour sur les N prochains jours (pour les stats)."""
    now = time.time() if now is None else now
    out = []
    for i in range(jours):
        debut, fin = now + i * DAY, now + (i + 1) * DAY
        out.append({
            "jour": i,
            "nb": int(db.scalar(
                "SELECT COUNT(*) FROM kr_carte WHERE suspendu = 0 "
                "AND due >= ? AND due < ?", (debut, fin), default=0)),
        })
    return out


# --------------------------------------------------------------- notation

def noter(carte_id: int, su: bool, temps_ms=None, source="pc", now=None,
          uid=None) -> dict:
    """SM-2 allégé. Idempotent sur `uuid` (rejeu d'une file de sync)."""
    now = time.time() if now is None else now
    uid = uid or str(_uuid.uuid4())
    if db.q1("SELECT id FROM kr_revue WHERE uuid = ?", (uid,)):
        return {"ok": True, "deja": True}

    carte = db.q1("SELECT * FROM kr_carte WHERE id = ?", (carte_id,))
    if not carte:
        return {"ok": False, "deja": False}

    ease = float(carte["ease"] or 2.5)
    reps = int(carte["reps"] or 0)
    lapses = int(carte["lapses"] or 0)

    if su:
        reps += 1
        if reps == 1:
            interval = 1 * DAY
        elif reps == 2:
            interval = 3 * DAY
        else:
            interval = float(carte["interval"] or DAY) * ease
        ease = min(3.0, ease + 0.1)
    else:
        reps = 0
        lapses += 1
        interval = 10 * 60.0          # 10 min : on la revoit vite
        ease = max(1.3, ease - 0.2)

    db.execute(
        "UPDATE kr_carte SET reps = ?, ease = ?, interval = ?, due = ?, "
        "lapses = ? WHERE id = ?",
        (reps, round(ease, 3), interval, now + interval, lapses, carte_id))
    db.execute(
        "INSERT OR IGNORE INTO kr_revue(uuid, carte_id, ts, su, temps_ms, "
        "source) VALUES (?,?,?,?,?,?)",
        (uid, carte_id, int(now), 1 if su else 0, temps_ms, source))

    debloquee = False
    if carte["direction"] == "kr_fr" and reps >= SEUIL_DEBLOCAGE:
        touchees = db.execute_count(
            "UPDATE kr_carte SET suspendu = 0, due = ? WHERE item_id = ? "
            "AND direction = 'fr_kr' AND suspendu = 1", (now, carte["item_id"]))
        debloquee = bool(touchees)
    return {"ok": True, "deja": False, "reps": reps, "interval": interval,
            "debloquee_fr_kr": debloquee}


# --------------------------------------------------------------- édition

def ajouter_item(kr, romaja="", fr="", exemple="", semaine_id=None,
                 type_="vocab", source="libre") -> int:
    kr = (kr or "").strip()
    if not kr:
        return 0
    item_id = db.execute(
        "INSERT INTO kr_item(semaine_id, type, kr, romaja, fr, exemple_kr, "
        "tags, source, ordre) VALUES (?,?,?,?,?,?,?,?,0)",
        (semaine_id, type_, kr, (romaja or "").strip(), (fr or "").strip(),
         (exemple or "").strip(), "vocabulaire libre", source))
    maintenant = time.time()
    db.execute("INSERT OR IGNORE INTO kr_carte(item_id, direction, due, "
               "suspendu) VALUES (?, 'kr_fr', ?, 0)", (item_id, maintenant))
    db.execute("INSERT OR IGNORE INTO kr_carte(item_id, direction, due, "
               "suspendu) VALUES (?, 'fr_kr', ?, 1)", (item_id, maintenant))
    return item_id


def modifier_item(item_id, kr, romaja, fr, exemple):
    db.execute("UPDATE kr_item SET kr = ?, romaja = ?, fr = ?, exemple_kr = ? "
               "WHERE id = ?", (kr, romaja, fr, exemple, item_id))


def supprimer_item(item_id):
    db.execute("DELETE FROM kr_item WHERE id = ?", (item_id,))


# ------------------------------------------------------------- exercices

def exercices_semaine(semaine_id) -> list:
    return db.q("SELECT * FROM kr_exercice WHERE semaine_id = ? ORDER BY id",
                (semaine_id,))


def contenu_exercice(exercice_id):
    """Construit le contenu réel d'un exercice (QCM générés à la volée)."""
    exo = db.q1("SELECT * FROM kr_exercice WHERE id = ?", (exercice_id,))
    if not exo:
        return None
    try:
        contenu = json.loads(exo["contenu_json"] or "{}")
    except ValueError:
        contenu = {}
    if not contenu.get("auto"):
        return {"type": exo["type"], "titre": exo["titre"], **contenu}

    # QCM : on tire les items de la semaine et des leurres pris ailleurs.
    nb_choix = int(contenu.get("qcm", 4))
    cibles = db.q(
        "SELECT id, kr, romaja, fr FROM kr_item WHERE semaine_id = ? "
        "AND type IN ('vocab', 'phrase') ORDER BY RANDOM() LIMIT 10",
        (exo["semaine_id"],))
    questions = []
    for cible in cibles:
        leurres = db.q(
            "SELECT fr, kr FROM kr_item WHERE id <> ? AND fr <> '' "
            "AND type IN ('vocab', 'phrase') ORDER BY RANDOM() LIMIT ?",
            (cible["id"], nb_choix - 1))
        if exo["type"] == "prod":
            bonne, autres = cible["kr"], [x["kr"] for x in leurres]
            enonce = cible["fr"]
        else:
            bonne, autres = cible["fr"], [x["fr"] for x in leurres]
            enonce = cible["kr"]
        questions.append({"item_id": cible["id"], "enonce": enonce,
                          "romaja": cible["romaja"], "bonne": bonne,
                          "choix": [bonne] + autres})
    return {"type": exo["type"], "titre": exo["titre"],
            "lang": contenu.get("lang"), "questions": questions}


# ------------------------------------------------------------ statistiques

def stats() -> dict:
    now = time.time()
    return {
        "items": int(db.scalar("SELECT COUNT(*) FROM kr_item", default=0)),
        "cartes": int(db.scalar("SELECT COUNT(*) FROM kr_carte", default=0)),
        "actives": int(db.scalar("SELECT COUNT(*) FROM kr_carte "
                                 "WHERE suspendu = 0", default=0)),
        "apprises": int(db.scalar("SELECT COUNT(*) FROM kr_carte "
                                  "WHERE reps > 0", default=0)),
        "matures": int(db.scalar("SELECT COUNT(*) FROM kr_carte "
                                 "WHERE interval >= ?", (21 * DAY,), default=0)),
        "dues": nb_dues(now),
    }


# --------------------------------------------------------- import / export

def export_json() -> str:
    return json.dumps(
        [{"kr": i["kr"], "romaja": i["romaja"], "fr": i["fr"],
          "example": i["exemple_kr"], "semaine": i["semaine_numero"],
          "type": i["type"]} for i in items()],
        ensure_ascii=False, indent="\t")


def export_csv() -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(FIELDS)
    for i in items():
        w.writerow([i["kr"], i["romaja"], i["fr"], i["exemple_kr"]])
    return buf.getvalue()


def import_json(texte: str, replace=False) -> int:
    data = json.loads(texte)
    if replace:
        db.execute("DELETE FROM kr_item WHERE source IN ('libre', 'legacy')")
    n = 0
    for item in data:
        if not isinstance(item, dict) or not item.get("kr"):
            continue
        ajouter_item(item.get("kr", ""), item.get("romaja", ""),
                     item.get("fr", ""), item.get("example", ""))
        n += 1
    return n


def import_csv(texte: str, replace=False) -> int:
    rows = list(csv.reader(io.StringIO(texte)))
    if rows and [h.strip().lower() for h in rows[0]][:1] == ["kr"]:
        rows = rows[1:]
    if replace:
        db.execute("DELETE FROM kr_item WHERE source IN ('libre', 'legacy')")
    n = 0
    for row in rows:
        if not row or not row[0].strip():
            continue
        row = (list(row) + ["", "", "", ""])[:4]
        ajouter_item(*[x.strip() for x in row])
        n += 1
    return n


# ------------------------------------------------- façade rétro-compatible

class Deck:
    """Ancienne interface (`app.deck`), servie par SQLite.

    `cards()` renvoie des dicts au format historique — l'onglet Coréen d'origine
    et tout code existant continuent de tourner.
    """

    def __init__(self, config=None):
        self.config = config

    def cards(self) -> list:
        rows = db.q(
            "SELECT c.id AS carte_id, c.due, c.interval, c.ease, c.reps, "
            "       i.kr, i.romaja, i.fr, i.exemple_kr "
            "FROM kr_carte c JOIN kr_item i ON i.id = c.item_id "
            "WHERE c.direction = 'kr_fr' ORDER BY i.id")
        return [{"carte_id": r["carte_id"], "kr": r["kr"],
                 "romaja": r["romaja"], "fr": r["fr"],
                 "example": r["exemple_kr"], "due": r["due"],
                 "interval": r["interval"], "ease": r["ease"],
                 "reps": r["reps"], "history": []} for r in rows]

    def words_per_session(self) -> int:
        if self.config is None:
            return 3
        return int(self.config.get("korean.words_per_session", 3))

    def due_cards(self, limit=None, now=None) -> list:
        limit = self.words_per_session() if limit is None else limit
        return [{"carte_id": c["id"], "kr": c["kr"], "romaja": c["romaja"],
                 "fr": c["fr"], "example": c["exemple_kr"], "due": c["due"],
                 "interval": c["interval"], "ease": c["ease"],
                 "reps": c["reps"], "history": []}
                for c in cartes_dues(limit, now, direction="kr_fr")]

    def grade(self, card, knew: bool, now=None):
        carte_id = card.get("carte_id")
        if carte_id is None:
            row = db.q1(
                "SELECT c.id FROM kr_carte c JOIN kr_item i ON i.id = c.item_id "
                "WHERE i.kr = ? AND c.direction = 'kr_fr' LIMIT 1",
                (card.get("kr"),))
            carte_id = (row or {}).get("id")
        if carte_id is not None:
            noter(carte_id, knew, now=now)

    def add(self, kr, romaja="", fr="", example=""):
        ajouter_item(kr, romaja, fr, example)

    def update(self, index, kr, romaja, fr, example):
        cartes = self.cards()
        if 0 <= index < len(cartes):
            carte = db.q1("SELECT item_id FROM kr_carte WHERE id = ?",
                          (cartes[index]["carte_id"],))
            if carte:
                modifier_item(carte["item_id"], kr, romaja, fr, example)

    def remove(self, index):
        cartes = self.cards()
        if 0 <= index < len(cartes):
            carte = db.q1("SELECT item_id FROM kr_carte WHERE id = ?",
                          (cartes[index]["carte_id"],))
            if carte:
                supprimer_item(carte["item_id"])

    export_json = staticmethod(export_json)
    export_csv = staticmethod(export_csv)

    def import_json(self, texte, replace=False):
        import_json(texte, replace=replace)

    def import_csv(self, texte, replace=False):
        import_csv(texte, replace=replace)
