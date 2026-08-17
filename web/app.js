/* MF Cockpit — application mobile (iPhone / Safari).
 *
 * Trois partis pris qui expliquent tout le reste du fichier :
 *
 * 1. HTTP simple, donc **pas de service worker** (impossible sans HTTPS). Tout
 *    ce qui est nécessaire hors ligne est copié dans `localStorage` par
 *    « Préparer la salle ». L'app tourne intégralement hors réseau tant que
 *    l'onglet reste ouvert — d'où le bandeau qui le rappelle.
 *
 * 2. **Les chronos sont des horodatages, jamais des ticks.** iOS gèle les
 *    `setInterval` dès que l'écran se verrouille : on stocke l'instant de fin
 *    et on recalcule l'affichage à chaque frame et à chaque `visibilitychange`.
 *    Au retour, le temps affiché est juste — et si le repos s'est terminé
 *    pendant le gel, on le dit.
 *
 * 3. **Pas de vibration** : l'API n'existe pas sur Safari iOS. Le signal de fin
 *    de repos est sonore (oscillateur Web Audio, aucun fichier) + un flash vert
 *    plein écran. Le bip est *programmé* sur l'horloge audio, qui continue de
 *    tourner écran verrouillé : il sonne même quand le JS est gelé.
 */
'use strict';

/* ------------------------------------------------------------- outils */
const $ = (id) => document.getElementById(id);
const jeton = new URLSearchParams(location.search).get('t') || '';
const uid = () => (crypto.randomUUID ? crypto.randomUUID()
  : 'x-' + Date.now() + '-' + Math.random().toString(16).slice(2));

const mmss = (s) => {
  s = Math.max(0, Math.round(s));
  const m = Math.floor(s / 60);
  return String(m).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
};

const LS = {
  get(cle, defaut) {
    try { const v = localStorage.getItem(cle); return v ? JSON.parse(v) : defaut; }
    catch (e) { return defaut; }
  },
  set(cle, val) {
    try { localStorage.setItem(cle, JSON.stringify(val)); return true; }
    catch (e) { return false; }   // quota plein : on continue sans cache
  },
  del(cle) { try { localStorage.removeItem(cle); } catch (e) { /* rien */ } },
};

const K = {
  bundle: 'mfc.bundle', file: 'mfc.file', media: 'mfc.media',
  prep: 'mfc.prep', reglages: 'mfc.reglages', session: 'mfc.session',
};

/* --------------------------------------------------------------- état */
const S = {
  bundle: LS.get(K.bundle, null),
  file: LS.get(K.file, []),
  media: LS.get(K.media, {}),
  prep: LS.get(K.prep, null),
  reglages: Object.assign(
    { effort: 45, repos: 15, tours: 8, saisieLibre: false }, LS.get(K.reglages, {})),
  session: LS.get(K.session, null),
  jour: null,
  enLigne: false,
  ecran: 'accueil',
};

function sauverFile() { LS.set(K.file, S.file); majFile(); }
function sauverSession() { LS.set(K.session, S.session); }

/* ------------------------------------------------------------ réseau */
async function api(chemin, options) {
  const sep = chemin.includes('?') ? '&' : '?';
  const r = await fetch(chemin + sep + 't=' + encodeURIComponent(jeton),
    Object.assign({ cache: 'no-store' }, options || {}));
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}

/** Empile une opération pour le serveur. Elle part maintenant si le wifi est
 *  là, sinon elle attend dans la file — et l'`uuid` garantit qu'un rejeu ne
 *  duplique rien côté base. */
function pousser(table, payload) {
  const op = { uuid: uid(), table, ts: Math.floor(Date.now() / 1000), payload };
  op.payload.uuid = op.uuid;
  S.file.push(op);
  sauverFile();
  if (S.enLigne) synchroniser(true);
  return op;
}

let syncEnCours = false;
async function synchroniser(silencieux) {
  if (syncEnCours) return;
  syncEnCours = true;
  try {
    const aEnvoyer = S.file.slice();
    if (aEnvoyer.length) {
      const rep = await api('/api/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ops: aEnvoyer, device: 'tel' }),
      });
      // Le serveur a tout absorbé (appliqué ou déjà connu) : on purge.
      const envoyes = new Set(aEnvoyer.map((o) => o.uuid));
      S.file = S.file.filter((o) => !envoyes.has(o.uuid));
      sauverFile();
      const n = rep.appliquees || 0;
      if (n) bandeau('b-sync', `✓ ${n} opération${n > 1 ? 's' : ''} synchronisée${n > 1 ? 's' : ''}.`, 4000);
    }
    await rafraichirJour();
    S.enLigne = true;
    if (!silencieux && !S.file.length) bandeau('b-sync', '✓ À jour.', 2500);
  } catch (e) {
    S.enLigne = false;
    if (!silencieux) bandeau('b-sync', '⚠️ Hors ligne — la file est conservée.', 4000, 'bandeau--rouge');
  } finally {
    syncEnCours = false;
    majFile();
  }
}

async function rafraichirJour() {
  const j = await api('/api/jour');
  S.jour = j;
  if (S.bundle) { S.bundle.jours[0] = j; LS.set(K.bundle, S.bundle); }
  rendreAccueil();
}

/** Garantit qu'on a un bundle en mémoire.
 *
 *  Les écrans Coréen et Sport en dépendent entièrement : sans lui, ils
 *  s'affichent vides. On ne peut pas exiger d'avoir appuyé sur « Préparer la
 *  salle » — on le récupère tout seul dès qu'il y a du réseau. Le bouton reste
 *  utile pour rafraîchir et mettre les **médias** en cache, ce qui est long.
 */
let bundleEnCours = null;
function assurerBundle() {
  if (S.bundle) return Promise.resolve(true);
  if (bundleEnCours) return bundleEnCours;
  bundleEnCours = api('/api/bundle').then((b) => {
    S.bundle = b;
    S.jour = b.jours[0];
    LS.set(K.bundle, b);
    S.enLigne = true;
    bundleEnCours = null;
    return true;
  }).catch(() => {
    bundleEnCours = null;
    return false;
  });
  return bundleEnCours;
}

/* --------------------------------------------------------- bandeaux */
const timersBandeau = {};
function bandeau(id, texte, ms, classe) {
  const el = $(id);
  if (!el) return;
  el.textContent = texte;
  el.className = 'bandeau' + (classe ? ' ' + classe : '');
  el.hidden = false;
  clearTimeout(timersBandeau[id]);
  if (ms) timersBandeau[id] = setTimeout(() => { el.hidden = true; }, ms);
}

