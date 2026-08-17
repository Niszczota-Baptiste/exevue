"""Encodeur QR minimal — **stdlib pure**, aucune dépendance image.

Mode octet, correction d'erreur **M**, versions 1 à 6 (jusqu'à 106 octets) :
largement de quoi encoder `http://192.168.x.x:8790/?t=jeton`. Le résultat est
une matrice de booléens, dessinée en rectangles sur un `CTkCanvas` par l'UI.

Si l'encodage échoue pour une raison quelconque, `matrice()` lève et l'appelant
retombe sur « URL en gros + bouton Copier » : jamais de plantage pour un QR.
"""

# (version -> (codewords de données par bloc, nb blocs, codewords EC par bloc))
# Niveau M uniquement, d'après la table 9 de l'ISO/IEC 18004.
_SPECS_M = {
    1: [(16, 1, 10)],
    2: [(28, 1, 16)],
    3: [(44, 1, 26)],
    4: [(32, 2, 18)],
    5: [(43, 2, 24)],
    6: [(27, 4, 16)],
}
# Capacité utile en octets (mode octet, niveau M).
CAPACITES = {1: 14, 2: 26, 3: 42, 4: 62, 5: 84, 6: 106}
# Centres des motifs d'alignement.
_ALIGNEMENT = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30],
               6: [6, 34]}

_EC_M_BITS = 0b00        # indicateur de niveau M dans l'info de format


# ------------------------------------------------------------ GF(2^8)

_EXP = [0] * 512
_LOG = [0] * 256


def _init_gf():
    x = 1
    for i in range(255):
        _EXP[i] = x
        _LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D       # polynôme primitif
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


_init_gf()


def _gf_mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _polynome_generateur(n):
    poly = [1]
    for i in range(n):
        suivant = [0] * (len(poly) + 1)
        for j, coef in enumerate(poly):
            suivant[j] ^= coef
            suivant[j + 1] ^= _gf_mul(coef, _EXP[i])
        poly = suivant
    return poly


def _codes_correction(data, nb_ec):
    gen = _polynome_generateur(nb_ec)
    reste = list(data) + [0] * nb_ec
    for i in range(len(data)):
        coef = reste[i]
        if coef == 0:
            continue
        for j, g in enumerate(gen):
            reste[i + j] ^= _gf_mul(g, coef)
    return reste[len(data):]


# ------------------------------------------------------- encodage données

def _version_pour(nb_octets):
    for version in sorted(CAPACITES):
        if nb_octets <= CAPACITES[version]:
            return version
    raise ValueError(f"{nb_octets} octets : trop long pour un QR v1-6 "
                     f"(max {CAPACITES[6]})")


def _bits_donnees(octets, version):
    total_data = sum(d * n for d, n, _ in _SPECS_M[version])
    bits = []

    def pousse(valeur, longueur):
        for i in range(longueur - 1, -1, -1):
            bits.append((valeur >> i) & 1)

    pousse(0b0100, 4)                  # mode octet
    pousse(len(octets), 8)             # compteur (8 bits pour v1-9)
    for o in octets:
        pousse(o, 8)
    # terminateur, puis alignement octet
    pousse(0, min(4, total_data * 8 - len(bits)))
    while len(bits) % 8:
        bits.append(0)

    codes = [int("".join(str(b) for b in bits[i:i + 8]), 2)
             for i in range(0, len(bits), 8)]
    remplissage = (0xEC, 0x11)
    i = 0
    while len(codes) < total_data:
        codes.append(remplissage[i % 2])
        i += 1
    return codes


def _message_final(codes, version):
    """Découpe en blocs, calcule l'EC, puis entrelace le tout."""
    blocs_data, blocs_ec = [], []
    curseur = 0
    for taille_data, nb_blocs, nb_ec in _SPECS_M[version]:
        for _ in range(nb_blocs):
            bloc = codes[curseur:curseur + taille_data]
            curseur += taille_data
            blocs_data.append(bloc)
            blocs_ec.append(_codes_correction(bloc, nb_ec))

    sortie = []
    for i in range(max(len(b) for b in blocs_data)):
        for bloc in blocs_data:
            if i < len(bloc):
                sortie.append(bloc[i])
    for i in range(max(len(b) for b in blocs_ec)):
        for bloc in blocs_ec:
            if i < len(bloc):
                sortie.append(bloc[i])
    return sortie


# ------------------------------------------------------- placement modules

def _grille_vide(taille):
    return [[None] * taille for _ in range(taille)]


