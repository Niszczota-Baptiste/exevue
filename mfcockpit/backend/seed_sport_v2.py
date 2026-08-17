# -*- coding: utf-8 -*-
"""Programme v2 — « Haut du corps & abdos ».

Recentrage demandé après la première semaine d'usage : la priorité va aux
**bras, aux abdos et au dos**. Les jambes restent au programme, mais elles
servent le foot et le basket (explosivité, amorti, mollets) plutôt que la prise
de masse — une seule séance dédiée, plyométrie en tête tant qu'on est frais.

Semaine type. Les **lieux sont imposés** : maison le lundi et le jeudi, salle
le mardi et le vendredi. Le reste est flexible, donc calé sur le confort.

| Jour     | Séance                              | Lieu   | Durée  |
|----------|-------------------------------------|--------|--------|
| Lundi    | Pecs, épaules & triceps             | Maison | 45 min |
| Mardi    | Dos & biceps                        | Salle  | 50 min |
| Mercredi | Mobilité & prehab genou/hanche      | Maison | 15 min |
| Jeudi    | Bras (volume) & dos                 | Maison | 45 min |
| Vendredi | Jambes & explosivité                | Salle  | 50 min |
| Samedi   | Course 5 km + Full abdos            | Ext./Maison | 30+30 |
| Dimanche | Mobilité & prehab genou/hanche      | Maison | 15 min |

Le placement suit l'équipement, pas l'inverse : les deux séances qui ont
réellement besoin des machines — le tirage/poulies du dos et la presse à
cuisses — tombent les jours de salle. Le lundi et le jeudi n'utilisent que la
kettlebell, une chaise et une table.

Plus, **tous les soirs sauf samedi**, un bloc de 15 min d'abdos (rotation
A/B/C) — que des abdos, plus de gainage anti-rotation déguisé.

L'ancien programme n'est pas supprimé : il est simplement désactivé, pour que
les séances déjà enregistrées gardent leur modèle et restent lisibles dans les
statistiques.
"""
import json

from .seed_sport import PAR_BRAS, PAR_COTE, PAR_JAMBE, _e

PROGRAMME_NOM = "Haut du corps & abdos"
PROGRAMME_NOTE = (
    "Priorité bras, abdos et dos. Les jambes servent le foot et le basket : "
    "explosivité et amorti, pas du volume pour du volume. Genou droit et "
    "hanche droite toujours sous surveillance."
)

