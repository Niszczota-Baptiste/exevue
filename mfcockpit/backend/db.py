"""Base SQLite du cockpit — `cockpit.db`, posé à côté de l'exe (portable).

Une seule connexion partagée (`check_same_thread=False`) protégée par un
`RLock` : l'UI *et* le thread du serveur HTTP écrivent tous les deux. WAL activé
pour que lecture et écriture ne se bloquent pas. Les migrations sont
**versionnées et idempotentes** : `migrate()` peut être rejoué autant de fois
qu'on veut, il n'applique que les étapes manquantes.

Aucune dépendance : `sqlite3` est dans la stdlib.
"""
import contextlib
import csv
import io
import os
import sqlite3
import threading
import time

from . import paths

_lock = threading.RLock()
_conn = None
_db_path = None

# ---------------------------------------------------------------- schéma v1

_SCHEMA_V1 = """
-- ============ RÉFÉRENTIEL SPORT ============
CREATE TABLE IF NOT EXISTS exercice (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    code              TEXT UNIQUE NOT NULL,
    nom               TEXT NOT NULL,
    categorie         TEXT,            -- force|plyo|core|prehab|mobilite|cardio
    lieu              TEXT,            -- maison|salle|partout
    equipement        TEXT,            -- kettlebell|unica|tapis|velo|poids_du_corps
    groupe            TEXT,            -- pectoraux|dos|…|abdos|tout
    unite             TEXT,            -- reps|secondes|metres|contacts
    chargeable        INTEGER DEFAULT 0,
    consignes         TEXT,
    erreurs_frequentes TEXT,
    media_path        TEXT,
    video_url         TEXT,
    variantes_json    TEXT,            -- échelle de progression, facile -> dur
    actif             INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS programme (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nom         TEXT NOT NULL,
    actif       INTEGER DEFAULT 0,
    date_debut  TEXT,
    note        TEXT
);

CREATE TABLE IF NOT EXISTS seance_modele (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    programme_id    INTEGER REFERENCES programme(id) ON DELETE CASCADE,
    jour_semaine    INTEGER,          -- 1=lundi … 7=dimanche, 0 = rotation quotidienne
    nom             TEXT NOT NULL,
    lieu            TEXT,
    type            TEXT,             -- force|core|cardio|prehab|mixte
    duree_cible_min INTEGER,
    ordre_affichage INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS seance_modele_exo (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    seance_modele_id INTEGER REFERENCES seance_modele(id) ON DELETE CASCADE,
    exercice_id      INTEGER REFERENCES exercice(id),
    ordre            INTEGER DEFAULT 1,
    bloc             TEXT,            -- echauffement|explosif|principal|finisher
    series_cible     INTEGER,
    reps_min         INTEGER,
    reps_max         INTEGER,
    repos_sec        INTEGER,
    tempo            TEXT,
    charge_depart    REAL,
    superset_group   TEXT,
    note             TEXT
);

-- ============ JOURNAL SPORT ============
CREATE TABLE IF NOT EXISTS seance (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid             TEXT UNIQUE,
    seance_modele_id INTEGER REFERENCES seance_modele(id),
    date             TEXT NOT NULL,   -- YYYY-MM-DD (journée « 4 h du matin »)
    statut           TEXT,            -- planifie|en_cours|fait|partiel|manque
    debut_ts         INTEGER,
    fin_ts           INTEGER,
    duree_s          INTEGER,
    rpe              INTEGER,
    humeur           INTEGER,
    douleur_genou    INTEGER,
    douleur_hanche   INTEGER,
    note             TEXT,
    source           TEXT DEFAULT 'pc'
);

CREATE TABLE IF NOT EXISTS serie (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid         TEXT UNIQUE,
    seance_id    INTEGER REFERENCES seance(id) ON DELETE CASCADE,
    exercice_id  INTEGER REFERENCES exercice(id),
    index_serie  INTEGER,
    reps         INTEGER,
    charge_kg    REAL,
    duree_s      INTEGER,
    tempo        TEXT,
    rpe          INTEGER,
    repos_reel_s INTEGER,
    variante     TEXT,
    echec        INTEGER DEFAULT 0,
    note         TEXT,
    ts           INTEGER,
    source       TEXT DEFAULT 'pc'
);

CREATE TABLE IF NOT EXISTS record (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    exercice_id INTEGER REFERENCES exercice(id),
    type        TEXT,     -- charge_max|reps_max|volume_seance|1rm_estime
    valeur      REAL,
    unite       TEXT,
    date        TEXT,
    serie_id    INTEGER REFERENCES serie(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS cardio (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid         TEXT UNIQUE,
    date         TEXT,
    type         TEXT,     -- course|velo|tapis|foot_salle
    distance_km  REAL,
    duree_s      INTEGER,
    allure_s_km  REAL,
    fc_moy       INTEGER,
    ressenti     INTEGER,
    note         TEXT,
    source       TEXT DEFAULT 'pc'
);

CREATE TABLE IF NOT EXISTS mesure (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT UNIQUE,
    poids_kg    REAL,
    tour_taille REAL,
    tour_bras   REAL,
    tour_cuisse REAL,
    note        TEXT
);

-- ============ CORÉEN ============
CREATE TABLE IF NOT EXISTS kr_semaine (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    numero         INTEGER UNIQUE,
    theme          TEXT,
    date_debut     TEXT,
    date_fin       TEXT,
    objectifs_json TEXT,
    note_culture   TEXT
);

CREATE TABLE IF NOT EXISTS kr_item (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    semaine_id INTEGER REFERENCES kr_semaine(id) ON DELETE SET NULL,
    type       TEXT,       -- vocab|structure|phrase|dialogue
    kr         TEXT NOT NULL,
    romaja     TEXT,
    fr         TEXT,
    exemple_kr TEXT,
    exemple_fr TEXT,
    tags       TEXT,
    source     TEXT,
    ordre      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS kr_carte (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id   INTEGER REFERENCES kr_item(id) ON DELETE CASCADE,
    direction TEXT,        -- kr_fr|fr_kr
    due       REAL,
    interval  REAL DEFAULT 0,
    ease      REAL DEFAULT 2.5,
    reps      INTEGER DEFAULT 0,
    lapses    INTEGER DEFAULT 0,
    suspendu  INTEGER DEFAULT 0,
    UNIQUE (item_id, direction)
);

CREATE TABLE IF NOT EXISTS kr_revue (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid     TEXT UNIQUE,
    carte_id INTEGER REFERENCES kr_carte(id) ON DELETE CASCADE,
    ts       INTEGER,
    su       INTEGER,
    temps_ms INTEGER,
    source   TEXT DEFAULT 'pc'
);

CREATE TABLE IF NOT EXISTS kr_exercice (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    semaine_id      INTEGER REFERENCES kr_semaine(id) ON DELETE CASCADE,
    type            TEXT,   -- reco|prod|trous|roleplay|ecoute
    titre           TEXT,
    contenu_json    TEXT,
    duree_cible_min INTEGER
);

CREATE TABLE IF NOT EXISTS kr_seance (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid           TEXT UNIQUE,
    date           TEXT,
    statut         TEXT,
    duree_s        INTEGER,
    checklist_json TEXT,
    cartes_vues    INTEGER DEFAULT 0,
    cartes_sues    INTEGER DEFAULT 0,
    note           TEXT,
    source         TEXT DEFAULT 'pc'
);

-- ============ TRANSVERSE ============
CREATE TABLE IF NOT EXISTS tache_jour (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    date     TEXT NOT NULL,
    domaine  TEXT NOT NULL,   -- sport|core|coreen|cardio|prehab
    ref_type TEXT,
    ref_id   INTEGER,
    libelle  TEXT,
    ordre    INTEGER DEFAULT 0,
    fait     INTEGER DEFAULT 0,
    fait_ts  INTEGER,
    source   TEXT DEFAULT 'pc',
    UNIQUE (date, domaine, ref_type, ref_id)
);

CREATE TABLE IF NOT EXISTS streak (
    domaine             TEXT PRIMARY KEY,
    courant             INTEGER DEFAULT 0,
    record              INTEGER DEFAULT 0,
    dernier_jour_valide TEXT
);

CREATE TABLE IF NOT EXISTS rappel (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    date    TEXT,
    ts      INTEGER,
    domaine TEXT,
    envoye  INTEGER DEFAULT 0,
    ouvert  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sync_op (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid         TEXT UNIQUE,
    table_cible  TEXT,
    payload_json TEXT,
    ts           INTEGER,
    applique     INTEGER DEFAULT 0,
    device       TEXT
);

CREATE TABLE IF NOT EXISTS reglage (
    cle    TEXT PRIMARY KEY,
    valeur TEXT
);

-- ============ INDEX ============
CREATE INDEX IF NOT EXISTS idx_seance_date       ON seance(date);
CREATE INDEX IF NOT EXISTS idx_serie_seance      ON serie(seance_id);
CREATE INDEX IF NOT EXISTS idx_serie_exo         ON serie(exercice_id, ts);
CREATE UNIQUE INDEX IF NOT EXISTS idx_serie_slot ON serie(seance_id, exercice_id, index_serie);
CREATE INDEX IF NOT EXISTS idx_tache_date        ON tache_jour(date);
CREATE INDEX IF NOT EXISTS idx_kr_carte_due      ON kr_carte(due, suspendu);
CREATE INDEX IF NOT EXISTS idx_kr_revue_ts       ON kr_revue(ts);
CREATE INDEX IF NOT EXISTS idx_kr_item_semaine   ON kr_item(semaine_id, ordre);
CREATE INDEX IF NOT EXISTS idx_smexo_modele      ON seance_modele_exo(seance_modele_id, ordre);
CREATE INDEX IF NOT EXISTS idx_cardio_date       ON cardio(date);
CREATE INDEX IF NOT EXISTS idx_record_exo        ON record(exercice_id, type);
"""