/* ------------------------------------------------------------- audio */
const Son = {
  ctx: null, pret: false, silence: null, programmes: [],

  /** iOS n'autorise l'audio qu'après un geste : à appeler depuis un clic. */
  async debloquer() {
    try {
      if (!this.ctx) {
        const AC = window.AudioContext || window.webkitAudioContext;
        if (!AC) return false;
        this.ctx = new AC();
      }
      await this.ctx.resume();
      // Oscillateur muet permanent : garde le contexte vivant (donc les bips
      // programmés audibles) même écran verrouillé.
      if (!this.silence) {
        const o = this.ctx.createOscillator();
        const g = this.ctx.createGain();
        g.gain.value = 0.0001;
        o.connect(g).connect(this.ctx.destination);
        o.start();
        this.silence = o;
      }
      this.pret = this.ctx.state === 'running';
      majBoutonsSon();
      return this.pret;
    } catch (e) { return false; }
  },

  /** Bip à `dans` secondes sur l'horloge AUDIO (pas sur setTimeout). */
  bip(dans, freq, duree, volume) {
    if (!this.ctx || !this.pret) return null;
    const t = this.ctx.currentTime + Math.max(0, dans || 0);
    const o = this.ctx.createOscillator();
    const g = this.ctx.createGain();
    o.type = 'sine';
    o.frequency.value = freq || 880;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(volume || 0.32, t + 0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, t + (duree || 0.18));
    o.connect(g).connect(this.ctx.destination);
    o.start(t);
    o.stop(t + (duree || 0.18) + 0.05);
    this.programmes.push(o);
    return o;
  },

  /** Décompte 10 s puis 3-2-1 puis fanfare, tout programmé d'avance. */
  programmerFin(secondes) {
    this.annuler();
    if (!this.pret) return;
    if (secondes > 10) this.bip(secondes - 10, 660, 0.12, 0.22);
    for (let i = 3; i >= 1; i--) {
      if (secondes > i) this.bip(secondes - i, 740, 0.12, 0.26);
    }
    this.bip(secondes, 990, 0.30, 0.4);
    this.bip(secondes + 0.34, 1320, 0.34, 0.4);
  },

  annuler() {
    this.programmes.forEach((o) => { try { o.stop(); } catch (e) { /* déjà fini */ } });
    this.programmes = [];
  },

  dire(texte, lang) {
    try {
      if (!window.speechSynthesis) return;
      const u = new SpeechSynthesisUtterance(texte);
      u.lang = lang || 'fr-FR';
      const v = voixPour(u.lang);
      if (v) u.voice = v;
      speechSynthesis.speak(u);
    } catch (e) { /* pas de synthèse : tant pis */ }
  },
};

let voix = [];
function chargerVoix() { try { voix = speechSynthesis.getVoices() || []; } catch (e) { voix = []; } }
function voixPour(lang) {
  const p = (lang || '').slice(0, 2).toLowerCase();
  return voix.find((v) => (v.lang || '').toLowerCase().startsWith(p)) || null;
}
if (window.speechSynthesis) {
  chargerVoix();
  speechSynthesis.onvoiceschanged = () => { chargerVoix(); majVoixKR(); };
}
const voixCoreenne = () => !!voixPour('ko');

function majBoutonsSon() {
  ['s-son', 'c-son'].forEach((id) => {
    const b = $(id);
    if (b) { b.textContent = Son.pret ? '🔔' : '🔕'; b.classList.toggle('ico--off', !Son.pret); }
  });
  const e = $('r-etat-son');
  if (e) e.textContent = Son.pret ? 'Son débloqué ✓' : 'Son pas encore débloqué — appuie sur 🔔.';
}

/* ---------------------------------------------------- garder l'écran */
const Reveil = {
  verrou: null, video: null,
  async activer() {
    try {
      if (navigator.wakeLock && !this.verrou) {
        this.verrou = await navigator.wakeLock.request('screen');
        this.verrou.addEventListener('release', () => { this.verrou = null; });
        $('b-reveil').hidden = true;
        return 'api';
      }
    } catch (e) { /* refusé (HTTP simple) : on tente la vidéo */ }
    // Repli « NoSleep » : une micro-vidéo en boucle. Elle n'existe que si un
    // fichier a été déposé dans media/ — sinon on montre la note iOS.
    try {
      const v = $('nosleep');
      if (v && !v.src) v.src = '/api/media/nosleep.mp4';
      if (v) { await v.play(); return 'video'; }
    } catch (e) { /* pas de vidéo : note iOS */ }
    $('b-reveil').hidden = false;
    return 'note';
  },
  desactiver() {
    try { if (this.verrou) { this.verrou.release(); this.verrou = null; } } catch (e) { /* rien */ }
    try { $('nosleep').pause(); } catch (e) { /* rien */ }
    $('b-reveil').hidden = true;
  },
};

/* ------------------------------------------------------------ chrono */
const Chrono = {
  fin: 0, duree: 0, actif: false, type: null, onFin: null, fini: false,

  lancer(secondes, type, onFin) {
    this.duree = secondes;
    this.fin = Date.now() + secondes * 1000;
    this.actif = true; this.fini = false;
    this.type = type || 'repos'; this.onFin = onFin || null;
    Son.programmerFin(secondes);
  },
  ajuster(delta) {
    if (!this.actif) return;
    this.fin += delta * 1000;
    const reste = this.reste();
    if (reste <= 0) { this.fin = Date.now() + 1000; }
    Son.programmerFin(this.reste());
  },
  arreter() { this.actif = false; this.fini = false; this.fin = 0; Son.annuler(); },
  /** Toujours calculé sur l'horloge murale : juste après n'importe quel gel. */
  reste() { return this.actif ? (this.fin - Date.now()) / 1000 : 0; },
  depuis() { return this.actif ? (Date.now() - this.fin) / 1000 : 0; },
};

/** Boucle d'affichage : rAF quand l'onglet est visible, plus une remise à
 *  l'heure explicite au retour au premier plan. */
function boucle() {
  if (Chrono.actif) {
    const reste = Chrono.reste();
    if (reste <= 0 && !Chrono.fini) {
      Chrono.fini = true;
      montrerFlash();
      if (Chrono.onFin) Chrono.onFin();
    }
    peindreChrono(reste);
  }
  if (S.session && S.session.debut) {
    const el = $('s-chrono');
    if (el) el.textContent = mmss((Date.now() - S.session.debut) / 1000);
  }
  requestAnimationFrame(boucle);
}

function peindreChrono(reste) {
  const aff = $('c-affiche');
  const sous = $('c-sous');
  if (!aff) return;
  if (reste > 0) {
    aff.textContent = mmss(reste);
    aff.classList.remove('fini');
    if (sous && Chrono.type === 'interval') sous.textContent = etiquetteInterval();
  } else {
    aff.textContent = '00:00';
    aff.classList.add('fini');
    // Le repos s'est peut-être terminé pendant que l'écran était verrouillé :
    // on affiche depuis combien de temps, plutôt qu'un zéro muet.
    if (sous) sous.textContent = `Terminé depuis ${Math.round(Chrono.depuis())} s`;
  }
}

function montrerFlash() {
  const f = $('flash');
  $('flash-txt').textContent = Chrono.type === 'iso' ? 'FINI' : 'REPOS TERMINÉ';
  f.hidden = false;
}
$('flash-ok').onclick = () => {
  $('flash').hidden = true;
  if (Chrono.type !== 'interval') Chrono.arreter();
};

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState !== 'visible') return;
  if (Chrono.actif) peindreChrono(Chrono.reste());          // remise à l'heure
  if (S.enLigne || navigator.onLine) synchroniser(true);
});

/* =====================================================================
 *  ACCUEIL
 * ===================================================================*/
/** Empreinte de tout ce que l'accueil affiche : si elle n'a pas bougé, on ne
 *  touche pas au DOM. Sans ça, le ping de synchro toutes les 30 s reconstruit
 *  les listes de tâches et la page semble se relancer toute seule. */
