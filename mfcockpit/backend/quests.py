"""Flux « cockpit » du site : quêtes + ressources wanted (modèle PULL).

Le site expose un endpoint secret par membre
(GET https://…/api/quests/cockpit/<token>.json, sans cookie) qui renvoie les
quêtes récurrentes redevenues disponibles, les échéances proches, les gains
potentiels et — feed étendu — les ressources « wanted » non récupérées.

`QuestFeedWatcher.tick()` est appelé à chaque heavy-tick du poller mais ne
refetch qu'à sa propre cadence (`quests_feed.poll_seconds`, défaut 5 min : le
flux est une lecture pure, rate-limitée côté site). Il publie un snapshot
{ok, error, fetched_at, feed} — en cas d'erreur réseau le dernier feed valide
est conservé pour que l'UI reste peuplée.

Notifications (anti-spam, même esprit que l'alerte seuil joueurs) : jamais au
premier relevé, puis uniquement sur les *nouveautés* — une quête qui redevient
disponible (la clé inclut `periodKey`, donc chaque reset re-déclenche), une
échéance qui entre dans la fenêtre, une ressource wanted ajoutée. Une seule
notif par catégorie et par tick, groupée.
"""
import json
import time
import urllib.error
import urllib.request

from . import notify

# libellés d'occurrence pour les notifs groupées
_OCC_LABELS = {
    "journaliere": "journalière",
    "hebdomadaire": "hebdomadaire",
    "mensuelle": "mensuelle",
}


def fetch_feed(url: str, timeout: float = 10.0) -> dict:
    """GET le flux JSON. Lève urllib.error.* / ValueError en cas de souci."""
    req = urllib.request.Request(url, headers={"User-Agent": "mf-cockpit"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _alert_keys(feed: dict):
    """Clés stables des alertes du feed (pour détecter les nouveautés).

    - quête dispo : "q:<id>:<periodKey>" -> re-notifie à chaque reset
    - échéance    : "d:<id>"
    - wanted      : "w:<id>"
    """
    keys = set()
    available = feed.get("available") or {}
    for quests in available.values():
        for q in quests or []:
            keys.add(f"q:{q.get('id')}:{q.get('periodKey', '')}")
    for q in feed.get("deadlines") or []:
        keys.add(f"d:{q.get('id')}")
    for w in feed.get("wanted") or []:
        keys.add(f"w:{w.get('id')}")
    return keys


class QuestFeedWatcher:
    def __init__(self, config):
        self.config = config
        self._last_fetch = 0.0
        self._last_url = None
        self._seen = None       # clés vues au tick précédent (None = 1er relevé)
        self._snapshot = None   # dernier état publié

    # ---- tick (appelé par le poller, thread de fond) ----
    def tick(self, now=None):
        now = now if now is not None else time.time()
        url = (self.config.get("quests_feed.url", "") or "").strip()
        if not url:
            self._last_url = None
            self._seen = None
            self._snapshot = None
            return None

        if url != self._last_url:  # URL changée : repart de zéro, fetch direct
            self._last_url = url
            self._seen = None
            self._snapshot = None
            self._last_fetch = 0.0

        every = max(60, int(self.config.get("quests_feed.poll_seconds", 300)))
        if self._snapshot is not None and now - self._last_fetch < every:
            return self._snapshot
        self._last_fetch = now

        try:
            feed = fetch_feed(url)
        except urllib.error.HTTPError as e:
            return self._fail(f"HTTP {e.code}" + (" (token invalide ?)"
                                                  if e.code == 404 else ""), now)
        except Exception:
            return self._fail("site injoignable", now)

        if not isinstance(feed, dict):
            return self._fail("réponse inattendue", now)

        keys = _alert_keys(feed)
        if self._seen is not None:
            self._notify_new(feed, keys - self._seen)
        self._seen = keys

        self._snapshot = {"ok": True, "error": None, "fetched_at": now,
                          "feed": feed}
        return self._snapshot

    def _fail(self, error: str, now: float):
        prev = self._snapshot or {}
        self._snapshot = {"ok": False, "error": error, "fetched_at": now,
                          "feed": prev.get("feed")}  # garde le dernier valide
        return self._snapshot

    # ---- notifications groupées ----
    def _notify_new(self, feed: dict, new_keys: set):
        if not new_keys or not self.config.get("quests_feed.notify", True):
            return

        # quêtes redevenues disponibles : compte par occurrence
        occ_counts = {}
        available = feed.get("available") or {}
        for occ, quests in available.items():
            n = sum(1 for q in quests or []
                    if f"q:{q.get('id')}:{q.get('periodKey', '')}" in new_keys)
            if n:
                occ_counts[occ] = n
        if occ_counts:
            total = sum(occ_counts.values())
            detail = ", ".join(
                f"{n} {_OCC_LABELS.get(occ, occ)}{'s' if n > 1 else ''}"
                for occ, n in occ_counts.items())
            notify.notify("Quêtes disponibles",
                          f"{total} quête{'s' if total > 1 else ''} à faire "
                          f"({detail}).")

        deadlines = [q for q in feed.get("deadlines") or []
                     if f"d:{q.get('id')}" in new_keys]
        if deadlines:
            titles = ", ".join(str(q.get("titre", "?")) for q in deadlines[:3])
            if len(deadlines) > 3:
                titles += "…"
            notify.notify("Quête à échéance" + ("s" if len(deadlines) > 1 else ""),
                          f"Bientôt expirée{'s' if len(deadlines) > 1 else ''} : "
                          f"{titles}")

        wanted = [w for w in feed.get("wanted") or []
                  if f"w:{w.get('id')}" in new_keys]
        if wanted:
            names = ", ".join(str(w.get("name", "?")) for w in wanted[:3])
            if len(wanted) > 3:
                names += "…"
            notify.notify("Ressources recherchées",
                          f"Nouvelle{'s' if len(wanted) > 1 else ''} demande"
                          f"{'s' if len(wanted) > 1 else ''} : {names}")