# ------------------------------------------------- exercices supplémentaires
# Même format que `seed_sport.EXERCICES` (semés avec INSERT OR IGNORE).
EXERCICES = [
    # ---- bras ----
    ("curl_concentre", "Curl concentré KB", "force", "partout", "kettlebell",
     "bras", "reps", 1,
     "Assis, coude calé contre l'intérieur de la cuisse. Le bras ne bouge "
     "pas, seul l'avant-bras monte. Pause 1 s en haut, descente lente.",
     "Décoller le coude de la cuisse · balancer le buste.", None),
    ("kickback_triceps", "Kickback triceps KB", "force", "partout",
     "kettlebell", "bras", "reps", 1,
     "Buste penché, bras collé au corps, coude fixe : on tend l'avant-bras "
     "vers l'arrière et on serre le triceps 1 s.",
     "Coude qui descend · mouvement lancé à l'élan.", None),
    ("dips_chaise", "Dips sur chaise", "force", "partout", "poids_du_corps",
     "bras", "reps", 0,
     "Mains sur le bord d'une chaise, descends jusqu'à ~90° au coude, "
     "épaules basses. Jambes tendues pour durcir, pliées pour alléger.",
     "Descendre trop bas (épaule) · épaules qui remontent aux oreilles.",
     ["Jambes pliées", "Jambes tendues", "Pieds surélevés",
      "Lesté (sac à dos)"]),
    ("curl_inverse", "Curl inversé (prise pronation)", "force", "partout",
     "kettlebell", "bras", "reps", 1,
     "Paumes vers le bas. Charge plus légère que le curl classique, c'est "
     "normal : ça travaille l'avant-bras et le brachial.",
     "Prendre trop lourd et compenser avec les poignets.", None),
    # ---- dos ----
    ("pull_over_kb", "Pull-over KB", "force", "partout", "kettlebell", "dos",
     "reps", 1,
     "Allongé, KB tenue à deux mains au-dessus de la poitrine. Descends "
     "derrière la tête bras quasi tendus, côtes basses, puis reviens.",
     "Cambrer pour aller plus loin · plier les coudes.", None),
    ("shrug_kb", "Haussements d'épaules KB", "force", "partout", "kettlebell",
     "dos", "reps", 1,
     "Monte les épaules vers les oreilles, pause 1 s, descends lentement. "
     "Aucune rotation, c'est une ligne droite.",
     "Rouler les épaules · plier les bras.", None),
    ("rowing_australien", "Rowing australien (sous une table)", "force",
     "maison", "poids_du_corps", "dos", "reps", 0,
     "Allongé sous une table solide, mains sur le bord, corps gainé en "
     "planche : tu tires la poitrine vers la table. Plus les pieds sont "
     "loin, plus c'est dur. C'est le seul vrai tirage disponible à la "
     "maison — vérifie que la table ne bascule pas avant de t'y suspendre.",
     "Bassin qui s'affaisse · amplitude coupée en haut.",
     ["Genoux pliés", "Jambes tendues", "Pieds surélevés"]),
    ("superman", "Superman (extensions lombaires)", "force", "partout",
     "tapis", "dos", "reps", 0,
     "À plat ventre, on décolle bras et jambes de quelques centimètres, "
     "pause 1 s, on repose. Le regard reste au sol, la nuque dans l'axe.",
     "Casser la nuque en arrière · monter en force et rebondir.", None),
    # ---- abdos ----
    ("crunch", "Crunch", "core", "partout", "tapis", "abdos", "reps", 0,
     "On décolle les omoplates, pas plus. Le bas du dos reste au sol, "
     "expire en montant.",
     "Tirer sur la nuque · monter tout le buste (c'est du psoas).", None),
    ("crunch_oblique", "Crunch oblique", "core", "partout", "tapis", "abdos",
     "reps", 0,
     "Même chose que le crunch, mais l'épaule va vers le genou opposé. "
     "Mouvement court et contrôlé.",
     "Tirer sur la nuque · aller vite.", None),
    ("bicycle_crunch", "Crunch vélo", "core", "partout", "tapis", "abdos",
     "reps", 0,
     "Coude vers le genou opposé en alternance, jambe libre tendue près du "
     "sol. Lent : c'est la rotation qui compte, pas la vitesse.",
     "Pédaler vite sans rotation réelle · dos décollé.", None),
    ("hollow_rock", "Hollow rock", "core", "partout", "tapis", "abdos",
     "reps", 0,
     "Position hollow (dos plaqué), on se balance d'un bloc comme une "
     "banane rigide. Si le dos se creuse, reviens au hollow hold statique.",
     "Se plier au milieu · creux lombaire.", None),
    ("v_ups", "V-ups", "core", "partout", "tapis", "abdos", "reps", 0,
     "Bras et jambes montent en même temps pour se rejoindre au-dessus du "
     "bassin. Version genoux pliés si le dos décolle.",
     "Utiliser l'élan · bas du dos qui claque au sol.",
     ["Genoux pliés", "Une jambe", "Complet", "Lesté"]),
    ("side_bend_kb", "Flexion latérale KB", "core", "partout", "kettlebell",
     "abdos", "reps", 1,
     "Debout, KB d'un seul côté, on s'incline sur le côté chargé puis on "
     "remonte par les obliques opposés. Buste dans le plan, sans rotation.",
     "Se pencher en avant · charge trop lourde qui tire le dos.", None),
    ("mountain_climber", "Mountain climbers", "core", "partout",
     "poids_du_corps", "abdos", "secondes", 0,
     "En position de planche haute, on ramène les genoux en alternance. "
     "Le bassin ne monte pas et ne descend pas.",
     "Fesses en l'air · rebondir sur les pieds.", None),
]