function signatureAccueil(j) {
  const seance = (s) => s && [s.nom, s.statut, s.faits, s.total, s.version_courte,
    (s.exos || []).map((e) => [e.tache_id, e.fait, e.cible, e.charge_proposee])];
  return JSON.stringify([
    j.date, j.libelle, j.semaine_programme, j.allegee, j.reprise,
    j.streaks, j.valide, j.conseils,
    (j.seances || []).map(seance), seance(j.core), seance(j.cardio),
    j.coreen && [j.coreen.semaine, j.coreen.theme, j.coreen.cartes_dues,
                 j.coreen.checklist],
    S.file.length, S.enLigne, S.prep && S.prep.ts,
  ]);
}

let sigAccueil = null;

function rendreAccueil(force) {
  const j = S.jour || (S.bundle && S.bundle.jours && S.bundle.jours[0]);
  if (!j) return;
  const sig = signatureAccueil(j);
  if (!force && sig === sigAccueil) return;      // rien n'a bougé : on ne redessine pas
  sigAccueil = sig;
  $('a-date').textContent = j.libelle || j.date;
  $('a-semaine').textContent =
    `Semaine ${j.semaine_programme} du programme` +
    (j.allegee ? ' · allégée' : '') + (j.reprise ? ' · reprise' : '');

  const st = j.streaks || {};
  $('a-streak-sport').textContent = '🔥 ' + ((st.sport && st.sport.courant) || 0) + ' j';
  $('a-streak-sport-r').textContent = 'record ' + ((st.sport && st.sport.record) || 0);
  $('a-streak-kr').textContent = '🔥 ' + ((st.coreen && st.coreen.courant) || 0) + ' j';
  $('a-streak-kr-r').textContent = 'record ' + ((st.coreen && st.coreen.record) || 0);

  $('a-conseils').innerHTML = (j.conseils || []).map((c) =>
    `<div class="carte"><div class="meta${c.niveau === 'medical' ? ' meta--rouge' : ''}">${echap(c.texte)}</div></div>`
  ).join('');

  // --- séance principale ---
  const s = (j.seances || [])[0];
  const carteS = $('a-carte-seance');
  if (s) {
    carteS.hidden = false;
    $('a-seance-nom').textContent = s.nom;
    $('a-seance-meta').innerHTML =
      `<b>${echap(s.lieu)}</b> · ${s.duree_cible_min} min · ${s.faits}/${s.total} exercices`
      + (s.statut === 'manque' ? ' · <b>manquée</b>' : '')
      + (s.contacts_plyo ? `<br>Plyo : ${echap(s.plyo_libelle)} — ${s.contacts_plyo}/${s.contacts_max} contacts` : '');
    $('a-seance-barre').style.width = (s.total ? (100 * s.faits / s.total) : 0) + '%';
    $('a-go-seance').onclick = () => ouvrirSeance(s);
    $('a-manquee').onclick = () => {
      if (!s.seance_id) return;
      pousser('seance', { seance_id: s.seance_id, statut: 'manque' });
      s.statut = 'manque';
      bandeau('b-sync', 'Séance marquée manquée. Elle ne sera pas replanifiée.', 4000, 'bandeau--warn');
      rendreAccueil();
    };
  } else { carteS.hidden = true; }

  // --- bloc core ---
  const c = j.core;
  const carteC = $('a-carte-core');
  if (c) {
    carteC.hidden = false;
    $('a-core-nom').textContent = c.nom;
    $('a-core-meta').innerHTML = `${c.duree_cible_min} min · ${c.faits}/${c.total}`
      + (c.version_courte ? ' · <b>version courte</b> (grosse journée)' : '');
    rendreTaches($('a-core-liste'), c.exos.map((e) => ({
      id: e.tache_id, fait: e.fait, libelle: `${e.nom} — ${e.cible}` + (e.note ? ` (${e.note})` : ''),
    })), () => rendreAccueil());
    if (!$('a-go-core')) {
      const b = document.createElement('button');
      b.id = 'a-go-core'; b.className = 'gros gros--primaire';
      b.textContent = '▶ Dérouler le bloc';
      carteC.appendChild(b);
    }
    $('a-go-core').onclick = () => ouvrirSeance(c);
  } else { carteC.hidden = true; }

  // --- cardio ---
  const cd = j.cardio;
  const carteCd = $('a-carte-cardio');
  if (cd) {
    carteCd.hidden = false;
    $('a-cardio-meta').innerHTML = `<b>${echap(cd.nom)}</b> · ${echap(cd.plan_course || '')}`;
  } else { carteCd.hidden = true; }

  // --- coréen ---
  const kr = j.coreen || {};
  $('a-kr-meta').innerHTML =
    `Semaine ${kr.semaine || '—'} · <b>${echap(kr.theme || '')}</b><br>${kr.cartes_dues || 0} cartes dues`;
  rendreTaches($('a-kr-liste'), (kr.checklist || []).map((t) => ({
    id: t.id, fait: t.fait, libelle: t.libelle,
  })), () => rendreAccueil());

  majPrep();
  majFile();
}

function rendreTaches(ul, taches, apres) {
  ul.innerHTML = '';
  taches.forEach((t) => {
    const li = document.createElement('li');
    li.className = t.fait ? 'fait' : '';
    li.innerHTML = `<span class="case">✓</span><span>${echap(t.libelle)}</span>`;
    li.onclick = () => {
      if (!t.id) return;
      t.fait = !t.fait;
      li.classList.toggle('fait', t.fait);
      pousser('tache_jour', { id: t.id, fait: t.fait });
      majEtatLocal(t.id, t.fait);
      if (apres) apres();
    };
    ul.appendChild(li);
  });
}

/** Répercute le coche dans la copie locale : hors ligne, l'écran doit rester
 *  juste sans attendre le serveur. */
function majEtatLocal(tacheId, fait) {
  const j = S.jour;
  if (!j) return;
  const groupes = [].concat(j.seances || [], j.core ? [j.core] : [], j.cardio ? [j.cardio] : []);
  groupes.forEach((g) => {
    (g.exos || []).forEach((e) => { if (e.tache_id === tacheId) e.fait = fait; });
    g.faits = (g.exos || []).filter((e) => e.fait).length;
  });
  ((j.coreen || {}).checklist || []).forEach((t) => { if (t.id === tacheId) t.fait = fait; });
}

function majFile() {
  const n = S.file.length;
  const el = $('a-file');
  if (el) {
    el.textContent = n ? `${n} opération${n > 1 ? 's' : ''} en attente d'envoi.`
      : (S.enLigne ? 'Tout est synchronisé.' : 'Rien en attente.');
    el.className = 'meta' + (n ? ' meta--rouge' : '');
  }
}

function majPrep() {
  const el = $('a-prep-etat');
  if (!S.prep) { el.textContent = 'Jamais préparé — appuie avant de partir à la salle.'; el.className = 'meta meta--rouge'; return; }
  const jours = Math.floor((Date.now() - S.prep.ts) / 86400000);
  const restants = Math.max(0, (S.prep.jours || 0) - jours);
  el.innerHTML = `Préparé il y a <b>${jours} j</b> · prêt pour <b>${restants} jour${restants > 1 ? 's' : ''}</b>`
    + ` · ${S.prep.medias || 0} médias en cache`;
  el.className = 'meta' + (jours > 3 ? ' meta--rouge' : '');
  $('b-cache').hidden = false;
}