# ------------------------------------------------------------- connexion

def db_path() -> str:
    return _db_path if _db_path is not None else paths.DB_FILE


def set_path(path: str):
    """Redirige la base (tests). Ferme la connexion en cours."""
    global _db_path
    close()
    _db_path = path


def conn() -> sqlite3.Connection:
    """Connexion partagée, ouverte à la demande."""
    global _conn
    with _lock:
        if _conn is None:
            target = db_path()
            folder = os.path.dirname(target)
            if folder and not os.path.isdir(folder):
                try:
                    os.makedirs(folder, exist_ok=True)
                except Exception:
                    pass
            c = sqlite3.connect(target, check_same_thread=False, timeout=10.0)
            c.row_factory = sqlite3.Row
            try:
                c.execute("PRAGMA journal_mode=WAL")
            except Exception:
                pass  # système de fichiers sans WAL (réseau) : on continue
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA synchronous=NORMAL")
            _conn = c
        return _conn


def close():
    global _conn
    with _lock:
        if _conn is not None:
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None


# ------------------------------------------------------------- helpers

@contextlib.contextmanager
def tx():
    """Transaction : commit à la sortie, rollback si ça casse."""
    c = conn()
    with _lock:
        try:
            yield c
            c.commit()
        except Exception:
            try:
                c.rollback()
            except Exception:
                pass
            raise


