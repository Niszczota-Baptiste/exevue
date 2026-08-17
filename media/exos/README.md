# Médias d'exercices

Dépose ici une image ou une vidéo par exercice. Elle est détectée
automatiquement et servie au téléphone pendant la séance.

## Convention de nommage

```
media/exos/<code_exercice>.gif   (ou .png .jpg .webp .mp4 .svg)
```

Le `<code_exercice>` est la colonne `code` de la table `exercice`. Pour la
retrouver : onglet **Système → Export CSV → `exercice`**, ou directement

```bash
sqlite3 cockpit.db "SELECT code, nom FROM exercice ORDER BY code;"
```

Quelques exemples : `goblet_squat.gif`, `pompes.mp4`, `rdl_kb.png`,
`copenhagen.gif`, `depth_jump.gif`.

## Ce qui se passe sans fichier

Rien ne casse. Pour chaque exercice sans média, l'app **génère un schéma SVG
maison** (silhouette + flèche de mouvement orientée selon le groupe musculaire)
servi à la même adresse. C'est volontairement sommaire : ça situe le mouvement,
ça ne remplace pas une démonstration.

Le champ `video_url` de la table `exercice` reste libre : tu peux y coller un
lien vers une vidéo en ligne, il est affiché tel quel dans la fiche.

## Droits

**Aucun média récupéré sur le web n'est embarqué dans le dépôt** — les GIFs
d'exercices qui circulent sont presque tous sous droits. Ce dossier est ignoré
par git (sauf ce README) : ce que tu y déposes reste chez toi.

Si tu veux des médias : filme-toi (c'est de loin le plus utile pour corriger sa
technique), ou achète une banque d'images dont la licence autorise l'usage.

## Poids

Le téléphone met les médias en cache **en base64 dans `localStorage`**, dont le
quota Safari tourne autour de 5 Mo. L'app ignore les fichiers de plus de 220 Ko
et ne met en cache que les exercices d'aujourd'hui et de demain. Vise donc des
GIFs courts et compressés (2-3 s, ~150 Ko), pas des vidéos HD.

## Garder l'écran allumé (optionnel)

Safari en HTTP simple ne peut pas verrouiller l'écran allumé. Si tu déposes une
petite vidéo muette en boucle ici sous le nom `nosleep.mp4` (1 s, quelques Ko
suffisent), la page mobile la lira en fond pendant la séance, ce qui empêche
iOS d'éteindre l'écran. Sans ce fichier, l'app affiche simplement le rappel :

> Réglages iOS → Écran et luminosité → Verrouillage auto → **Jamais**