$('a-preparer').onclick = async () => {
  const b = $('a-preparer');
  b.disabled = true; b.textContent = '⬇ Téléchargement…';
  try {
    const bundle = await api('/api/bundle');
    S.bundle = bundle;
    S.jour = bundle.jours[0];
    LS.set(K.bundle, bundle);
    b.textContent = '⬇ Mise en cache des médias…';
    const medias = await cacherMedias(bundle);
    S.prep = { ts: Date.now(), jours: bundle.jours.length, version: bundle.version, medias };
    LS.set(K.prep, S.prep);
    S.enLigne = true;
    bandeau('b-sync', `✓ Prêt pour ${bundle.jours.length} jours, hors ligne.`, 5000);
    rendreAccueil();
  } catch (e) {
    bandeau('b-sync', '⚠️ Téléchargement impossible — es-tu bien sur le wifi ?', 5000, 'bandeau--rouge');
  } finally {
    b.disabled = false; b.textContent = '⬇ Préparer la salle';
  }
};

/** Met en base64 les médias des exos d'aujourd'hui et de demain seulement :
 *  au-delà, on ferait exploser le quota `localStorage`. */
async function cacherMedias(bundle) {
  const codes = new Set();
  (bundle.jours || []).slice(0, 2).forEach((j) => {
    [].concat(j.seances || [], j.core ? [j.core] : [], j.cardio ? [j.cardio] : [])
      .forEach((s) => (s.exos || []).forEach((e) => codes.add(e.code)));
  });
  const parCode = {};
  (bundle.exercices || []).forEach((e) => { parCode[e.code] = e; });
  const cache = {};
  let n = 0;
  for (const code of codes) {
    const exo = parCode[code];
    if (!exo || !exo.media) continue;
    try {
      const r = await fetch(exo.media + '?t=' + encodeURIComponent(jeton), { cache: 'no-store' });
      if (!r.ok) continue;
      const blob = await r.blob();
      if (blob.size > 220000) continue;            // trop gros pour le quota
      cache[code] = await new Promise((res, rej) => {
        const fr = new FileReader();
        fr.onload = () => res(fr.result);
        fr.onerror = rej;
        fr.readAsDataURL(blob);
      });
      n++;
    } catch (e) { /* un média manquant n'empêche pas la séance */ }
  }
  S.media = cache;
  if (!LS.set(K.media, cache)) bandeau('b-sync', '⚠️ Cache média partiel (mémoire pleine).', 4000, 'bandeau--warn');
  return n;
}

$('a-sync').onclick = () => synchroniser(false);

$('a-cardio-ok').onclick = () => {
  const km = parseFloat($('a-cardio-km').value || '0');
  const min = parseFloat($('a-cardio-min').value || '0');
  if (!km && !min) return;
  pousser('cardio', {
    date: (S.jour || {}).date, type: 'course',
    distance_km: km || null, duree_s: Math.round(min * 60) || null,
  });
  bandeau('b-sync', '✓ Sortie enregistrée.', 3000);
};

$('a-foot-ok').onclick = () => {
  const min = parseFloat($('a-foot-min').value || '0');
  pousser('cardio', {
    date: (S.jour || {}).date, type: 'foot_salle',
    duree_s: Math.round(min * 60) || null,
    ressenti: parseInt($('a-foot-res').value || '7', 10),
  });
  bandeau('b-sync', '✓ Foot en salle enregistré.', 3000);
};

/* =====================================================================
 *  SÉANCE
 * ===================================================================*/
function ouvrirSeance(seance) {
  const memeSeance = S.session && S.session.seance_id === seance.seance_id;
  if (!memeSeance) {
    S.session = {
      seance_id: seance.seance_id,
      nom: seance.nom,
      debut: Date.now(),
      index: 0,
      exos: (seance.exos || []).map((e) => ({
        code: e.code, exercice_id: e.exercice_id, nom: e.nom, cible: e.cible,
        unite: e.unite, series: e.series, reps_min: e.reps_min, reps_max: e.reps_max,
        repos_sec: e.repos_sec || 90, charge: e.charge_proposee, variante: e.variante,
        consignes: e.consignes, erreurs: e.erreurs_frequentes, note: e.note,
        conseil: e.conseil, chargeable: e.chargeable, tache_id: e.tache_id,
        fait: e.fait, journal: [],
      })),
    };
    if (seance.seance_id) pousser('seance', { seance_id: seance.seance_id, statut: 'en_cours' });
  }
  sauverSession();
  Reveil.activer();
  aller('seance');
  rendreExo();
}

function exoCourant() {
  if (!S.session) return null;
  return S.session.exos[S.session.index] || null;
}

function rendreExo() {
  const s = S.session;
  const e = exoCourant();
  if (!s || !e) { aller('accueil'); return; }

  $('s-pos').textContent = `${s.index + 1} / ${s.exos.length}`;
  $('s-nom').textContent = e.nom;
  $('s-cible').textContent = e.cible + (e.note ? ` · ${e.note}` : '');
  $('s-conseil').textContent = e.conseil || '';
  $('s-consignes').textContent = e.consignes || '';
  $('s-erreurs').textContent = e.erreurs ? '⚠ ' + e.erreurs : '';

  const charge = [];
  if (e.charge) charge.push(`Charge proposée <em>${e.charge} kg</em>`);
  if (e.variante) charge.push(`Variante : <em>${echap(e.variante)}</em>`);
  $('s-charge').innerHTML = charge.join(' · ');

  const img = $('s-media');
  const src = S.media[e.code];
  if (src) { img.src = src; img.hidden = false; } else { img.hidden = true; img.removeAttribute('src'); }

  // grille de séries
  const grille = $('s-series');
  grille.innerHTML = '';
  for (let i = 1; i <= (e.series || 1); i++) {
    const faite = e.journal.find((x) => x.index === i);
    const b = document.createElement('button');
    b.className = 'serie' + (faite ? ' faite' : '');
    b.innerHTML = faite
      ? `<small>SÉRIE ${i}</small><b>${faite.reps ?? '—'}</b><small>${faite.charge ? faite.charge + ' kg' : (e.unite === 'secondes' ? 's' : '')}</small>`
      : `<small>SÉRIE ${i}</small><b>—</b><small>${e.reps_min ? viseur(e) : ''}</small>`;
    b.onclick = () => ouvrirModaleSerie(i);
    grille.appendChild(b);
  }

  const total = s.exos.reduce((a, x) => a + (x.series || 1), 0);
  const faits = s.exos.reduce((a, x) => a + x.journal.length, 0);
  $('s-barre').style.width = (total ? 100 * faits / total : 0) + '%';
}

function viseur(e) {
  if (!e.reps_min) return '';
  const u = e.unite === 'secondes' ? ' s' : '';
  return e.reps_max && e.reps_max !== e.reps_min ? `${e.reps_min}-${e.reps_max}${u}` : `${e.reps_min}${u}`;
}

/* ---- modale de saisie ---- */
let M = { index: 1, reps: 10, charge: 0, rpe: 8, pas: 2.5 };

