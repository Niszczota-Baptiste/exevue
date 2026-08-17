"""Notifications desktop (winotify) avec fallback bannière + bip.

`notify()` poste une notif système si winotify est dispo, sinon déclenche un
callback de bannière in-app (+ bip Windows). Tout est best-effort.
"""

try:
    from winotify import Notification as _WinNotif
except Exception:
    _WinNotif = None

try:
    import winsound
except Exception:
    winsound = None


# Callbacks optionnels posés par l'app : bannière in-app, et remise au premier
# plan quand on clique sur une notification.
_banner_cb = None
_focus_cb = None


def set_banner_callback(fn):
    global _banner_cb
    _banner_cb = fn


def set_focus_callback(fn):
    global _focus_cb
    _focus_cb = fn


def revenir_au_premier_plan(onglet="aujourdhui"):
    """Remonte la fenêtre du cockpit sur l'onglet demandé (best-effort)."""
    if _focus_cb is None:
        return
    try:
        _focus_cb(onglet)
    except Exception:
        pass


def _beep():
    if winsound is not None:
        try:
            winsound.MessageBeep()
            return
        except Exception:
            pass
    try:
        print("\a", end="", flush=True)  # bip terminal en dernier recours
    except Exception:
        pass


def _url_ouverture():
    """URL locale qui remet le cockpit au premier plan quand on la visite.

    Windows ne laisse pas winotify rappeler du code Python au clic sur le
    corps d'un toast. On passe donc par le serveur mobile déjà en écoute : le
    bouton d'action ouvre `http://127.0.0.1:<port>/ouvrir`, et c'est ce
    serveur qui remonte la fenêtre. Import tardif : `notify` doit rester
    importable même sans base ni serveur.
    """
    try:
        from . import webserver
        if not webserver.actif():
            return None
        return (f"http://127.0.0.1:{webserver.port()}/ouvrir"
                f"?t={webserver.jeton()}")
    except Exception:
        return None


def notify(title: str, message: str, app_id: str = "MF Cockpit",
           ouvrir_cockpit: bool = False):
    """Notif desktop best-effort + fallback bannière/bip. Non bloquant."""
    posted = False
    if _WinNotif is not None:
        try:
            n = _WinNotif(app_id=app_id, title=title, msg=message)
            if ouvrir_cockpit:
                lien = _url_ouverture()
                if lien:
                    n.add_actions(label="Ouvrir le cockpit", launch=lien)
            n.show()
            posted = True
        except Exception:
            posted = False

    if not posted:
        _beep()
        if _banner_cb is not None:
            try:
                _banner_cb(f"{title} — {message}")
            except Exception:
                pass
