"""Contenu de départ sport — programme « Reprise & explosivité ».

Profil : 58 kg / 1 m 68, reprise après deux mois sans muscu (futsal seulement).
Objectifs : prise de muscle, abdos, détente verticale (basket), explosivité foot.
Points de vigilance : **genou droit** et **hanche droite**.

Matériel — salle : station multifonction Unica (poulie haute/basse, chest press,
pec deck, leg extension, leg curl, poste squat) + tapis + vélo. Maison : tapis de
sol + **2 kettlebells de 12 kg**.

Ce module ne contient que des *données* : il est appelé une seule fois par la
migration 2 de `db.py`.
"""
import json

# --------------------------------------------------------------- exercices
# (code, nom, categorie, lieu, equipement, groupe, unite, chargeable,
#  consignes, erreurs_frequentes, variantes)

_VAR_GOBLET = ["1 KB", "1 KB tempo 4 s", "2 KB en rack", "2 KB rack tempo",
               "Squat bulgare 2 KB", "Pistol assisté"]
_VAR_POMPES = ["Sur les genoux", "Standard", "Tempo 4 s", "Pieds surélevés",
               "Archer", "Déclinées lestées (sac à dos)"]
_VAR_RDL = ["2 KB", "2 KB tempo", "Unilatéral 1 KB", "Unilatéral 2 KB"]
_VAR_MILITAIRE = ["2 KB", "Tempo", "Unilatéral", "Z-press assis au sol"]
_VAR_ROWING = ["Unilatéral", "Tempo 3 s", "Renegade row en gainage"]
_VAR_PLANCHE = ["Genoux", "Standard", "Bras tendus", "Tap épaules",
                "Planche avec levée de jambe"]