function ouvrirModaleSerie(index) {
  const e = exoCourant();
  const deja = e.journal.find((x) => x.index === index);
  M.index = index;
  M.reps = deja ? (deja.reps ?? e.reps_min ?? 10) : (e.reps_min || 10);
  M.charge = deja ? (deja.charge ?? e.charge ?? 0) : (e.charge || 0);
  M.rpe = deja ? deja.rpe : 8;
  $('m-titre').textContent = `${e.nom} — série ${index}`;
  $('m-unite').textContent = e.unite === 'secondes' ? 'secondes' : (e.unite === 'contacts' ? 'contacts' : 'reps');
  $('m-bloc-charge').hidden = !e.chargeable;
  $('m-pas-choix').hidden = !e.chargeable;
  peindreModale();
  $('m-serie').hidden = false;
}

function peindreModale() {
  $('m-reps').textContent = M.reps;
  // On affiche la charge telle qu'elle sera enregistrée : arrondir ici ferait
  // lire « 16 » pour une série à 15,5 kg.
  $('m-charge').textContent = String(Math.round(M.charge * 10) / 10);
  document.querySelectorAll('.rpe button').forEach((b) =>
    b.classList.toggle('on', parseInt(b.dataset.rpe, 10) === M.rpe));
  document.querySelectorAll('#m-pas-choix button').forEach((b) =>
    b.classList.toggle('on', parseFloat(b.dataset.pas) === M.pas));
}

document.querySelectorAll('.pas').forEach((b) => {
  b.onclick = () => {
    const d = parseInt(b.dataset.delta, 10);
    if (b.dataset.champ === 'reps') M.reps = Math.max(0, M.reps + d);
    else M.charge = Math.max(0, Math.round((M.charge + d * M.pas) * 100) / 100);
    peindreModale();
  };
});
document.querySelectorAll('#m-pas-choix button').forEach((b) => {
  b.onclick = () => { M.pas = parseFloat(b.dataset.pas); peindreModale(); };
});
document.querySelectorAll('.rpe button').forEach((b) => {
  b.onclick = () => { M.rpe = parseInt(b.dataset.rpe, 10); peindreModale(); };
});
$('m-annuler').onclick = () => { $('m-serie').hidden = true; };

$('m-valider').onclick = () => {
  const e = exoCourant();
  const s = S.session;
  const ligne = { index: M.index, reps: M.reps, charge: e.chargeable ? M.charge : null, rpe: M.rpe };
  e.journal = e.journal.filter((x) => x.index !== M.index).concat([ligne])
    .sort((a, b) => a.index - b.index);

  if (s.seance_id) {
    pousser('serie', {
      seance_id: s.seance_id, exercice_id: e.exercice_id, index_serie: M.index,
      reps: e.unite === 'secondes' ? null : M.reps,
      duree_s: e.unite === 'secondes' ? M.reps : null,
      charge_kg: e.chargeable ? M.charge : null,
      rpe: M.rpe, variante: e.variante || null,
      echec: M.rpe >= 10 ? 1 : 0,
    });
  }
  // Toutes les séries faites -> la tâche de l'exercice se coche toute seule.
  if (e.journal.length >= (e.series || 1) && !e.fait && e.tache_id) {
    e.fait = true;
    pousser('tache_jour', { id: e.tache_id, fait: true });
    majEtatLocal(e.tache_id, true);
  }
  sauverSession();
  $('m-serie').hidden = true;
  rendreExo();

  // Valider une série lance AUTOMATIQUEMENT le chrono de repos.
  Chrono.lancer(e.repos_sec || 90, 'repos');
  aller('chrono');
  peindreChrono(Chrono.reste());
};

/* ---- navigation entre exercices (boutons + swipe) ---- */
function bougerExo(delta) {
  const s = S.session;
  if (!s) return;
  s.index = Math.min(s.exos.length - 1, Math.max(0, s.index + delta));
  sauverSession();
  rendreExo();
}
$('s-prec').onclick = () => bougerExo(-1);
$('s-suiv').onclick = () => bougerExo(1);
$('s-retour').onclick = () => aller('accueil');
$('s-son').onclick = () => Son.debloquer();

(() => {
  const z = $('s-swipe');
  let x0 = null, y0 = null;
  z.addEventListener('touchstart', (ev) => {
    x0 = ev.touches[0].clientX; y0 = ev.touches[0].clientY;
  }, { passive: true });
  z.addEventListener('touchend', (ev) => {
    if (x0 === null) return;
    const dx = ev.changedTouches[0].clientX - x0;
    const dy = ev.changedTouches[0].clientY - y0;
    if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.6) bougerExo(dx < 0 ? 1 : -1);
    x0 = y0 = null;
  }, { passive: true });
})();

$('s-terminer').onclick = () => { rendreFin(); aller('fin'); };

/* =====================================================================
 *  CHRONO LIBRE
 * ===================================================================*/
let modeChrono = 'repos';
let interval = { tour: 0, phase: 'effort' };

function etiquetteInterval() {
  return `Tour ${interval.tour}/${S.reglages.tours} · ${interval.phase === 'effort' ? 'EFFORT' : 'transition'}`;
}

function rendreParamsChrono() {
  const p = $('c-params');
  if (modeChrono === 'interval') {
    p.innerHTML = `
      <label>Effort (s)<input type="number" inputmode="numeric" id="ci-effort" value="${S.reglages.effort}"></label>
      <label>Repos (s)<input type="number" inputmode="numeric" id="ci-repos" value="${S.reglages.repos}"></label>
      <label>Tours<input type="number" inputmode="numeric" id="ci-tours" value="${S.reglages.tours}"></label>`;
  } else {
    const d = modeChrono === 'iso' ? 40 : 90;
    p.innerHTML = `<label>Durée (s)<input type="number" inputmode="numeric" id="ci-duree" value="${d}"></label>`;
  }
}

document.querySelectorAll('#c-modes button').forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll('#c-modes button').forEach((x) => x.classList.remove('on'));
    b.classList.add('on');
    modeChrono = b.dataset.mode;
    Chrono.arreter();
    rendreParamsChrono();
    peindreChrono(0);
  };
});

$('c-go').onclick = async () => {
  await Son.debloquer();
  if (modeChrono === 'interval') {
    S.reglages.effort = parseInt(($('ci-effort') || {}).value || S.reglages.effort, 10);
    S.reglages.repos = parseInt(($('ci-repos') || {}).value || S.reglages.repos, 10);
    S.reglages.tours = parseInt(($('ci-tours') || {}).value || S.reglages.tours, 10);
    LS.set(K.reglages, S.reglages);
    interval = { tour: 1, phase: 'effort' };
    Chrono.lancer(S.reglages.effort, 'interval', phaseIntervalSuivante);
  } else {
    const d = parseInt(($('ci-duree') || {}).value || '90', 10);
    Chrono.lancer(d, modeChrono);
  }
  peindreChrono(Chrono.reste());
};

function phaseIntervalSuivante() {
  if (interval.phase === 'effort') {
    if (interval.tour >= S.reglages.tours) { Chrono.arreter(); return; }
    interval.phase = 'repos';
    Son.dire('suivant');
    setTimeout(() => {
      $('flash').hidden = true;
      Chrono.lancer(S.reglages.repos, 'interval', phaseIntervalSuivante);
    }, 700);
  } else {
    interval.phase = 'effort';
    interval.tour += 1;
    setTimeout(() => {
      $('flash').hidden = true;
      Chrono.lancer(S.reglages.effort, 'interval', phaseIntervalSuivante);
    }, 700);
  }
}