def _pose_carre(grille, r0, c0, motif):
    for dr, ligne in enumerate(motif):
        for dc, val in enumerate(ligne):
            r, c = r0 + dr, c0 + dc
            if 0 <= r < len(grille) and 0 <= c < len(grille):
                grille[r][c] = val


_FINDER = [[1, 1, 1, 1, 1, 1, 1],
           [1, 0, 0, 0, 0, 0, 1],
           [1, 0, 1, 1, 1, 0, 1],
           [1, 0, 1, 1, 1, 0, 1],
           [1, 0, 1, 1, 1, 0, 1],
           [1, 0, 0, 0, 0, 0, 1],
           [1, 1, 1, 1, 1, 1, 1]]

_ALIGN_MOTIF = [[1, 1, 1, 1, 1],
                [1, 0, 0, 0, 1],
                [1, 0, 1, 0, 1],
                [1, 0, 0, 0, 1],
                [1, 1, 1, 1, 1]]


def _motifs_fixes(version):
    taille = 17 + 4 * version
    grille = _grille_vide(taille)

    for r0, c0 in ((0, 0), (0, taille - 7), (taille - 7, 0)):
        _pose_carre(grille, r0, c0, _FINDER)
    # séparateurs (blancs) autour des trois repères
    for r0, c0 in ((0, 0), (0, taille - 8), (taille - 8, 0)):
        for i in range(8):
            for r, c in ((r0 + i, c0 + 7 if c0 == 0 else c0),
                         (r0 + 7 if r0 == 0 else r0, c0 + i)):
                if 0 <= r < taille and 0 <= c < taille and grille[r][c] is None:
                    grille[r][c] = 0

    for i in range(8, taille - 8):          # motifs de synchronisation
        val = 1 - (i % 2)
        grille[6][i] = val
        grille[i][6] = val

    centres = _ALIGNEMENT[version]
    for r in centres:
        for c in centres:
            proche_repere = ((r < 8 and c < 8) or (r < 8 and c > taille - 9)
                             or (r > taille - 9 and c < 8))
            if proche_repere:
                continue
            _pose_carre(grille, r - 2, c - 2, _ALIGN_MOTIF)

    grille[taille - 8][8] = 1               # module sombre, toujours noir

    # réservation des zones d'information de format
    for i in range(9):
        if grille[8][i] is None:
            grille[8][i] = 0
        if grille[i][8] is None:
            grille[i][8] = 0
    for i in range(8):
        if grille[8][taille - 1 - i] is None:
            grille[8][taille - 1 - i] = 0
        if grille[taille - 1 - i][8] is None:
            grille[taille - 1 - i][8] = 0
    return grille


def _cases_reservees(version):
    """Même géométrie que `_motifs_fixes`, mais en booléens « occupé »."""
    grille = _motifs_fixes(version)
    return [[cell is not None for cell in ligne] for ligne in grille]


def _place_donnees(grille, reserve, bits):
    taille = len(grille)
    i = 0
    col = taille - 1
    montant = True
    while col > 0:
        if col == 6:            # on saute la colonne de synchronisation
            col -= 1
        lignes = range(taille - 1, -1, -1) if montant else range(taille)
        for row in lignes:
            for dc in (0, 1):
                c = col - dc
                if reserve[row][c]:
                    continue
                grille[row][c] = bits[i] if i < len(bits) else 0
                i += 1
        montant = not montant
        col -= 2


# ------------------------------------------------------------- masquage

