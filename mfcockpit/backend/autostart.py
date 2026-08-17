"""Lancement au démarrage de Windows — via `winreg` (stdlib, zéro dépendance).

On écrit/supprime une valeur sous
`HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\MFCockpit`.
C'est la clé *utilisateur* : pas de droits administrateur nécessaires, et ça ne
touche rien pour les autres comptes de la machine.

Hors Windows, tout dégrade proprement : `disponible()` renvoie False et l'UI
grise la case.
"""
import os
import sys

try:
    import winreg
except ImportError:              # Linux / macOS : pas de registre
    winreg = None

CLE = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOM = "MFCockpit"
ARG_REDUIT = "--reduit"


def disponible() -> bool:
    return winreg is not None


def commande(reduit: bool = False) -> str:
    """Ligne de commande à inscrire — guillemets compris (chemins avec espaces)."""
    if getattr(sys, "frozen", False):
        base = f'"{sys.executable}"'
    else:
        script = os.path.abspath(
            os.path.join(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))), "mf_cockpit.py"))
        # pythonw.exe : pas de fenêtre console au démarrage de session.
        exe = sys.executable
        exew = exe.replace("python.exe", "pythonw.exe")
        if os.path.isfile(exew):
            exe = exew
        base = f'"{exe}" "{script}"'
    return f"{base} {ARG_REDUIT}" if reduit else base


def etat() -> dict:
    """{actif, reduit, commande} — lit le registre sans jamais lever."""
    if not disponible():
        return {"actif": False, "reduit": False, "commande": None,
                "supporte": False}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE) as cle:
            valeur, _type = winreg.QueryValueEx(cle, NOM)
        return {"actif": True, "reduit": ARG_REDUIT in valeur,
                "commande": valeur, "supporte": True}
    except FileNotFoundError:
        return {"actif": False, "reduit": False, "commande": None,
                "supporte": True}
    except OSError:
        return {"actif": False, "reduit": False, "commande": None,
                "supporte": True}


def activer(reduit: bool = False) -> bool:
    if not disponible():
        return False
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, CLE) as cle:
            winreg.SetValueEx(cle, NOM, 0, winreg.REG_SZ, commande(reduit))
        return True
    except OSError:
        return False


def desactiver() -> bool:
    if not disponible():
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE, 0,
                            winreg.KEY_SET_VALUE) as cle:
            winreg.DeleteValue(cle, NOM)
        return True
    except FileNotFoundError:
        return True          # déjà absent : le résultat voulu est atteint
    except OSError:
        return False


def demarre_reduit() -> bool:
    """Le process a-t-il été lancé avec `--reduit` ?"""
    return ARG_REDUIT in sys.argv
