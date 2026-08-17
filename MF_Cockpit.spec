# -*- mode: python ; coding: utf-8 -*-
"""Spec PyInstaller — .exe fenêtré mono-fichier MF Cockpit.

    pyinstaller MF_Cockpit.spec

Gère les hidden-imports/data des paquets qui se chargent dynamiquement
(mcstatus, dns.*, winotify, winsdk/winrt, customtkinter).
"""
import os

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hidden = ["pythoncom", "pywintypes", "win32com", "win32com.client",
          "win32com.client.dynamic",
          # stdlib chargée dynamiquement par le serveur mobile / la base
          "sqlite3", "http.server", "socketserver", "winreg"]
datas = []

for pkg in ("mcstatus", "dns", "winotify", "winsdk", "winrt", "tzdata"):
    try:
        hidden += collect_submodules(pkg)
    except Exception:
        pass

# tzdata est un paquet de données pures (fuseaux horaires) -> embarquer ses .zi.
try:
    datas += collect_data_files("tzdata")
except Exception:
    pass

# customtkinter embarque des fichiers de thème/police à copier.
try:
    datas += collect_data_files("customtkinter")
except Exception:
    pass
try:
    datas += collect_data_files("winotify")
except Exception:
    pass

# Thème violet chargé au runtime (os.path.join(__file__, ...)).
datas += [("mfcockpit/ui/theme_purple.json", "mfcockpit/ui")]

# Page mobile servie par le serveur local (paths.WEB_DIR -> sys._MEIPASS/web).
for _f in ("index.html", "app.js", "style.css"):
    _p = os.path.join("web", _f)
    if os.path.isfile(_p):
        datas += [(_p, "web")]

# Médias d'exercices livrés avec l'app (le dossier à côté de l'exe reste
# prioritaire : c'est là que l'utilisateur dépose les siens).
if os.path.isdir(os.path.join("media", "exos")):
    for _f in os.listdir(os.path.join("media", "exos")):
        _p = os.path.join("media", "exos", _f)
        if os.path.isfile(_p):
            datas += [(_p, os.path.join("media", "exos"))]

block_cipher = None

a = Analysis(
    ["mf_cockpit.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "PyQt5", "PySide6", "tornado"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="MF_Cockpit",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,   # --windowed
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
