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


# Callback optionnel pour afficher une bannière dans l'UI (mis par l'app).
_banner_cb = None


def set_banner_callback(fn):
    global _banner_cb
    _banner_cb = fn


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


def notify(title: str, message: str, app_id: str = "MF Cockpit"):
    """Notif desktop best-effort + fallback bannière/bip. Non bloquant."""
    posted = False
    if _WinNotif is not None:
        try:
            n = _WinNotif(app_id=app_id, title=title, msg=message)
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
