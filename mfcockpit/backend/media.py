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


def available() -> bool:
    return _AVAILABLE


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


def poll():
    """Renvoie {title, artist, album, playing, app} ou None. Best-effort."""
    if not _AVAILABLE:
        return None
    try:
        return _run(_poll_async())
    except Exception:
        return None


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
    """playpause / next / prev. Best-effort, non bloquant côté UI."""
    if not _AVAILABLE:
        return False
    try:
        return bool(_run(_control_async(action)))
    except Exception:
        return False