# ------------------------------------------------------------ séances type
SEANCES = [
    # ---------------------------------------------------------- lundi
    {
        "jour": 1, "nom": "Pecs, épaules & triceps", "lieu": "maison",
        "type": "force", "duree": 45, "ordre": 1,
        "exos": [
            _e("rotations_epaules", "echauffement", 2, 15, repos=20),
            _e("pompes", "principal", 4, 8, 15, repos=90, tempo="3-1-1",
               note="Variante selon le palier atteint"),
            _e("dev_militaire_kb", "principal", 4, 8, 12, repos=90,
               tempo="2-0-1", charge=24, note="2 × KB de 12"),
            _e("floor_press_kb", "principal", 3, 10, 15, repos=75,
               tempo="3-1-1", charge=24),
            _e("elevations_lat_kb", "principal", 3, 12, 15, repos=45,
               tempo="2-1-2", charge=12),
            _e("ext_triceps_tete_kb", "principal", 3, 10, 15, repos=30,
               tempo="3-1-1", charge=12, superset="B"),
            _e("dips_chaise", "principal", 3, 8, 15, repos=60, superset="B"),
            _e("kickback_triceps", "finisher", 3, 12, 15, repos=45, charge=12,
               note=PAR_BRAS),
        ],
    },
    # ---------------------------------------------------------- mardi
    {
        "jour": 2, "nom": "Dos & biceps", "lieu": "salle", "type": "force",
        "duree": 50, "ordre": 1,
        "exos": [
            _e("velo", "echauffement", 1, 300, repos=0, note="Allure facile"),
            _e("rotations_epaules", "echauffement", 2, 15, repos=20),
            _e("tirage_vertical", "principal", 4, 8, 12, repos=120),
            _e("rowing_poulie_basse", "principal", 4, 10, 12, repos=90),
            _e("pull_over_kb", "principal", 3, 12, 15, repos=75, charge=12),
            _e("curl_poulie_basse", "principal", 4, 10, 12, repos=30,
               superset="A"),
            _e("curl_marteau_kb", "principal", 3, 10, 15, repos=60,
               superset="A", charge=24),
            _e("curl_concentre", "principal", 3, 12, 15, repos=45, charge=12,
               note=PAR_BRAS),
            _e("face_pull", "finisher", 3, 15, repos=45,
               note="Santé d'épaule"),
            _e("shrug_kb", "finisher", 3, 12, 15, repos=45, charge=24),
        ],
    },
    # ---------------------------------------------------------- mercredi
    {
        "jour": 3, "nom": "Mobilité & prehab genou/hanche", "lieu": "maison",
        "type": "prehab", "duree": 15, "ordre": 1,
        "exos": [
            _e("copenhagen", "principal", 3, 20, repos=30, note=PAR_COTE),
            _e("abduction_couche", "principal", 3, 15, repos=30,
               note=PAR_COTE + " — lente"),
            _e("clamshell", "principal", 3, 15, repos=30, note=PAR_COTE),
            _e("step_down_excentrique", "principal", 3, 8, repos=45,
               note="Descente en 3 s — " + PAR_JAMBE),
            _e("wall_sit", "principal", 3, 30, 45, repos=45),
            _e("tibialis_raise", "principal", 3, 20, repos=30),
            _e("soleus_raise", "principal", 3, 20, repos=30, charge=12,
               note=PAR_JAMBE),
            _e("etirement_flechisseurs", "finisher", 2, 40, repos=10,
               note=PAR_COTE),
            _e("etirement_pigeon", "finisher", 2, 40, repos=10, note=PAR_COTE),
            _e("etirement_mollet_mur", "finisher", 2, 40, repos=10,
               note=PAR_COTE),
        ],
    },
    # ---------------------------------------------------------- jeudi
    {
        "jour": 4, "nom": "Bras (volume) & dos", "lieu": "maison",
        "type": "force", "duree": 45, "ordre": 1,
        # Version maison : les poulies partent au mardi (jour de salle), le
        # tirage est repris par le rowing australien sous la table.
        "exos": [
            _e("rotations_epaules", "echauffement", 2, 15, repos=20),
            _e("rowing_australien", "principal", 4, 8, 12, repos=90,
               tempo="2-1-2", note="Recule les pieds quand 12 reps passent"),
            _e("rowing_kb_uni", "principal", 4, 10, 12, repos=75,
               tempo="2-1-2", charge=12, note=PAR_BRAS),
            _e("pull_over_kb", "principal", 3, 12, 15, repos=75, charge=12),
            _e("curl_marteau_kb", "principal", 4, 10, 12, repos=30,
               superset="C", charge=24),
            _e("ext_triceps_tete_kb", "principal", 4, 10, 15, repos=60,
               superset="C", charge=12),
            _e("curl_inverse", "principal", 3, 12, 15, repos=45, charge=12),
            _e("dips_chaise", "principal", 3, 8, 15, repos=60),
            _e("superman", "finisher", 3, 15, repos=30),
            _e("suitcase_carry", "finisher", 3, 40, repos=45, charge=12,
               note=PAR_COTE),
        ],
    },
    # ---------------------------------------------------------- vendredi
    {
        "jour": 5, "nom": "Jambes & explosivité", "lieu": "salle",
        "type": "mixte", "duree": 50, "ordre": 1,
        "exos": [
            _e("velo", "echauffement", 1, 300, repos=0, note="Allure facile"),
            _e("mob_cheville_mur", "echauffement", 2, 10, repos=30,
               note=PAR_COTE),
            _e("pont_fessier", "echauffement", 2, 15, repos=30),
            # Plyo en tête de séance : détente basket et appuis foot, jamais
            # sur des jambes déjà cuites.
            _e("pogo_hops", "explosif", 3, 15, repos=45),
            _e("squat_jump", "explosif", 4, 5, repos=90,
               note="Atterrissage silencieux, 3 s de reset entre chaque"),
            _e("broad_jump", "explosif", 3, 3, repos=90,
               note="À partir de la semaine 3"),
            _e("presse_cuisses", "principal", 4, 8, 12, repos=150),
            _e("leg_curl", "principal", 4, 10, 15, repos=90,
               note="Ischios prioritaires : genou + sprint"),
            _e("leg_extension", "principal", 3, 12, 15, repos=75,
               note="Dans l'amplitude sans douleur"),
            _e("step_up_banc", "principal", 3, 10, repos=75, note=PAR_JAMBE),
            _e("mollets_machine", "principal", 4, 12, 20, repos=60),
            _e("abduction_hanche", "finisher", 3, 15, repos=45,
               note=PAR_COTE + " — moyen fessier"),
        ],
    },
    # ---------------------------------------------------------- samedi
    {
        "jour": 6, "nom": "Course 5 km", "lieu": "exterieur", "type": "cardio",
        "duree": 30, "ordre": 1,
        "exos": [
            _e("course", "principal", 1, 5000, repos=0,
               note="Suit le plan de progression de la semaine"),
        ],
    },
    {
        "jour": 6, "nom": "Full abdos", "lieu": "maison", "type": "core",
        "duree": 30, "ordre": 2,
        # Circuit 4 tours, 45 s d'effort / 15 s de transition.
        "exos": [
            _e(code, "principal", 4, repos=15, tempo="45/15",
               superset="circuit", note=note)
            for code, note in [
                ("planche", "Palier selon progression"),
                ("hollow_hold", None),
                ("releves_jambes", None),
                ("planche_laterale", "Côté droit"),
                ("planche_laterale", "Côté gauche"),
                ("bicycle_crunch", "Lent"),
                ("russian_twist", None),
                ("v_ups", None),
                ("kb_swing", "À deux mains"),
            ]
        ],
    },
    # ---------------------------------------------------------- dimanche
    {
        "jour": 7, "nom": "Mobilité & prehab genou/hanche", "lieu": "maison",
        "type": "prehab", "duree": 15, "ordre": 1,
        "exos": [
            _e("copenhagen", "principal", 3, 20, repos=30, note=PAR_COTE),
            _e("abduction_couche", "principal", 3, 15, repos=30,
               note=PAR_COTE + " — lente"),
            _e("clamshell", "principal", 3, 15, repos=30, note=PAR_COTE),
            _e("step_down_excentrique", "principal", 3, 8, repos=45,
               note="Descente en 3 s — " + PAR_JAMBE),
            _e("wall_sit", "principal", 3, 30, 45, repos=45),
            _e("tibialis_raise", "principal", 3, 20, repos=30),
            _e("soleus_raise", "principal", 3, 20, repos=30, charge=12,
               note=PAR_JAMBE),
            _e("etirement_flechisseurs", "finisher", 2, 40, repos=10,
               note=PAR_COTE),
            _e("etirement_pigeon", "finisher", 2, 40, repos=10, note=PAR_COTE),
            _e("etirement_mollet_mur", "finisher", 2, 40, repos=10,
               note=PAR_COTE),
        ],
    },
    # ------------------------------- bloc abdos du soir (rotation A/B/C)
    # jour_semaine = 0 -> tous les soirs sauf samedi. 5 exercices, ~15 min.
    {
        "jour": 0, "nom": "Abdos A · gainage", "lieu": "maison",
        "type": "core", "duree": 15, "ordre": 1,
        "exos": [
            _e("planche", "principal", 3, 40, repos=40),
            _e("planche_laterale", "principal", 3, 30, repos=30,
               note=PAR_COTE),
            _e("hollow_hold", "principal", 3, 30, repos=40),
            _e("dead_bug", "principal", 3, 10, repos=30, note=PAR_COTE),
            _e("mountain_climber", "finisher", 3, 30, repos=30),
        ],
    },
    {
        "jour": 0, "nom": "Abdos B · fléchisseurs", "lieu": "maison",
        "type": "core", "duree": 15, "ordre": 2,
        "exos": [
            _e("releves_jambes", "principal", 3, 12, repos=40),
            _e("crunch_inverse", "principal", 3, 12, repos=40),
            _e("v_ups", "principal", 3, 10, repos=40),
            _e("hollow_rock", "principal", 3, 15, repos=40),
            _e("planche", "finisher", 1, None, repos=0, note="Au maximum"),
        ],
    },
    {
        "jour": 0, "nom": "Abdos C · obliques", "lieu": "maison",
        "type": "core", "duree": 15, "ordre": 3,
        "exos": [
            _e("russian_twist", "principal", 3, 20, repos=40, charge=12),
            _e("crunch_oblique", "principal", 3, 15, repos=30, note=PAR_COTE),
            _e("bicycle_crunch", "principal", 3, 20, repos=40),
            _e("side_bend_kb", "principal", 3, 15, repos=30, charge=12,
               note=PAR_COTE),
            _e("planche_laterale", "finisher", 3, 30, repos=30, note=PAR_COTE),
        ],
    },
]


