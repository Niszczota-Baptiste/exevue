"""Emplacement des fichiers de données / config.

Tout est posé À CÔTÉ de l'exe (ou du script en dev) pour rester portable :
config.json y est lu au démarrage et réécrit à chaque modif de réglage.
"""
import os
import sys


def base_dir() -> str:
    """Dossier de l'exe gelé (PyInstaller) ou du paquet en dev."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # …/mfcockpit/backend/paths.py -> remonte à la racine du projet
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def data_path(name: str) -> str:
    return os.path.join(base_dir(), name)


def bundle_dir() -> str:
    """Dossier des ressources embarquées (web/, media/).

    Gelé : PyInstaller dépose les `datas` dans `sys._MEIPASS`. En dev, c'est
    simplement la racine du projet.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    return meipass if meipass else base_dir()


def bundle_path(*parts: str) -> str:
    return os.path.join(bundle_dir(), *parts)


CONFIG_FILE = data_path("config.json")
PLAYTIME_FILE = data_path("playtime.json")
ATTENDANCE_FILE = data_path("attendance.log")
CLIPBOARD_FILE = data_path("clipboard.json")
DB_FILE = data_path("cockpit.db")

# Ressources embarquées (lecture seule) : page mobile et médias d'exercices.
WEB_DIR = bundle_path("web")
MEDIA_DIR = bundle_path("media", "exos")

# Médias ajoutés par l'utilisateur : toujours à côté de l'exe, jamais dans le
# bundle gelé (qui est volatile). Les deux dossiers sont consultés, celui-ci
# d'abord.
USER_MEDIA_DIR = data_path(os.path.join("media", "exos"))
