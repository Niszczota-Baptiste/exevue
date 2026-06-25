"""Contrôle média Windows via SMTC (winsdk / Windows.Media.Control).

Best-effort : si winsdk est absent (hors Windows) ou qu'aucune session ne
publie sur SMTC, tout dégrade proprement. L'API étant async, on l'exécute dans
un mini event-loop appelé depuis le thread de fond (jamais l'UI).
"""
import asyncio

try:
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as _Manager,
    )
    _AVAILABLE = True
except Exception:
    _Manager = None
    _AVAILABLE = False

try:
    from winsdk.windows.storage.streams import (
        Buffer, DataReader, InputStreamOptions,
    )
    _STREAMS = True
except Exception:
    _STREAMS = False

# iTunes (Apple) ne publie PAS sur SMTC : on l'atteint via son API COM.
try:
    import pythoncom  # noqa: F401  (fourni par pywin32)
    import win32com.client  # noqa: F401
    _ITUNES = True
except Exception:
    _ITUNES = False


def available() -> bool:
    return _AVAILABLE or _ITUNES


def _run(coro):
    """Exécute une coroutine dans une boucle dédiée (thread de fond)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _current_session():
    mgr = await _Manager.request_async()
    if mgr is None:
        return None
    return mgr.get_current_session()


async def _poll_async():
    session = await _current_session()
    if session is None:
        return None
    info = await session.try_get_media_properties_async()
    playback = session.get_playback_info()
    status = None
    try:
        status = int(playback.playback_status)  # 4 = playing, 5 = paused
    except Exception:
        status = None
    thumb = await _read_thumbnail(info)
    return {
        "title": getattr(info, "title", "") or "",
        "artist": getattr(info, "artist", "") or "",
        "album": getattr(info, "album_title", "") or "",
        "playing": status == 4,
        "app": getattr(session, "source_app_user_model_id", "") or "",
        "thumbnail": thumb,  # bytes JPEG/PNG ou None
    }


async def _read_thumbnail(info):
    """Pochette en bytes (best-effort). None si indispo."""
    if not _STREAMS:
        return None
    try:
        ref = getattr(info, "thumbnail", None)
        if ref is None:
            return None
        stream = await ref.open_read_async()
        size = stream.size
        if not size:
            return None
        buf = Buffer(size)
        await stream.read_async(buf, size, InputStreamOptions.READ_AHEAD)
        reader = DataReader.from_buffer(buf)
        data = bytearray(buf.length)
        reader.read_bytes(data)
        return bytes(data)
    except Exception:
        return None


# ---- iTunes (COM) ----

def _itunes_running():
    """Vrai si iTunes.exe tourne (évite de le lancer via COM)."""
    try:
        import psutil
        for p in psutil.process_iter(["name"]):
            if (p.info["name"] or "").lower() == "itunes.exe":
                return True
    except Exception:
        pass
    return False


def _itunes_app():
    if not _ITUNES or not _itunes_running():
        return None
    try:
        pythoncom.CoInitialize()  # thread de fond : init COM (idempotent)
    except Exception:
        pass
    try:
        # Dispatch dynamique : pas de cache makepy (fiable une fois gelé).
        return win32com.client.dynamic.Dispatch("iTunes.Application")
    except Exception:
        return None


def _itunes_poll():
    app = _itunes_app()
    if app is None:
        return None
    try:
        track = app.CurrentTrack
        if track is None:
            return None
        playing = False
        try:
            playing = int(app.PlayerState) == 1  # 1 = lecture
        except Exception:
            pass
        return {
            "title": getattr(track, "Name", "") or "",
            "artist": getattr(track, "Artist", "") or "",
            "album": getattr(track, "Album", "") or "",
            "playing": playing,
            "app": "iTunes",
            "thumbnail": None,
        }
    except Exception:
        return None


def _itunes_control(action: str) -> bool:
    app = _itunes_app()
    if app is None:
        return False
    try:
        if action == "playpause":
            app.PlayPause()
        elif action == "next":
            app.NextTrack()
        elif action == "prev":
            app.PreviousTrack()
        else:
            return False
        return True
    except Exception:
        return False


def poll():
    """Renvoie {title, artist, album, playing, app} ou None.

    SMTC d'abord (navigateurs, Apple Music du Store…) ; repli iTunes COM.
    """
    res = None
    if _AVAILABLE:
        try:
            res = _run(_poll_async())
        except Exception:
            res = None
    if (not res or not res.get("title")) and _ITUNES:
        it = _itunes_poll()
        if it and it.get("title"):
            return it
    return res


async def _control_async(action: str):
    session = await _current_session()
    if session is None:
        return False
    if action == "playpause":
        await session.try_toggle_play_pause_async()
    elif action == "next":
        await session.try_skip_next_async()
    elif action == "prev":
        await session.try_skip_previous_async()
    else:
        return False
    return True


def control(action: str) -> bool:
    """playpause / next / prev. SMTC si une session existe, sinon iTunes."""
    if _AVAILABLE:
        try:
            if bool(_run(_control_async(action))):
                return True
        except Exception:
            pass
    if _ITUNES:
        return _itunes_control(action)
    return False