def _semer_exercices(c) -> dict:
    """Insère les exercices manquants et renvoie la table `{code: id}`."""
    for row in EXERCICES:
        (code, nom, categorie, lieu, equipement, groupe, unite, chargeable,
         consignes, erreurs, variantes) = row
        c.execute(
            "INSERT OR IGNORE INTO exercice(code, nom, categorie, lieu, "
            "equipement, groupe, unite, chargeable, consignes, "
            "erreurs_frequentes, variantes_json, actif) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,1)",
            (code, nom, categorie, lieu, equipement, groupe, unite,
             int(chargeable), consignes, erreurs,
             json.dumps(variantes, ensure_ascii=False) if variantes else None))
    return {r["code"]: r["id"]
            for r in c.execute("SELECT id, code FROM exercice").fetchall()}


def _poser_exos(c, modele_id: int, exos: list, exo_ids: dict):
    """(Re)pose la liste d'exercices d'un modèle de séance."""
    c.execute("DELETE FROM seance_modele_exo WHERE seance_modele_id = ?",
              (modele_id,))
    for i, e in enumerate(exos, start=1):
        eid = exo_ids.get(e["code"])
        if eid is None:
            continue
        c.execute(
            "INSERT INTO seance_modele_exo(seance_modele_id, exercice_id, "
            "ordre, bloc, series_cible, reps_min, reps_max, repos_sec, "
            "tempo, charge_depart, superset_group, note) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (modele_id, eid, i, e["bloc"], e["series"], e["rmin"],
             e["rmax"], e["repos"], e["tempo"], e["charge"],
             e["superset"], e["note"]))


