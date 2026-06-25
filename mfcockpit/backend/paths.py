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


CONFIG_FILE = data_path("config.json")
PLAYTIME_FILE = data_path("playtime.json")
ATTENDANCE_FILE = data_path("attendance.log")
CLIPBOARD_FILE = data_path("clipboard.json")
