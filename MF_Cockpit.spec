# -*- mode: python ; coding: utf-8 -*-
"""Spec PyInstaller — .exe fenêtré mono-fichier MF Cockpit.

    pyinstaller MF_Cockpit.spec

Gère les hidden-imports/data des paquets qui se chargent dynamiquement
(mcstatus, dns.*, winotify, winsdk/winrt, customtkinter).
"""
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hidden = []
datas = []

for pkg in ("mcstatus", "dns", "winotify", "winsdk", "winrt"):
    try:
        hidden += collect_submodules(pkg)
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