$('c-stop').onclick = () => { Chrono.arreter(); $('flash').hidden = true; peindreChrono(0); };
$('c-moins').onclick = () => { Chrono.ajuster(-30); peindreChrono(Chrono.reste()); };
$('c-plus').onclick = () => { Chrono.ajuster(30); peindreChrono(Chrono.reste()); };
$('c-retour').onclick = () => aller(S.session ? 'seance' : 'accueil');
$('c-son').onclick = () => Son.debloquer();

/* =====================================================================
 *  SPORT — ce qui arrive, et où j'en suis
 * ===================================================================*/
const JOURS_COURTS = ['lun', 'mar', 'mer', 'jeu', 'ven', 'sam', 'dim'];

function rendreSport() {
  if (!S.bundle) {
    $('sp-sous').textContent = 'Chargement…';
    assurerBundle().then((ok) => {
      if (ok && S.ecran === 'sport') rendreSport();
      else if (!ok) $('sp-sous').textContent = 'Hors ligne — cache vide.';
    });
    return;
  }
  const jours = S.bundle.jours || [];
  const auj = (S.jour && S.jour.date) || (jours[0] && jours[0].date);
  $('sp-sous').textContent =
    `Semaine ${(S.jour || jours[0] || {}).semaine_programme || '—'} du programme`;

  // --- bande des 7 jours ---
  const semaine = (S.jour && S.jour.semaine) || [];
  $('sp-semaine').innerHTML = semaine.map((c) => `
    <div class="jour${c.aujourdhui ? ' auj' : ''}">
      <small>${c.lettre}</small>
      <i class="${c.futur ? '' : c.sport}"></i>
      <i class="${c.futur ? '' : c.coreen}"></i>
    </div>`).join('');

  // --- prochaines séances (14 jours, celles qui ont vraiment du contenu) ---
  const lignes = [];
  jours.slice(0, 14).forEach((j) => {
    const seances = [].concat(j.seances || [], j.cardio ? [j.cardio] : []);
    seances.forEach((s) => {
      if (!s || !s.total) return;
      const dans = Math.round((new Date(j.date) - new Date(auj)) / 86400000);
      const quand = dans <= 0 ? "auj." : (dans === 1 ? 'dem.'
        : JOURS_COURTS[(new Date(j.date).getDay() + 6) % 7]);
      lignes.push(`
        <div class="seance-a-venir">
          <div class="quand${dans <= 0 ? ' auj' : ''}">${quand}</div>
          <div style="flex:1">
            <b>${echap(s.nom)}</b>
            <small>${echap(s.lieu || '')} · ${s.duree_cible_min} min ·
              ${s.total} exo${s.total > 1 ? 's' : ''}${
                s.statut === 'manque' ? ' · manquée'
                : (s.faits ? ` · ${s.faits} fait${s.faits > 1 ? 's' : ''}` : '')}</small>
          </div>
        </div>`);
    });
  });
  $('sp-prochaines').innerHTML = lignes.slice(0, 10).join('')
    || '<div class="meta">Rien de planifié.</div>';

  // --- charges du moment ---
  const charges = (S.bundle.exercices || [])
    .filter((e) => e.chargeable && e.derniere_charge)
    .sort((a, b) => b.derniere_charge - a.derniere_charge);
  $('sp-charges').innerHTML = charges.length
    ? charges.map((e) => `<div class="charge-exo"><span>${echap(e.nom)}</span>
        <b>${e.derniere_charge} kg</b></div>`).join('')
    : '<div class="meta">Aucune charge enregistrée — elle se remplit toute seule '
      + 'dès la première séance.</div>';

  // --- bilan de la semaine ---
  const faits = semaine.filter((c) => c.sport === 'fait').length;
  const partiels = semaine.filter((c) => c.sport === 'partiel').length;
  const manques = semaine.filter((c) => c.sport === 'manque').length;
  const st = (S.jour && S.jour.streaks) || {};
  $('sp-bilan').innerHTML = `
    <div class="bilan">
      <div><small>Jours validés</small><b>${faits}</b></div>
      <div><small>Partiels</small><b>${partiels}</b></div>
      <div><small>Manqués</small><b>${manques}</b></div>
      <div><small>Série sport</small><b>${(st.sport && st.sport.courant) || 0} j</b></div>
    </div>`;
}

$('sp-maj').onclick = () => {
  S.bundle = null;
  LS.del(K.bundle);
  rendreSport();
};

/* =====================================================================
 *  CORÉEN
 * ===================================================================*/
let KR = { file: [], courante: null, revelee: false, vue: 'cartes', qcm: null, debut: 0 };

function rendreCoreen() {
  const b = S.bundle && S.bundle.coreen;
  if (!b) {
    // Pas encore de bundle : on le récupère au lieu d'afficher un écran vide.
    $('k-titre').textContent = 'Coréen';
    $('k-sous').textContent = 'Chargement des cartes…';
    assurerBundle().then((ok) => {
      if (ok && S.ecran === 'coreen') rendreCoreen();
      else if (!ok) $('k-sous').textContent =
        'Hors ligne — appuie sur « Préparer la salle » quand le wifi revient.';
    });
    return;
  }
  const sem = b.semaine;
  $('k-titre').textContent = sem ? `S${sem.numero} · ${sem.theme}` : 'Coréen';
  $('k-sous').textContent = sem ? (sem.note_culture || '').slice(0, 90) : '';
  if (!KR.file.length) {
    KR.file = (b.cartes || []).filter((c) => c.due * 1000 <= Date.now());
  }
  majVoixKR();
  carteSuivante();
  rendreDialogues();
}

function majVoixKR() {
  const b = $('k-audio');
  if (b) b.classList.toggle('ico--off', !voixCoreenne());
  const r = $('r-voix');
  if (r) r.textContent = voixCoreenne()
    ? 'Voix coréenne détectée ✓ (la lecture 🔊 fonctionne).'
    : 'Aucune voix coréenne sur cet iPhone : Réglages → Accessibilité → Contenu énoncé → Voix → Coréen.';
}

function carteSuivante() {
  KR.courante = KR.file[0] || null;
  KR.revelee = false;
  KR.debut = Date.now();
  const c = KR.courante;
  $('k-file').textContent = `${KR.file.length} carte${KR.file.length > 1 ? 's' : ''} en file`;
  $('k-notes').hidden = true;
  $('k-reveler').hidden = false;
  $('k-verso').hidden = true;
  $('k-exemple').hidden = true;
  if (!c) {
    $('k-dir').textContent = '';
    $('k-recto').textContent = '✓';
    $('k-romaja').textContent = 'Rien à réviser pour l’instant.';
    $('k-reveler').hidden = true;
    return;
  }
  const versFr = c.direction === 'kr_fr';
  $('k-dir').textContent = versFr ? 'KR → FR' : 'FR → KR';
  $('k-recto').textContent = versFr ? c.kr : c.fr;
  $('k-romaja').textContent = '';
}