def q(sql: str, params=()) -> list:
    """SELECT -> liste de dicts."""
    with _lock:
        cur = conn().execute(sql, params)
        rows = cur.fetchall()
        cur.close()
    return [dict(r) for r in rows]


def q1(sql: str, params=()):
    """SELECT -> premier dict ou None."""
    rows = q(sql, params)
    return rows[0] if rows else None


def scalar(sql: str, params=(), default=None):
    """SELECT d'une seule valeur."""
    with _lock:
        cur = conn().execute(sql, params)
        row = cur.fetchone()
        cur.close()
    if row is None or row[0] is None:
        return default
    return row[0]


def execute(sql: str, params=()) -> int:
    """INSERT/UPDATE/DELETE -> lastrowid. Commit immédiat."""
    with _lock:
        c = conn()
        cur = c.execute(sql, params)
        c.commit()
        rid = cur.lastrowid
        cur.close()
    return rid


def execute_count(sql: str, params=()) -> int:
    """UPDATE/DELETE -> nombre de lignes touchées."""
    with _lock:
        c = conn()
        cur = c.execute(sql, params)
        c.commit()
        n = cur.rowcount
        cur.close()
    return n


def executemany(sql: str, seq) -> None:
    with _lock:
        c = conn()
        c.executemany(sql, seq)
        c.commit()