EXERCICES = [
    # ---- échauffement & mobilité ----
    ("mob_cheville_mur", "Mobilité cheville au mur", "mobilite", "partout",
     "poids_du_corps", "mollets", "reps", 0,
     "Pied à ~10 cm du mur, genou vers le mur sans décoller le talon. Recule "
     "le pied jusqu'à la limite où le talon veut se lever, tiens 2 s.",
     "Talon qui décolle · genou qui part vers l'intérieur.", None),
    ("mob_9090", "90/90 hanches", "mobilite", "partout", "tapis", "tout",
     "reps", 0,
     "Assis, une jambe à 90° devant, l'autre à 90° sur le côté. Bascule "
     "lentement d'un côté à l'autre en gardant le buste droit.",
     "Buste qui s'effondre · mouvement rapide et balistique.", None),
    ("pont_fessier", "Pont fessier", "force", "partout", "tapis", "fessiers",
     "reps", 0,
     "Talons près des fesses, pousse par les talons, serre les fessiers en "
     "haut 1 s. Les côtes restent basses.",
     "Cambrure lombaire à la place de l'extension de hanche.", None),
    ("montees_genoux", "Montées de genoux", "cardio", "partout",
     "poids_du_corps", "tout", "secondes", 0,
     "Sur place, appuis rapides et légers, buste droit.",
     "Se pencher en arrière · taper le sol avec le talon.", None),
    ("velo", "Vélo", "cardio", "salle", "velo", "tout", "secondes", 0,
     "Échauffement : allure très facile, on doit pouvoir parler. Retour au "
     "calme : idem, ça sert à faire redescendre le cardio.",
     "Partir trop fort et arriver cuit au premier exercice.", None),
    ("rotations_epaules", "Rotations d'épaules", "mobilite", "partout",
     "poids_du_corps", "epaules", "reps", 0,
     "Grands cercles lents en avant puis en arrière, bras tendus.",
     "Cercles minuscules et rapides — ça ne réchauffe rien.", None),

    # ---- plyométrie ----
    ("drop_landing", "Drop landing (amorti)", "plyo", "partout",
     "poids_du_corps", "quadriceps", "contacts", 0,
     "Descends d'une marche, atterris sur les deux pieds et **tiens 2 s**. "
     "C'est l'apprentissage de l'amorti, pas un saut.",
     "Atterrir jambes tendues · genoux qui rentrent vers l'intérieur.", None),
    ("pogo_hops", "Pogo hops", "plyo", "partout", "poids_du_corps", "mollets",
     "contacts", 0,
     "Sauts de cheville, genoux quasi tendus. Le sol brûle : contact au sol "
     "le plus court possible, on rebondit sur l'avant-pied.",
     "Plier les genoux à chaque saut · contacts longs et lourds.", None),
    ("squat_jump", "Squat jump", "plyo", "partout", "poids_du_corps",
     "quadriceps", "contacts", 0,
     "Descends à mi-squat, saute haut, **atterrissage silencieux**. 3 s de "
     "reset complet entre chaque rep : la qualité prime sur l'enchaînement.",
     "Enchaîner sans reset · atterrissage bruyant (mauvais amorti).", None),
    ("broad_jump", "Saut horizontal (broad jump)", "plyo", "partout",
     "poids_du_corps", "fessiers", "contacts", 0,
     "Saut vers l'avant, bras qui lancent, réception amortie et stabilisée "
     "2 s avant le saut suivant.",
     "Chercher la distance au prix d'une réception subie.", None),
    ("fente_sautee", "Fente sautée", "plyo", "partout", "poids_du_corps",
     "quadriceps", "contacts", 0,
     "Alternance de fentes en sautant, buste droit, genou arrière qui "
     "descend sans toucher le sol.",
     "Genou avant qui dépasse loin devant · réception raide.", None),
    ("bond_une_jambe", "Bond sur une jambe", "plyo", "partout",
     "poids_du_corps", "fessiers", "contacts", 0,
     "Bonds successifs sur la même jambe, réception contrôlée. **Stop "
     "immédiat** si le genou droit tire.",
     "Genou qui s'effondre vers l'intérieur à la réception.", None),
    ("depth_jump", "Depth jump (marche 20-30 cm)", "plyo", "partout",
     "poids_du_corps", "quadriceps", "contacts", 0,
     "Descends de la marche, et **dès le contact au sol** saute le plus haut "
     "possible. Le temps au sol doit être minimal.",
     "Marche trop haute · temps de contact long (ça devient du squat jump).",
     None),
    ("saut_elan", "Saut avec course d'élan", "plyo", "partout",
     "poids_du_corps", "quadriceps", "contacts", 0,
     "2-3 appuis d'élan puis détente verticale, réception amortie sur les "
     "deux pieds.",
     "Réception sur une jambe raide · trop de répétitions d'affilée.", None),

    # ---- bas du corps, maison (kettlebells) ----
    ("goblet_squat", "Goblet squat KB", "force", "maison", "kettlebell",
     "quadriceps", "reps", 1,
     "KB tenue contre la poitrine, coudes vers l'intérieur. Descends entre "
     "les talons, buste le plus droit possible, remonte en poussant le sol.",
     "Talons qui décollent · genoux qui rentrent · dos qui s'arrondit en bas.",
     _VAR_GOBLET),
    ("fente_bulgare_kb", "Fente bulgare KB", "force", "maison", "kettlebell",
     "quadriceps", "reps", 1,
     "Pied arrière sur une chaise, buste légèrement penché en avant pour "
     "charger le fessier. Descends à la verticale.",
     "Pas assez d'écart (le genou avant part trop loin) · perte d'équilibre "
     "par manque d'appui du gros orteil.", None),
    ("rdl_kb", "Soulevé de terre roumain 2 × KB", "force", "maison",
     "kettlebell", "ischios", "reps", 1,
     "Jambes quasi tendues, on pousse les hanches **en arrière**, dos plat. "
     "Descends jusqu'à sentir l'étirement des ischios, pas plus bas.",
     "Plier les genoux comme un squat · arrondir le bas du dos.", _VAR_RDL),
    ("pont_fessier_1j", "Pont fessier une jambe", "force", "maison", "tapis",
     "fessiers", "reps", 0,
     "Une jambe tendue en l'air, pousse par le talon au sol. Bassin de "
     "niveau : pas de bascule sur le côté.",
     "Bassin qui tombe du côté de la jambe levée · cambrer au lieu de serrer "
     "le fessier.", None),
    ("mollets_1j_kb", "Mollets debout une jambe, KB en main", "force",
     "maison", "kettlebell", "mollets", "reps", 1,
     "Sur l'avant-pied (marche ou livre), amplitude complète : descends bien "
     "bas, monte bien haut, pause 1 s en haut.",
     "Petits rebonds sans amplitude · s'aider du bras d'appui.", None),
    ("soleus_raise", "Soleus raise assis, KB sur le genou", "prehab",
     "maison", "kettlebell", "mollets", "reps", 1,
     "Assis, genou à 90°, KB posée sur le genou. Monte sur l'avant-pied, "
     "pause, descends lentement. **Ne pas sauter cet exercice** : c'est le "
     "muscle qui encaisse la réception de saut et qui soulage le genou.",
     "Amplitude tronquée · rythme trop rapide.", None),

    # ---- haut du corps, salle (Unica) ----
    ("chest_press", "Chest press", "force", "salle", "unica", "pectoraux",
     "reps", 1,
     "Poignées à hauteur de poitrine, omoplates serrées contre le dossier. "
     "Pousse sans verrouiller les coudes.",
     "Épaules qui roulent en avant · amplitude écourtée.", None),
    ("tirage_vertical", "Tirage vertical (poulie haute)", "force", "salle",
     "unica", "dos", "reps", 1,
     "Tire les coudes vers les hanches, poitrine haute. La barre descend au "
     "niveau du menton/haut de poitrine.",
     "Tirer avec les bras seuls · se balancer en arrière.", None),
    ("rowing_poulie_basse", "Rowing poulie basse", "force", "salle", "unica",
     "dos", "reps", 1,
     "Buste fixe, tire vers le nombril, serre les omoplates 1 s, revient en "
     "contrôlant.",
     "Balancer le buste · hausser les épaules.", None),
    ("pec_deck", "Écarté / pec deck", "force", "salle", "unica", "pectoraux",
     "reps", 1,
     "Coudes légèrement fléchis et **fixes**, mouvement d'ouverture-fermeture "
     "à l'épaule uniquement.",
     "Transformer l'écarté en développé en pliant les coudes.", None),
    ("elevations_lat_poulie", "Élévations latérales à la poulie basse",
     "force", "salle", "unica", "epaules", "reps", 1,
     "Monte jusqu'à l'horizontale, petit doigt légèrement plus haut, "
     "descends lentement.",
     "Monter trop haut · s'aider d'une impulsion de jambes.", None),
    ("curl_poulie_basse", "Curl biceps poulie basse", "force", "salle",
     "unica", "bras", "reps", 1,
     "Coudes collés au corps, seul l'avant-bras bouge.",
     "Coudes qui avancent · buste qui recule.", None),
    ("extension_triceps_poulie", "Extension triceps poulie haute", "force",
     "salle", "unica", "bras", "reps", 1,
     "Coudes fixes le long du corps, extension complète en bas, pause 1 s.",
     "Coudes qui s'écartent · aider avec le dos.", None),
    ("face_pull", "Face pull poulie haute", "prehab", "salle", "unica",
     "epaules", "reps", 1,
     "Corde à hauteur du visage, tire vers le front en écartant les mains, "
     "rotation externe en fin de mouvement. Santé d'épaule : léger et propre.",
     "Trop lourd · tirer vers la poitrine au lieu du visage.", None),

    # ---- haut du corps, maison (kettlebells) ----
    ("pompes", "Pompes", "force", "maison", "poids_du_corps", "pectoraux",
     "reps", 0,
     "Corps gainé d'un bloc, coudes à ~45° du buste, poitrine qui frôle le "
     "sol. Choisis la variante du palier atteint.",
     "Bassin qui tombe · coudes en T à 90° · demi-amplitude.", _VAR_POMPES),
    ("rowing_kb_uni", "Rowing KB unilatéral", "force", "maison", "kettlebell",
     "dos", "reps", 1,
     "Appui d'une main sur une chaise, dos plat, tire le coude vers la "
     "hanche, pause 1 s en haut.",
     "Rotation du buste pour aider · tirer avec le biceps seul.", _VAR_ROWING),
    ("dev_militaire_kb", "Développé militaire debout 2 × KB", "force",
     "maison", "kettlebell", "epaules", "reps", 1,
     "Debout, KB en rack, fessiers et abdos serrés. Pousse à la verticale "
     "sans cambrer.",
     "Cambrure lombaire compensatoire · pousser en avant du visage.",
     _VAR_MILITAIRE),
    ("floor_press_kb", "Floor press 2 × KB", "force", "maison", "kettlebell",
     "pectoraux", "reps", 1,
     "Allongé au sol, les triceps touchent le sol en bas puis on repousse. "
     "L'amplitude limitée protège l'épaule.",
     "Rebondir les coudes sur le sol.", None),
    ("elevations_lat_kb", "Élévations latérales KB", "force", "maison",
     "kettlebell", "epaules", "reps", 1,
     "Jusqu'à l'horizontale, descente lente. Léger : c'est un muscle de "
     "finition.",
     "Trop lourd, donc balancé avec tout le corps.", None),
    ("curl_marteau_kb", "Curl marteau 2 × KB", "force", "maison",
     "kettlebell", "bras", "reps", 1,
     "Prise neutre (pouces vers le haut), coudes collés.",
     "Balancer les KB · coudes qui avancent.", None),
    ("ext_triceps_tete_kb",
     "Extension triceps au-dessus de la tête (1 KB, 2 mains)", "force",
     "maison", "kettlebell", "bras", "reps", 1,
     "KB tenue à deux mains derrière la tête, coudes serrés vers l'avant, "
     "extension complète.",
     "Coudes qui s'écartent en grand · cambrer.", None),
    ("suitcase_carry", "Suitcase carry KB", "core", "maison", "kettlebell",
     "abdos", "secondes", 1,
     "Marche lestée d'un seul côté, épaules de niveau, on résiste à "
     "l'inclinaison. C'est un exercice d'abdos, pas de bras.",
     "Se pencher du côté de la charge · marcher trop vite.", None),

    # ---- bas du corps, salle ----
    ("presse_cuisses", "Squat / presse à cuisses Unica", "force", "salle",
     "unica", "quadriceps", "reps", 1,
     "Pieds à largeur d'épaules, descends à l'amplitude confortable, "
     "genoux dans l'axe des pieds. Ne verrouille pas en haut.",
     "Décoller le bassin du dossier en bas · verrouiller les genoux.", None),
    ("leg_curl", "Leg curl", "force", "salle", "unica", "ischios", "reps", 1,
     "Ischios prioritaires : c'est le muscle qui protège le genou et qui "
     "sert au sprint. Contraction 1 s, retour lent.",
     "Décoller les hanches · retour en chute libre.", None),
    ("leg_extension", "Leg extension", "force", "salle", "unica",
     "quadriceps", "reps", 1,
     "**Dans l'amplitude sans douleur uniquement.** Si le genou droit "
     "pique, réduis l'amplitude haute, pas la charge.",
     "Aller chercher l'extension complète malgré la gêne.", None),
    ("step_up_banc", "Step-up sur banc (ou fentes marchées)", "force",
     "salle", "unica", "fessiers", "reps", 1,
     "Monte en poussant par le talon de la jambe sur le banc, sans "
     "impulsion de la jambe au sol. Descente contrôlée.",
     "S'aider d'un rebond de la jambe basse.", None),
    ("mollets_machine", "Mollets", "force", "salle", "unica", "mollets",
     "reps", 1,
     "Amplitude complète, pause 1 s en haut et en bas.",
     "Rebonds sur le tendon d'Achille.", None),
    ("abduction_hanche", "Abduction de hanche (moyen fessier)", "prehab",
     "salle", "unica", "fessiers", "reps", 1,
     "Poulie basse à la cheville ou couché sur le côté. Mouvement lent, on "
     "cible le moyen fessier — clé pour la hanche droite.",
     "Basculer le bassin en arrière pour tricher.", None),
    ("tapis", "Tapis de course", "cardio", "salle", "tapis", "tout",
     "secondes", 0,
     "Semaines impaires : footing continu allure conversation. Semaines "
     "paires : 8 × (1 min rapide / 1 min marche).",
     "Partir sur une allure qu'on ne tient pas 15 min.", None),
    ("course", "Course extérieur", "cardio", "partout", "poids_du_corps",
     "tout", "metres", 0,
     "Allure conversation sauf indication. Suis le plan de la semaine.",
     "Partir trop vite les 500 premiers mètres.", None),

    # ---- core / abdos ----
    ("planche", "Planche", "core", "partout", "tapis", "abdos", "secondes", 0,
     "Corps d'un bloc, bassin en rétroversion (côtes basses, fessiers "
     "serrés). Mieux vaut 20 s parfaites que 60 s affaissées.",
     "Fesses en l'air ou bassin qui tombe · apnée.", _VAR_PLANCHE),
    ("hollow_hold", "Hollow hold", "core", "partout", "tapis", "abdos",
     "secondes", 0,
     "Bas du dos **plaqué au sol**, épaules et jambes décollées. Si le dos "
     "se creuse, remonte les jambes.",
     "Creux lombaire · retenir sa respiration.", None),
    ("releves_jambes", "Relevés de jambes au sol", "core", "partout", "tapis",
     "abdos", "reps", 0,
     "Mains sous les fesses, descends les jambes lentement sans décoller le "
     "bas du dos.",
     "Descendre trop bas et cambrer · utiliser l'élan.", None),
    ("planche_laterale", "Planche latérale", "core", "partout", "tapis",
     "abdos", "secondes", 0,
     "Coude sous l'épaule, hanche haute, corps aligné. Regarde droit devant.",
     "Hanche qui s'affaisse · épaule qui rentre dans le cou.", None),
    ("dead_bug", "Dead bug lent", "core", "partout", "tapis", "abdos", "reps",
     0,
     "Dos plaqué au sol en permanence. Bras et jambe opposés descendent "
     "lentement, expire en descendant.",
     "Décoller le bas du dos · aller vite.", None),
    ("russian_twist", "Russian twist KB", "core", "partout", "kettlebell",
     "abdos", "reps", 1,
     "Buste incliné, rotation depuis le tronc (pas seulement les bras), "
     "la KB touche à peine le sol.",
     "Bouger les bras sans tourner le buste.", None),
    ("superman", "Extension lombaire au sol (superman)", "prehab", "partout",
     "tapis", "tout", "reps", 0,
     "À plat ventre, décolle bras et jambes, pause 1 s, redescends. "
     "Mouvement court et contrôlé.",
     "Hyperextension violente du cou.", None),
    ("kb_swing", "KB swing à deux mains", "force", "partout", "kettlebell",
     "fessiers", "reps", 1,
     "C'est une charnière de hanche, pas un squat : la KB est projetée par "
     "l'extension de hanche. Serre fessiers et abdos en haut.",
     "Squatter le mouvement · monter la KB avec les bras · cambrer en haut.",
     None),
    ("pallof_press", "Pallof press isométrique au KB", "core", "partout",
     "kettlebell", "abdos", "secondes", 0,
     "KB tenue à deux mains devant le sternum, bras tendus sur le côté : on "
     "résiste à la rotation. Anti-rotation pur.",
     "Laisser le buste tourner · retenir sa respiration.", None),
    ("crunch_inverse", "Crunch inversé", "core", "partout", "tapis", "abdos",
     "reps", 0,
     "Genoux vers la poitrine, on décolle le bassin **par les abdos**, pas "
     "par l'élan des jambes.",
     "Balancer les jambes · pousser avec les mains.", None),

    # ---- prehab genou droit / hanche droite ----
    ("copenhagen", "Copenhagen adducteur (genou fléchi)", "prehab", "partout",
     "tapis", "tout", "secondes", 0,
     "Version genou fléchi : le genou de la jambe haute repose sur le "
     "support. Hanche haute, corps aligné.",
     "Hanche qui s'affaisse · passer trop vite à la version tendue.", None),
    ("abduction_couche", "Abduction couché sur le côté (jambe tendue)",
     "prehab", "partout", "tapis", "fessiers", "reps", 0,
     "Jambe tendue, orteils légèrement vers le sol, montée **lente**. On "
     "doit sentir brûler le côté de la hanche.",
     "Basculer le bassin en arrière · aller vite.", None),
    ("clamshell", "Clamshell", "prehab", "partout", "tapis", "fessiers",
     "reps", 0,
     "Couché sur le côté, genoux fléchis, talons joints : ouvre le genou "
     "haut sans bouger le bassin.",
     "Rouler le bassin en arrière pour gagner de l'amplitude.", None),
    ("step_down_excentrique", "Step-down excentrique", "prehab", "partout",
     "poids_du_corps", "quadriceps", "reps", 0,
     "Descente d'une marche **en 3 s**, genou dans l'axe, dans l'amplitude "
     "sans douleur. Remonte avec l'autre jambe.",
     "Descendre en chute libre · genou qui rentre.", None),
    ("wall_sit", "Wall sit isométrique", "prehab", "partout",
     "poids_du_corps", "quadriceps", "secondes", 0,
     "Dos plaqué au mur, cuisses à ~90°, poids sur les talons.",
     "Descendre plus bas que ce que le genou tolère.", None),
    ("tibialis_raise", "Tibialis raise dos au mur", "prehab", "partout",
     "poids_du_corps", "mollets", "reps", 0,
     "Dos au mur, pieds avancés de ~30 cm, remonte les orteils vers les "
     "tibias. Antagoniste du mollet : soulage le genou et l'amorti.",
     "Amplitude minuscule · pieds trop près du mur.", None),
    ("etirement_flechisseurs", "Étirement fléchisseurs de hanche", "mobilite",
     "partout", "tapis", "tout", "secondes", 0,
     "En fente à genou, rétroversion du bassin **avant** d'avancer. C'est la "
     "rétroversion qui étire, pas l'amplitude.",
     "Cambrer pour aller plus loin.", None),
    ("etirement_pigeon", "Pigeon", "mobilite", "partout", "tapis", "tout",
     "secondes", 0,
     "Tibia devant, hanche arrière tendue, buste qui descend lentement. "
     "Respire dans l'étirement.",
     "Forcer sur un genou douloureux.", None),
    ("etirement_mollet_mur", "Mollet au mur", "mobilite", "partout",
     "poids_du_corps", "mollets", "secondes", 0,
     "Jambe arrière tendue, talon au sol, bassin qui avance. Puis une "
     "version genou fléchi pour le soléaire.",
     "Talon qui décolle.", None),
]

