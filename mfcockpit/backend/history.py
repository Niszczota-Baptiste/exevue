"""Historique de fréquentation Minefield : fichier roulant (~48 h).

Format : une ligne `epoch\tplayers` par tick. `recent_points()` renvoie les
points pour dessiner un sparkline (sans matplotlib).
"""
import os
import time

from . import paths

WINDOW_SECONDS = 48 * 3600  # ~48 h


def log_players(players: int, ts: float = None):
    ts = time.time() if ts is None else ts
    line = f"{int(ts)}\t{int(players)}\n"
    try:
        with open(paths.ATTENDANCE_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        return
    # Compaction occasionnelle : ~1 chance sur 30 (≈ tous les ~10 min à POLL=20s).
    if int(ts) % 30 == 0:
        _prune()


def _read_all():
    rows = []
    try:
        with open(paths.ATTENDANCE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) != 2:
                    continue
                try:
                    rows.append((int(parts[0]), int(parts[1])))
                except ValueError:
                    continue
    except FileNotFoundError:
        return []
    except Exception:
        return []
    return rows


def _prune():
    rows = _read_all()
    if not rows:
        return
    cutoff = time.time() - WINDOW_SECONDS
    kept = [r for r in rows if r[0] >= cutoff]
    if len(kept) == len(rows):
        return
    tmp = paths.ATTENDANCE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            for ts, p in kept:
                f.write(f"{ts}\t{p}\n")
        os.replace(tmp, paths.ATTENDANCE_FILE)
    except Exception:
        pass


def recent_points(hours: float = 12.0):
    """Renvoie [(epoch, players)] sur les dernières `hours` heures."""
    cutoff = time.time() - hours * 3600
    return [r for r in _read_all() if r[0] >= cutoff]