def seed(c):
    """Sème le programme v2 et désactive le précédent. Idempotent."""
    exo_ids = _semer_exercices(c)

    if c.execute("SELECT id FROM programme WHERE nom = ?",
                 (PROGRAMME_NOM,)).fetchone():
        return                                    # déjà semé

    # L'ancien programme est désactivé, pas supprimé : les séances déjà faites
    # gardent leur modèle et restent lisibles dans les statistiques.
    c.execute("UPDATE programme SET actif = 0")
    cur = c.execute(
        "INSERT INTO programme(nom, actif, date_debut, note) "
        "VALUES (?, 1, date('now'), ?)", (PROGRAMME_NOM, PROGRAMME_NOTE))
    prog_id = cur.lastrowid

    for s in SEANCES:
        cur = c.execute(
            "INSERT INTO seance_modele(programme_id, jour_semaine, nom, lieu, "
            "type, duree_cible_min, ordre_affichage) VALUES (?,?,?,?,?,?,?)",
            (prog_id, s["jour"], s["nom"], s["lieu"], s["type"], s["duree"],
             s["ordre"]))
        _poser_exos(c, cur.lastrowid, s["exos"], exo_ids)


def resynchroniser(c):
    """Réaligne le programme v2 déjà en base sur `SEANCES` ci-dessus.

    `seed()` s'arrête net si le programme existe déjà : sans ce complément,
    une base installée resterait bloquée sur l'ancienne semaine et seule une
    installation neuve verrait le nouveau découpage.

    Les modèles sont **modifiés sur place**, jamais recréés : `seance` pointe
    dessus, et une séance déjà enregistrée doit garder son modèle pour rester
    lisible dans les statistiques. L'appariement se fait par nom, en
    consommant chaque modèle une seule fois — les deux « Mobilité & prehab »
    sont interchangeables, leur contenu est identique.
    """
    prog = c.execute("SELECT id FROM programme WHERE nom = ?",
                     (PROGRAMME_NOM,)).fetchone()
    if prog is None:                    # base neuve : le seed fait le travail
        return seed(c)

    exo_ids = _semer_exercices(c)
    restants = list(c.execute(
        "SELECT id, nom FROM seance_modele WHERE programme_id = ? "
        "ORDER BY jour_semaine, ordre_affichage", (prog["id"],)).fetchall())

    for s in SEANCES:
        trouve = next((i for i, r in enumerate(restants)
                       if r["nom"] == s["nom"]), None)
        if trouve is None:
            cur = c.execute(
                "INSERT INTO seance_modele(programme_id, jour_semaine, nom, "
                "lieu, type, duree_cible_min, ordre_affichage) "
                "VALUES (?,?,?,?,?,?,?)",
                (prog["id"], s["jour"], s["nom"], s["lieu"], s["type"],
                 s["duree"], s["ordre"]))
            modele_id = cur.lastrowid
        else:
            modele_id = restants.pop(trouve)["id"]
            c.execute(
                "UPDATE seance_modele SET jour_semaine = ?, lieu = ?, "
                "type = ?, duree_cible_min = ?, ordre_affichage = ? "
                "WHERE id = ?",
                (s["jour"], s["lieu"], s["type"], s["duree"], s["ordre"],
                 modele_id))
        _poser_exos(c, modele_id, s["exos"], exo_ids)