# ------------------------------------------------------------- séances type


def _e(code, bloc, series, rmin=None, rmax=None, repos=60, tempo=None,
       charge=None, superset=None, note=None):
    """Une ligne de `seance_modele_exo` (lisible à l'œil)."""
    return {"code": code, "bloc": bloc, "series": series, "rmin": rmin,
            "rmax": rmax if rmax is not None else rmin, "repos": repos,
            "tempo": tempo, "charge": charge, "superset": superset,
            "note": note}


PAR_JAMBE = "par jambe"
PAR_COTE = "par côté"
PAR_BRAS = "par bras"

SEANCES = [
    # ---------------------------------------------------------- lundi
    {
        "jour": 1, "nom": "Bas du corps & explosivité", "lieu": "maison",
        "type": "mixte", "duree": 45, "ordre": 1,
        "exos": [
            _e("mob_cheville_mur", "echauffement", 2, 10, repos=30,
               note=PAR_COTE),
            _e("mob_9090", "echauffement", 2, 8, repos=30, note=PAR_COTE),
            _e("pont_fessier", "echauffement", 2, 15, repos=30),
            _e("montees_genoux", "echauffement", 2, 30, repos=30),

            _e("pogo_hops", "explosif", 3, 15, repos=45),
            _e("squat_jump", "explosif", 4, 5, repos=90,
               note="Atterrissage silencieux, 3 s de reset entre chaque"),
            _e("broad_jump", "explosif", 3, 3, repos=90,
               note="À partir de la semaine 3"),

            _e("goblet_squat", "principal", 4, 10, 15, repos=90, tempo="3-1-1",
               charge=12),
            _e("fente_bulgare_kb", "principal", 3, 8, 12, repos=75,
               tempo="2-1-1", charge=12,
               note="Pied arrière sur chaise — " + PAR_JAMBE),
            _e("rdl_kb", "principal", 4, 10, 15, repos=90, tempo="3-0-1",
               charge=24, note="2 × KB de 12"),
            _e("pont_fessier_1j", "principal", 3, 12, 15, repos=60,
               tempo="2-1-2", note=PAR_JAMBE),
            _e("mollets_1j_kb", "principal", 3, 15, 20, repos=45, tempo="2-1-2",
               charge=12, note=PAR_JAMBE),
            _e("soleus_raise", "finisher", 2, 20, repos=45, tempo="2-1-2",
               charge=12, note=PAR_JAMBE + " — ne pas sauter"),
        ],
    },
    # ---------------------------------------------------------- mardi
    {
        "jour": 2, "nom": "Haut du corps (Unica)", "lieu": "salle",
        "type": "force", "duree": 50, "ordre": 1,
        "exos": [
            _e("velo", "echauffement", 1, 300, repos=0, note="Allure facile"),
            _e("rotations_epaules", "echauffement", 2, 15, repos=20),
            _e("chest_press", "principal", 4, 8, 12, repos=120,
               note="Précède de 2 séries très légères en échauffement"),
            _e("tirage_vertical", "principal", 4, 8, 12, repos=120),
            _e("rowing_poulie_basse", "principal", 4, 10, 12, repos=90),
            _e("pec_deck", "principal", 3, 12, 15, repos=60),
            _e("elevations_lat_poulie", "principal", 3, 12, 15, repos=60),
            _e("curl_poulie_basse", "principal", 3, 10, 15, repos=30,
               superset="A"),
            _e("extension_triceps_poulie", "principal", 3, 10, 15, repos=60,
               superset="A"),
            _e("face_pull", "finisher", 3, 15, repos=45,
               note="Santé d'épaule — léger et propre"),
            _e("velo", "finisher", 1, 480, repos=0, note="Retour au calme"),
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
        "jour": 4, "nom": "Haut du corps (kettlebells)", "lieu": "maison",
        "type": "force", "duree": 45, "ordre": 1,
        "exos": [
            _e("rotations_epaules", "echauffement", 2, 15, repos=20),
            _e("pompes", "principal", 4, 8, 15, repos=90, tempo="3-1-1",
               note="Variante selon le palier atteint"),
            _e("rowing_kb_uni", "principal", 4, 10, 12, repos=75, tempo="2-1-2",
               charge=12, note=PAR_BRAS),
            _e("dev_militaire_kb", "principal", 4, 8, 12, repos=90,
               tempo="2-0-1", charge=24, note="2 × KB de 12"),
            _e("floor_press_kb", "principal", 3, 10, 15, repos=75,
               tempo="3-1-1", charge=24, note="2 × KB de 12"),
            _e("elevations_lat_kb", "principal", 3, 12, 15, repos=45,
               tempo="2-1-2", charge=12),
            _e("curl_marteau_kb", "principal", 3, 10, 15, repos=30,
               tempo="2-1-2", charge=24, superset="B"),
            _e("ext_triceps_tete_kb", "principal", 3, 10, 15, repos=45,
               tempo="3-1-1", charge=12, superset="B"),
            _e("suitcase_carry", "finisher", 3, 40, repos=45, charge=12,
               note=PAR_COTE),
        ],
    },
    # ---------------------------------------------------------- vendredi
    {
        "jour": 5, "nom": "Bas du corps + tapis", "lieu": "salle",
        "type": "force", "duree": 55, "ordre": 1,
        "exos": [
            _e("velo", "echauffement", 1, 300, repos=0, note="Allure facile"),
            _e("presse_cuisses", "principal", 4, 8, 12, repos=150),
            _e("leg_curl", "principal", 4, 10, 15, repos=90,
               note="Ischios prioritaires : genou + sprint"),
            _e("leg_extension", "principal", 3, 12, 15, repos=75,
               note="Dans l'amplitude sans douleur"),
            _e("step_up_banc", "principal", 3, 10, repos=75, note=PAR_JAMBE),
            _e("mollets_machine", "principal", 4, 12, 20, repos=60),
            _e("abduction_hanche", "principal", 3, 15, repos=45,
               note=PAR_COTE + " — moyen fessier"),
            _e("tapis", "finisher", 1, 900, repos=0,
               note="Semaines impaires : footing continu allure conversation · "
                    "semaines paires : 8 × (1 min rapide / 1 min marche)"),
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
        # Circuit 4 tours, 45 s d'effort / 15 s de transition, 90 s entre tours.
        "exos": [
            _e(code, "principal", 4, repos=15, tempo="45/15",
               superset="circuit", note=note)
            for code, note in [
                ("planche", "Palier selon progression"),
                ("hollow_hold", None),
                ("releves_jambes", None),
                ("planche_laterale", "Côté droit"),
                ("planche_laterale", "Côté gauche"),
                ("dead_bug", "Lent"),
                ("russian_twist", None),
                ("superman", None),
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
    # ------------------------------------ bloc core du soir (rotation A/B/C)
    # jour_semaine = 0 -> « tous les soirs », l'ordre_affichage porte la
    # rotation : 1 = A, 2 = B, 3 = C.
    {
        "jour": 0, "nom": "Core A · anti-extension", "lieu": "maison",
        "type": "core", "duree": 10, "ordre": 1,
        "exos": [
            _e("planche", "principal", 3, 40, repos=45),
            _e("hollow_hold", "principal", 3, 30, repos=45),
            _e("dead_bug", "principal", 3, 10, repos=45, note=PAR_COTE),
        ],
    },
    {
        "jour": 0, "nom": "Core B · anti-rotation & latéral", "lieu": "maison",
        "type": "core", "duree": 10, "ordre": 2,
        "exos": [
            _e("planche_laterale", "principal", 3, 30, repos=45,
               note=PAR_COTE),
            _e("pallof_press", "principal", 3, 20, repos=45, charge=12,
               note=PAR_COTE),
            _e("suitcase_carry", "principal", 3, 30, repos=45, charge=12,
               note=PAR_COTE),
        ],
    },
    {
        "jour": 0, "nom": "Core C · fléchisseurs & obliques", "lieu": "maison",
        "type": "core", "duree": 10, "ordre": 3,
        "exos": [
            _e("releves_jambes", "principal", 3, 12, repos=45),
            _e("crunch_inverse", "principal", 3, 12, repos=45),
            _e("russian_twist", "principal", 3, 20, repos=45, charge=12),
            _e("planche", "finisher", 1, None, repos=0, note="Au maximum"),
        ],
    },
]

PROGRAMME_NOM = "Reprise & explosivité"
PROGRAMME_NOTE = (
    "9 semaines. Prise de muscle + abdos + détente verticale (basket) + "
    "explosivité foot. Genou droit et hanche droite sous surveillance : "
    "saisie de la douleur 0-10 à chaque fin de séance."
)


def _aujourdhui() -> str:
    """La journée du cockpit, pas celle de SQLite.

    `date('now')` est en **UTC** et ignore la bascule de 4 h du matin : un
    programme semé à 1 h démarrait donc le lendemain de la journée en cours,
    ce qui décalait d'un jour tout le calcul des semaines.
    """
    from .jour import jour_courant
    return jour_courant()


def seed(c):
    """Insère le référentiel et le programme. Idempotent (INSERT OR IGNORE)."""
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

    exo_ids = {r["code"]: r["id"]
               for r in c.execute("SELECT id, code FROM exercice").fetchall()}

    row = c.execute("SELECT id FROM programme WHERE nom = ?",
                    (PROGRAMME_NOM,)).fetchone()
    if row:
        return  # déjà semé
    cur = c.execute(
        "INSERT INTO programme(nom, actif, date_debut, note) "
        "VALUES (?, 1, ?, ?)", (PROGRAMME_NOM, _aujourdhui(), PROGRAMME_NOTE))
    prog_id = cur.lastrowid

    for s in SEANCES:
        cur = c.execute(
            "INSERT INTO seance_modele(programme_id, jour_semaine, nom, lieu, "
            "type, duree_cible_min, ordre_affichage) VALUES (?,?,?,?,?,?,?)",
            (prog_id, s["jour"], s["nom"], s["lieu"], s["type"], s["duree"],
             s["ordre"]))
        modele_id = cur.lastrowid
        for i, e in enumerate(s["exos"], start=1):
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