_MASQUES = [
    lambda i, j: (i + j) % 2 == 0,
    lambda i, j: i % 2 == 0,
    lambda i, j: j % 3 == 0,
    lambda i, j: (i + j) % 3 == 0,
    lambda i, j: (i // 2 + j // 3) % 2 == 0,
    lambda i, j: (i * j) % 2 + (i * j) % 3 == 0,
    lambda i, j: ((i * j) % 2 + (i * j) % 3) % 2 == 0,
    lambda i, j: ((i + j) % 2 + (i * j) % 3) % 2 == 0,
]


def _applique_masque(grille, reserve, num):
    regle = _MASQUES[num]
    sortie = [ligne[:] for ligne in grille]
    for r in range(len(grille)):
        for c in range(len(grille)):
            if not reserve[r][c] and regle(r, c):
                sortie[r][c] ^= 1
    return sortie


def _penalite(grille):
    taille = len(grille)
    score = 0

    def suite(vals):
        total = 0
        courant, longueur = vals[0], 1
        for v in vals[1:]:
            if v == courant:
                longueur += 1
            else:
                if longueur >= 5:
                    total += 3 + (longueur - 5)
                courant, longueur = v, 1
        if longueur >= 5:
            total += 3 + (longueur - 5)
        return total

    for r in range(taille):                                   # règle 1
        score += suite(grille[r])
        score += suite([grille[i][r] for i in range(taille)])

    for r in range(taille - 1):                               # règle 2
        for c in range(taille - 1):
            bloc = (grille[r][c], grille[r][c + 1], grille[r + 1][c],
                    grille[r + 1][c + 1])
            if bloc[0] == bloc[1] == bloc[2] == bloc[3]:
                score += 3

    # Règle 3 : motif 1:1:3:1:1 précédé OU suivi de 4 modules clairs. Au bord
    # du symbole, c'est la zone de silence qui fait office de zone claire.
    noyau = [1, 0, 1, 1, 1, 0, 1]
    for r in range(taille):
        ligne = grille[r]
        colonne = [grille[i][r] for i in range(taille)]
        for vals in (ligne, colonne):
            for c in range(taille - 6):
                if vals[c:c + 7] != noyau:
                    continue
                if (c == 0 or c == taille - 7
                        or not any(vals[max(0, c - 4):c])
                        or not any(vals[c + 7:c + 11])):
                    score += 40

    sombres = sum(sum(ligne) for ligne in grille)             # règle 4
    pourcent = sombres * 100 / (taille * taille)
    score += int(abs(pourcent - 50) / 5) * 10
    return score


# ------------------------------------------------------ info de format

def _bits_format(masque):
    donnees = (_EC_M_BITS << 3) | masque
    valeur = donnees << 10
    generateur = 0b10100110111
    for i in range(4, -1, -1):
        if valeur & (1 << (i + 10)):
            valeur ^= generateur << i
    return ((donnees << 10) | valeur) ^ 0b101010000010010


def _positions_format(taille):
    """Les 15 positions de chaque copie, **du bit de poids fort au plus faible**
    (ISO/IEC 18004 figure 25). Table explicite : c'est le point du format le
    plus facile à inverser sans s'en apercevoir."""
    copie1 = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
              (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
    copie2 = [(taille - 1 - i, 8) for i in range(7)]
    copie2 += [(8, taille - 8 + i) for i in range(8)]
    return copie1, copie2


def _pose_format(grille, masque):
    taille = len(grille)
    bits = _bits_format(masque)
    copie1, copie2 = _positions_format(taille)
    for i in range(15):
        bit = (bits >> (14 - i)) & 1
        r, c = copie1[i]
        grille[r][c] = bit
        r, c = copie2[i]
        grille[r][c] = bit
    grille[taille - 8][8] = 1     # module sombre : jamais recouvert


# ---------------------------------------------------------------- API

def matrice(texte: str, marge: int = 2) -> list:
    """Matrice de booléens (True = module noir), marge blanche comprise.

    Lève `ValueError` si le texte dépasse la capacité d'un QR v6-M.
    """
    octets = texte.encode("utf-8")
    version = _version_pour(len(octets))
    codes = _message_final(_bits_donnees(octets, version), version)

    bits = []
    for code in codes:
        for i in range(7, -1, -1):
            bits.append((code >> i) & 1)

    reserve = _cases_reservees(version)
    base = _motifs_fixes(version)
    grille = [[0 if cell is None else cell for cell in ligne] for ligne in base]
    _place_donnees(grille, reserve, bits)

    # ISO/IEC 18004:2015 §7.8 : l'évaluation se fait **sans** l'information de
    # format — on ne l'écrit que sur le masque retenu.
    meilleur, meilleur_score = None, None
    for num in range(8):
        candidat = _applique_masque(grille, reserve, num)
        score = _penalite(candidat)
        if meilleur_score is None or score < meilleur_score:
            meilleur, meilleur_score, meilleur_num = candidat, score, num
    _pose_format(meilleur, meilleur_num)

    taille = len(meilleur)
    plein = [[False] * (taille + 2 * marge) for _ in range(marge)]
    for ligne in meilleur:
        plein.append([False] * marge + [bool(v) for v in ligne]
                     + [False] * marge)
    plein += [[False] * (taille + 2 * marge) for _ in range(marge)]
    return plein


def en_texte(texte: str) -> str:
    """Rendu ASCII (deux caractères par module) — pratique pour déboguer."""
    return "\n".join("".join("██" if v else "  " for v in ligne)
                     for ligne in matrice(texte))