$('k-reveler').onclick = () => {
  const c = KR.courante;
  if (!c) return;
  KR.revelee = true;
  const versFr = c.direction === 'kr_fr';
  $('k-romaja').textContent = c.romaja || '';
  $('k-verso').textContent = versFr ? c.fr : c.kr;
  $('k-verso').hidden = false;
  if (c.exemple_kr) {
    $('k-exemple').innerHTML = `${echap(c.exemple_kr)}<br><small>${echap(c.exemple_fr || '')}</small>`;
    $('k-exemple').hidden = false;
  }
  $('k-reveler').hidden = true;
  $('k-notes').hidden = false;
};

function noter(su) {
  const c = KR.courante;
  if (!c) return;
  pousser('kr_revue', { carte_id: c.id, su: su ? 1 : 0, temps_ms: Date.now() - KR.debut });
  KR.file.shift();
  if (!su) KR.file.push(c);            // pas su : on la revoit en fin de file
  carteSuivante();
}
$('k-su').onclick = () => noter(true);
$('k-nonsu').onclick = () => noter(false);

$('k-audio').onclick = () => {
  const c = KR.courante;
  if (!c || !voixCoreenne()) return;
  Son.dire(KR.revelee || c.direction === 'kr_fr' ? c.kr : c.kr, 'ko-KR');
};

document.querySelectorAll('#k-modes button').forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll('#k-modes button').forEach((x) => x.classList.remove('on'));
    b.classList.add('on');
    KR.vue = b.dataset.vue;
    $('k-vue-cartes').hidden = KR.vue !== 'cartes';
    $('k-vue-exercice').hidden = KR.vue !== 'exercice';
    $('k-vue-dialogue').hidden = KR.vue !== 'dialogue';
    if (KR.vue === 'exercice') rendreExerciceKR();
  };
});

function exerciceDuJour() {
  const b = S.bundle && S.bundle.coreen;
  const j = S.jour || {};
  const voulu = (j.coreen && j.coreen.exercice) ? j.coreen.exercice.type : null;
  if (!b || !b.exercices || !b.exercices.length) return null;
  return b.exercices.find((e) => e.type === voulu) || b.exercices[0];
}

function rendreExerciceKR() {
  const exo = exerciceDuJour();
  const corps = $('k-exo-corps');
  if (!exo) { $('k-exo-titre').textContent = 'Prépare la salle pour charger les exercices.'; corps.innerHTML = ''; return; }
  $('k-exo-titre').textContent = exo.titre;
  const c = exo.contenu || {};

  if (exo.type === 'roleplay' && c.scenes) {
    corps.innerHTML = c.scenes.map((s, i) => `
      <div class="dialogue">
        <div class="ligne"><div class="kr">${echap(s.app)}</div>
        <div class="fr">${echap(s.app_fr || '')}</div></div>
        <div class="qcm">${(s.choix || []).map((ch) =>
          `<button data-bon="${ch === s.choix[0] ? 1 : 0}">${echap(ch)}</button>`).join('')}</div>
      </div>`).join('');
    brancherQcm(corps);
    return;
  }
  if (exo.type === 'trous' && c.phrases) {
    corps.innerHTML = c.phrases.map((p) => `
      <div class="dialogue"><div class="kr">${echap(p.phrase)}</div>
      <div class="fr">${echap(p.indice || '')}</div>
      <div class="qcm"><button data-bon="1">${echap(p.reponse)}</button></div></div>`).join('');
    brancherQcm(corps);
    return;
  }
  if (c.questions && c.questions.length) {
    const ecoute = exo.type === 'ecoute';
    corps.innerHTML = c.questions.map((q) => {
      const choix = melanger(q.choix.slice());
      return `<div class="dialogue">
        <div class="kr">${ecoute ? '🔊 (appuie pour écouter)' : echap(q.enonce)}</div>
        ${ecoute ? `<div class="fr" data-dire="${echap(q.enonce)}">appuie sur la ligne</div>`
                 : `<div class="fr">${echap(q.romaja || '')}</div>`}
        <div class="qcm">${choix.map((ch) =>
          `<button data-bon="${ch === q.bonne ? 1 : 0}">${echap(ch)}</button>`).join('')}</div></div>`;
    }).join('');
    brancherQcm(corps);
    corps.querySelectorAll('[data-dire]').forEach((el) => {
      el.onclick = () => Son.dire(el.dataset.dire, 'ko-KR');
    });
    return;
  }
  corps.innerHTML = '<div class="meta">Exercice à faire sur le PC.</div>';
}

function brancherQcm(racine) {
  racine.querySelectorAll('.qcm button').forEach((b) => {
    b.onclick = () => {
      const bon = b.dataset.bon === '1';
      b.classList.add(bon ? 'bon' : 'mauvais');
      if (bon) Son.bip(0, 880, 0.1, 0.2);
    };
  });
}

function rendreDialogues() {
  const b = S.bundle && S.bundle.coreen;
  const zone = $('k-dialogues');
  if (!b || !b.items) { zone.innerHTML = '<div class="meta">Prépare la salle.</div>'; return; }
  const dialogues = b.items.filter((i) => i.type === 'dialogue');
  zone.innerHTML = dialogues.map((d) => {
    const kr = (d.kr || '').split('\n');
    const fr = (d.fr || '').split('\n');
    return `<div class="dialogue"><div class="titre"><i class="losange"></i>${echap(d.exemple_kr || '')}</div>`
      + kr.map((l, i) => `<div class="ligne"><div class="kr">${echap(l)}</div>
         <div class="fr">${echap(fr[i] || '')}</div></div>`).join('')
      + '</div>';
  }).join('') || '<div class="meta">Pas de dialogue cette semaine.</div>';
  zone.querySelectorAll('.kr').forEach((el) => {
    el.onclick = () => Son.dire(el.textContent.replace(/^[^:]*:\s*/, ''), 'ko-KR');
  });
}

/* ---- pomodoro 20 min ---- */
let pomo = null;
$('k-pomodoro').onclick = async () => {
  await Son.debloquer();
  const el = $('k-pomo');
  if (pomo) { clearInterval(pomo); pomo = null; el.hidden = true; return; }
  const fin = Date.now() + 20 * 60000;
  el.hidden = false;
  Son.bip(20 * 60, 990, 0.4, 0.4);
  pomo = setInterval(() => {
    const r = (fin - Date.now()) / 1000;
    el.textContent = mmss(r);
    if (r <= 0) { clearInterval(pomo); pomo = null; el.textContent = 'Pause !'; }
  }, 250);
};
$('k-retour').onclick = () => aller('accueil');

/* =====================================================================
 *  FIN DE SÉANCE
 * ===================================================================*/
function rendreFin() {
  const s = S.session;
  if (!s) { aller('accueil'); return; }
  const duree = (Date.now() - s.debut) / 1000;
  let volume = 0, series = 0;
  s.exos.forEach((e) => e.journal.forEach((l) => {
    series++;
    volume += (l.charge || 0) * (l.reps || 0);
  }));
  $('f-bilan').innerHTML = `
    <div><small>Durée</small><b>${mmss(duree)}</b></div>
    <div><small>Séries</small><b>${series}</b></div>
    <div><small>Volume</small><b>${Math.round(volume)}</b></div>
    <div><small>Exercices</small><b>${s.exos.filter((e) => e.journal.length).length}/${s.exos.length}</b></div>`;
  $('f-records').innerHTML = '';
}