# ------------------------------------------------------------- réglages

def reglage(cle: str, defaut=None):
    row = q1("SELECT valeur FROM reglage WHERE cle = ?", (cle,))
    return row["valeur"] if row else defaut


def set_reglage(cle: str, valeur):
    execute("INSERT INTO reglage(cle, valeur) VALUES (?, ?) "
            "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur",
            (cle, "" if valeur is None else str(valeur)))


def reglage_int(cle: str, defaut: int) -> int:
    try:
        return int(reglage(cle, defaut))
    except (TypeError, ValueError):
        return defaut


def reglage_bool(cle: str, defaut: bool) -> bool:
    val = reglage(cle, None)
    if val is None:
        return defaut
    return str(val).strip().lower() in ("1", "true", "oui", "yes", "on")


# ------------------------------------------------------------- migrations

def _version() -> int:
    try:
        return int(scalar("SELECT MAX(version) FROM schema_version", default=0) or 0)
    except sqlite3.Error:
        return 0


def _mark(version: int):
    execute("INSERT OR IGNORE INTO schema_version(version, applique_ts) "
            "VALUES (?, ?)", (version, int(time.time())))


def _m1_schema(c):
    c.executescript(_SCHEMA_V1)


def _m2_seed_sport(c):
    from . import seed_sport
    seed_sport.seed(c)


def _m3_seed_coreen(c):
    from . import seed_coreen
    seed_coreen.seed(c)


def _m4_defaults(c):
    defaults = {
        "ui.onglet_demarrage": "aujourdhui",
        "mobile.port": "8790",
        "rappels.actif": "1",
        "rappels.intervalle_h": "2",
        "rappels.debut_h": "9",
        "rappels.fin_h": "22",
        "rappels.sport": "1",
        "rappels.coreen": "1",
        "coreen.saisie_libre": "0",
        "sport.pas_charge_kg": "2.5",
    }
    for cle, valeur in defaults.items():
        c.execute("INSERT OR IGNORE INTO reglage(cle, valeur) VALUES (?, ?)",
                  (cle, valeur))


def _m5_programme_v2(c):
    from . import seed_sport_v2
    seed_sport_v2.seed(c)


def _m6_lieux_imposes(c):
    from . import seed_sport_v2
    seed_sport_v2.resynchroniser(c)


# (version, libellé, fonction) — appliquées dans l'ordre, une seule fois.
MIGRATIONS = [
    (1, "schéma initial", _m1_schema),
    (2, "seed programme sport", _m2_seed_sport),
    (3, "seed programme coréen", _m3_seed_coreen),
    (4, "réglages par défaut", _m4_defaults),
    (5, "programme v2 : bras/abdos/dos, bloc abdos du soir", _m5_programme_v2),
    (6, "lieux imposés : maison lundi/jeudi, salle mardi/vendredi",
     _m6_lieux_imposes),
]


def migrate(config=None) -> int:
    """Applique les migrations manquantes. Idempotent : rejouable à volonté.

    Renvoie la version finale du schéma.
    """
    with _lock:
        c = conn()
        c.executescript(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "  version INTEGER PRIMARY KEY, applique_ts INTEGER);")
        c.commit()
        current = _version()
        for version, _label, fn in MIGRATIONS:
            if version <= current:
                continue
            with tx() as cx:
                fn(cx)
            _mark(version)
        final = _version()

    if config is not None:
        migrer_deck_legacy(config)
    return final


