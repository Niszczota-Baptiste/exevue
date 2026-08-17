# Prompt à donner à Claude sur le repo du site (titisite)

Ce prompt fait évoluer le site pour alimenter l'onglet **[Alertes]** du cockpit :
flux enrichi (items, récompenses, coordonnées) + page d'admin « Cockpit » pour
gérer **personnellement** ce qui est envoyé (quêtes suivies, liste d'items
perso), plutôt que d'exposer la wishlist de groupe.

Il **remplace** l'ancien patch `titisite-cockpit-wanted.patch` (qui branchait
`wanted` sur la table de groupe `minecraft_wanted`) — le prompt gère le cas où
ce patch a déjà été appliqué.

Copie tout le bloc ci-dessous dans une session Claude Code ouverte sur titisite :

---

Je veux étendre le flux « cockpit » du module Quêtes
(`GET /api/quests/cockpit/<token>.json`, construit par
`server/quests/cockpit.js` — lis `docs/quetes.md` section « Cockpit Minefield »)
et ajouter une page d'admin pour piloter ce que ce flux envoie. Le flux est
consommé par une app Python locale (MF Cockpit) : le contrat JSON attendu est
donné au point 6, respecte-le exactement (le cockpit tolère les champs
absents, mais pas les renommages).

## 1. Enrichir les quêtes du flux

Pour chaque quête renvoyée dans `available.journaliere|hebdomadaire|mensuelle`
**et** dans `deadlines`, ajouter :

- `inputs` : les `quest_inputs` de la quête, triés par `ordre` —
  `{ kind, label, quantite, refCode, factionId, icon }` ;
- `rewards` : comme le fait déjà `rewardsBrief()` pour `available` —
  l'ajouter aussi aux quêtes de `deadlines` ;
- `mapPoints` : les `quest_map_points`, triés par `ordre` —
  `{ label, role, x, y, z }`.

## 2. Liste d'items perso (section `wanted` du flux)

La section `wanted` du flux ne doit **pas** lire la wishlist de groupe
`minecraft_wanted` (c'est un réglage perso, pas un truc d'équipe). Si une
version précédente l'a branchée dessus, remplace-la.

Nouvelle table `cockpit_items`, **par utilisateur** :
`id, user_id (FK users, CASCADE), name, quantity (défaut 1), priority
(1 haute / 2 moyenne / 3 basse, défaut 2), note (défaut ''), workspace_id
(FK workspaces, optionnel, SET NULL — pour rattacher l'item à un projet),
x, y, z (INTEGER optionnels — coordonnées en jeu), done (défaut 0), done_at,
position, created_at, updated_at`. Migration via `migrate()` dans
`server/db.js` (même style `CREATE TABLE IF NOT EXISTS` + index que le reste).

Le flux renvoie les items **non faits** du membre du token, triés par
`priority` puis `position` :
`{ id, name, quantity, priority, note, workspace (nom du projet lié, sinon
null), x, y, z }`, plus `counts.wanted`. Comme les autres listes
actionnables, `wanted` est vidé si `wants_quest_reminders = 0`.

## 3. Choisir les quêtes envoyées au cockpit

Table `cockpit_quest_follows (user_id, quest_id, UNIQUE)`. Comportement :

- l'utilisateur n'a **aucune** ligne → le flux envoie toutes les quêtes
  (comportement actuel, rien ne casse) ;
- il suit au moins une quête → seules les quêtes suivies apparaissent dans
  `available` et `deadlines` (les gains `potentialGains` restent globaux).

## 4. Page d'admin « Cockpit »

Nouvel onglet « Cockpit » dans l'admin du site. Chaque utilisateur y voit et
gère **uniquement ses propres** réglages (ce n'est pas une gestion de groupe) ;
accès pour tout membre ayant `can_view_quests`. Contenu :

- l'URL secrète du flux (réutilise `GET /api/me/cockpit-token`) avec boutons
  copier et régénérer, et l'interrupteur des rappels
  (`PUT /api/me/quest-reminders`) ;
- la gestion des **items perso** : ajouter / éditer / supprimer / cocher fait,
  avec nom, quantité, priorité, note, projet lié (select des workspaces dont
  je suis membre), coordonnées x/y/z optionnelles ;
- la liste des **quêtes** (groupées par occurrence, avec faction) avec un
  interrupteur « envoyer au cockpit » par quête + un état clair du mode
  (« tout est envoyé » tant qu'aucune quête n'est suivie) ;
- un **aperçu du flux** : fetch de l'endpoint avec mon token et affichage du
  JSON, pour vérifier ce que le cockpit va recevoir.

## 5. API

Sous `/api/me/cockpit/…` (session cookie, chaque utilisateur ne touche qu'à
ses données — jamais d'id utilisateur pris du client) :

- CRUD des items (`GET/POST/PUT/DELETE /items[/:id]`,
  `PATCH /items/:id/done`) ;
- quêtes suivies (`GET /quests` → liste + état follow,
  `PUT /quests/:id/follow { followed: bool }`).

Validation serveur comme le reste du module (enums, quantités, longueurs),
erreurs `{ error: 'code' }`.

## 6. Contrat JSON du flux (consommé par le cockpit)

```json
{
  "member": { "id": 1, "name": "…" },
  "generatedAt": 1751700000,
  "remindersEnabled": true,
  "available": {
    "journaliere": [
      {
        "id": 1, "titre": "Livrer 16 pains", "faction": "Bourg",
        "factionCouleur": "#a78bfa", "periodKey": "d:2026-07-06",
        "nextResetAt": 1751780000,
        "inputs":  [ { "kind": "item", "label": "Pain", "quantite": 16, "refCode": null, "factionId": null, "icon": null } ],
        "rewards": [ { "kind": "pa", "label": "", "quantite": 50, "refCode": null, "factionId": null } ],
        "mapPoints": [ { "label": "boulangerie", "role": "rendu", "x": 128, "y": 64, "z": -342 } ]
      }
    ],
    "hebdomadaire": [], "mensuelle": []
  },
  "deadlines": [
    { "id": 7, "titre": "…", "faction": "…", "dueDate": 1751780000,
      "inputs": [ … ], "rewards": [ … ], "mapPoints": [ … ] }
  ],
  "wanted": [
    { "id": 3, "name": "Diamant", "quantity": 64, "priority": 1,
      "note": "pour la beacon", "workspace": "Base principale",
      "x": -1204, "y": 11, "z": 356 }
  ],
  "counts": { "availableTotal": 1, "deadlines": 1, "wanted": 1 },
  "potentialGains": { … inchangé … }
}
```

## 7. Qualité

- Tests `node --test` dans le style de `test/quests.test.js` : flux enrichi
  (inputs/rewards/mapPoints présents), items perso dans `wanted` (done exclu,
  opt-out vide la liste), filtre follow (aucune ligne = tout, sinon
  seulement les suivies), isolation entre utilisateurs (un membre ne voit ni
  ne modifie les items d'un autre).
- Mets à jour `docs/quetes.md` (section cockpit : nouveau JSON + page admin).
- `npm test` et `npm run lint:security` doivent passer.