['genou', 'hanche', 'rpe'].forEach((c) => {
  const i = $('f-' + c);
  i.oninput = () => { $('f-' + c + '-v').textContent = i.value; };
});

$('f-terminer').onclick = () => {
  const s = S.session;
  if (!s) return;
  const duree = Math.round((Date.now() - s.debut) / 1000);
  if (s.seance_id) {
    pousser('seance', {
      seance_id: s.seance_id, statut: 'fait', duree_s: duree,
      rpe: parseInt($('f-rpe').value, 10),
      douleur_genou: parseInt($('f-genou').value, 10),
      douleur_hanche: parseInt($('f-hanche').value, 10),
      note: $('f-note').value || null,
    });
  }
  S.session = null;
  LS.del(K.session);
  Reveil.desactiver();
  Chrono.arreter();
  bandeau('b-sync', S.enLigne ? '✓ Séance envoyée.' : '✓ Séance enregistrée — elle partira au retour du wifi.', 5000);
  synchroniser(true);
  aller('accueil');
};

/** Filet de sécurité : si le cache saute, tout le détail est dans le presse-papier. */
$('f-copier').onclick = async () => {
  const s = S.session;
  if (!s) return;
  const lignes = [`MF Cockpit — ${s.nom}`, new Date(s.debut).toLocaleString('fr-FR'), ''];
  s.exos.forEach((e) => {
    if (!e.journal.length) return;
    lignes.push(e.nom + (e.variante ? ` (${e.variante})` : ''));
    e.journal.forEach((l) => lignes.push(
      `  #${l.index} ${l.reps ?? '—'}${e.unite === 'secondes' ? ' s' : ' reps'}`
      + (l.charge ? ` · ${l.charge} kg` : '') + ` · RPE ${l.rpe}`));
  });
  lignes.push('', `Genou ${$('f-genou').value}/10 · Hanche ${$('f-hanche').value}/10 · RPE ${$('f-rpe').value}`);
  const texte = lignes.join('\n');
  try {
    await navigator.clipboard.writeText(texte);
    bandeau('b-sync', '✓ Résumé copié dans le presse-papier.', 3000);
  } catch (e) {
    // Safari refuse parfois l'accès : on montre le texte, l'utilisateur copie à la main.
    prompt('Copie ce résumé :', texte);
  }
};
$('f-retour').onclick = () => aller('seance');

/* =====================================================================
 *  RÉGLAGES
 * ===================================================================*/
$('a-reglages').onclick = () => { rendreReglages(); aller('reglages'); };
$('r-retour').onclick = () => aller('accueil');
$('r-test-son').onclick = async () => { await Son.debloquer(); Son.bip(0, 990, 0.25, 0.35); };
$('r-vider').onclick = () => {
  if (!confirm('Vider le cache local ? La file d’envoi est conservée.')) return;
  [K.bundle, K.media, K.prep, K.session].forEach(LS.del);
  S.bundle = null; S.media = {}; S.prep = null; S.session = null;
  bandeau('b-sync', 'Cache vidé.', 3000, 'bandeau--warn');
  rendreReglages();
};
$('r-saisie-libre').onchange = (ev) => {
  S.reglages.saisieLibre = ev.target.checked;
  LS.set(K.reglages, S.reglages);
};
['effort', 'repos', 'tours'].forEach((c) => {
  const i = $('r-int-' + c);
  i.onchange = () => {
    S.reglages[c] = parseInt(i.value, 10) || S.reglages[c];
    LS.set(K.reglages, S.reglages);
  };
});

function rendreReglages() {
  $('r-saisie-libre').checked = !!S.reglages.saisieLibre;
  $('r-int-effort').value = S.reglages.effort;
  $('r-int-repos').value = S.reglages.repos;
  $('r-int-tours').value = S.reglages.tours;
  const octets = JSON.stringify(S.bundle || {}).length + JSON.stringify(S.media || {}).length;
  $('r-cache').textContent = S.bundle
    ? `Bundle version ${S.bundle.version} · ${Object.keys(S.media).length} médias · ~${Math.round(octets / 1024)} Ko`
    : 'Aucun cache — appuie sur « Préparer la salle ».';
  $('r-nosleep').textContent = navigator.wakeLock
    ? 'Cet appareil gère le verrou d’écran automatiquement.'
    : 'Verrou d’écran automatique indisponible en HTTP : utilise le réglage iOS ci-dessus.';
  majBoutonsSon();
  majVoixKR();
}

/* =====================================================================
 *  NAVIGATION
 * ===================================================================*/
const ECRANS = ['accueil', 'seance', 'sport', 'chrono', 'coreen', 'fin', 'reglages'];
function aller(nom) {
  S.ecran = nom;
  ECRANS.forEach((e) => { $('e-' + e).hidden = (e !== nom); });
  document.querySelectorAll('#nav button').forEach((b) =>
    b.classList.toggle('on', b.dataset.ecran === nom));
  if (nom === 'coreen') rendreCoreen();
  if (nom === 'sport') rendreSport();
  if (nom === 'chrono') { rendreParamsChrono(); peindreChrono(Chrono.reste()); }
  if (nom === 'seance') rendreExo();
  window.scrollTo(0, 0);
}
document.querySelectorAll('#nav button').forEach((b) => {
  b.onclick = () => {
    if (b.dataset.ecran === 'seance' && !S.session) {
      const j = S.jour || {};
      const s = (j.seances || [])[0] || j.core;
      if (s) { ouvrirSeance(s); return; }
    }
    aller(b.dataset.ecran);
  };
});

function echap(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
function melanger(t) {
  for (let i = t.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [t[i], t[j]] = [t[j], t[i]];
  }
  return t;
}

/* =====================================================================
 *  DÉMARRAGE
 * ===================================================================*/
(function demarrer() {
  if (S.bundle && S.bundle.jours) S.jour = S.bundle.jours[0];
  if (S.session) { $('b-cache').hidden = false; Reveil.activer(); }
  rendreAccueil();
  rendreParamsChrono();
  requestAnimationFrame(boucle);
  synchroniser(true);
  // Premier lancement : on remplit le cache tout seul pour que les écrans
  // Sport et Coréen ne soient jamais vides. Les médias, eux, restent derrière
  // « Préparer la salle » — c'est ce qui prend du temps et de la place.
  assurerBundle().then((ok) => { if (ok) rendreAccueil(true); });
  // Ping régulier quand la page est visible : détecte le retour du wifi,
  // vide la file, puis récupère un bundle frais.
  setInterval(() => {
    if (document.visibilityState === 'visible') synchroniser(true);
  }, 30000);
  window.addEventListener('online', () => synchroniser(true));
  window.addEventListener('offline', () => { S.enLigne = false; majFile(); });
})();

/* Exposé pour l'inspecteur Safari (Mac branché sur l'iPhone) et pour les
 * tests : rien dans l'app ne dépend de ces références. Pratique pour regarder
 * la file d'envoi ou forcer une synchro depuis la console quand quelque chose
 * cloche en pleine séance. */
window.MFC = { S, K, LS, Chrono, Son, Reveil, aller, pousser, synchroniser,
               rendreAccueil, rendreExo, rendreSport, assurerBundle, mmss };