# ------------------------------------------------- migration deck legacy

def migrer_deck_legacy(config) -> int:
    """Importe `config.json → korean.deck` dans les tables coréen (une fois).

    Les cartes deviennent des items « vocabulaire libre » (`source='legacy'`)
    et **gardent leurs échéances SRS**. La clé JSON reste en place (backup) mais
    plus rien ne l'écrit ensuite. Renvoie le nombre d'items importés.
    """
    if reglage("migration.deck_legacy") == "1":
        return 0
    try:
        deck = config.get("korean.deck", []) or []
    except Exception:
        deck = []

    importes = 0
    with tx() as c:
        for card in deck:
            if not isinstance(card, dict):
                continue
            kr = (card.get("kr") or "").strip()
            if not kr:
                continue
            row = c.execute(
                "SELECT id FROM kr_item WHERE kr = ? AND source = 'legacy'",
                (kr,)).fetchone()
            if row:
                continue
            cur = c.execute(
                "INSERT INTO kr_item(semaine_id, type, kr, romaja, fr, "
                "exemple_kr, tags, source, ordre) "
                "VALUES (NULL, 'vocab', ?, ?, ?, ?, 'vocabulaire libre', "
                "'legacy', 0)",
                (kr, card.get("romaja", ""), card.get("fr", ""),
                 card.get("example", "")))
            item_id = cur.lastrowid
            # Échéances conservées telles quelles sur la carte KR->FR.
            c.execute(
                "INSERT OR IGNORE INTO kr_carte(item_id, direction, due, "
                "interval, ease, reps, lapses, suspendu) "
                "VALUES (?, 'kr_fr', ?, ?, ?, ?, 0, 0)",
                (item_id, float(card.get("due") or time.time()),
                 float(card.get("interval") or 0.0),
                 float(card.get("ease") or 2.5), int(card.get("reps") or 0)))
            # La direction inverse se débloque après 3 réussites (règle commune).
            reps = int(card.get("reps") or 0)
            c.execute(
                "INSERT OR IGNORE INTO kr_carte(item_id, direction, due, "
                "interval, ease, reps, lapses, suspendu) "
                "VALUES (?, 'fr_kr', ?, 0, 2.5, 0, 0, ?)",
                (item_id, time.time(), 0 if reps >= 3 else 1))
            # Historique -> kr_revue (traçabilité des stats).
            carte = c.execute(
                "SELECT id FROM kr_carte WHERE item_id = ? AND direction = 'kr_fr'",
                (item_id,)).fetchone()
            if carte:
                for h in (card.get("history") or [])[-50:]:
                    if not isinstance(h, dict):
                        continue
                    c.execute(
                        "INSERT INTO kr_revue(uuid, carte_id, ts, su, source) "
                        "VALUES (?, ?, ?, ?, 'legacy')",
                        (f"legacy-{carte['id']}-{h.get('t', 0)}", carte["id"],
                         int(h.get("t") or 0), 1 if h.get("knew") else 0))
            importes += 1
    set_reglage("migration.deck_legacy", "1")
    return importes


# ------------------------------------------------------------- export CSV

TABLES_EXPORT = [
    "exercice", "programme", "seance_modele", "seance_modele_exo",
    "seance", "serie", "record", "cardio", "mesure",
    "kr_semaine", "kr_item", "kr_carte", "kr_revue", "kr_exercice", "kr_seance",
    "tache_jour", "streak", "rappel", "sync_op", "reglage",
]


def export_csv(table: str) -> str:
    """Dump CSV d'une table (en-tête + lignes). Table blanchie par liste."""
    if table not in TABLES_EXPORT:
        raise ValueError(f"table inconnue : {table}")
    rows = q(f"SELECT * FROM {table}")
    buf = io.StringIO()
    if not rows:
        cols = [r["name"] for r in q(f"PRAGMA table_info({table})")]
        csv.writer(buf).writerow(cols)
        return buf.getvalue()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()
