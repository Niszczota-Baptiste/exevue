"""Palette, polices et briques d'UI réutilisables (look « cockpit » violet).

S'inspire du mock HTML : cartes sombres, accents violets, voyants à halo,
typos condensées (Rajdhani) + chiffres mono (JetBrains Mono) avec repli propre
sur les polices système si elles ne sont pas installées. Aucune dépendance
lourde : tout reste tkinter/customtkinter, donc PyInstaller-friendly et léger.
"""
import os
import tkinter as tk
import tkinter.font as tkfont

import customtkinter as ctk

THEME_FILE = os.path.join(os.path.dirname(__file__), "theme_purple.json")

# --- palette (alignée sur le mock) ---
C = {
    "page": "#0c0a13",
    "sidebar": "#0a0811",
    "titlebar": "#120e1e",
    "card": "#13101d",
    "card_border": "#221b34",
    "inset": "#1a1626",
    "inset_border": "#2a2340",
    "accent": "#7c3aed",
    "accent_lt": "#a78bfa",
    "accent_lt2": "#c4b3f0",
    "accent_dk": "#6d28d9",
    "nav_active": "#1b1430",
    "text": "#e7e2f5",
    "text_norm": "#cdc6df",
    "muted": "#8b85a0",
    "dim": "#6a6383",
    "dimmer": "#5f5876",
    "green": "#34d399",
    "blue": "#7c8cff",
    "orange": "#f5b14e",
    "red": "#f0617f",
    "pink": "#f0a0b8",
    "grey": "#4a4458",
}

# repli de familles : 1re installée gagne, sinon police par défaut Tk.
_FALLBACKS = {
    "head": ["Rajdhani", "Bahnschrift", "Oswald", "Segoe UI Semibold",
             "Segoe UI", "DejaVu Sans"],
    "mono": ["JetBrains Mono", "Cascadia Mono", "Consolas", "DejaVu Sans Mono",
             "Courier New"],
    "body": ["Outfit", "Segoe UI", "Helvetica Neue", "DejaVu Sans"],
}
_resolved = {}


def _resolve_families():
    if _resolved:
        return
    try:
        available = set(tkfont.families())
    except Exception:
        available = set()
    for role, cands in _FALLBACKS.items():
        pick = next((f for f in cands if f in available), cands[-1])
        _resolved[role] = pick


def font(role="body", size=13, weight="normal"):
    """Tuple police prêt pour (CTk)tkinter, avec repli de famille."""
    _resolve_families()
    fam = _resolved.get(role, "TkDefaultFont")
    return (fam, size, weight) if weight != "normal" else (fam, size)


def apply_theme():
    """Active le mode sombre + le thème violet global (recolore tous les widgets)."""
    ctk.set_appearance_mode("dark")
    try:
        ctk.set_default_color_theme(THEME_FILE)
    except Exception:
        ctk.set_default_color_theme("blue")


# ---- briques réutilisables ----

def diamond(master, size=8, color=None):
    """Petit losange accent (le marqueur des titres de section)."""
    color = color or C["accent_lt"]
    cv = tk.Canvas(master, width=size, height=size, highlightthickness=0,
                   bg=C["card"])
    h = size / 2
    cv.create_polygon(h, 0, size, h, h, size, 0, h, fill=color, outline="")
    return cv


def section(parent, title, subtitle=None, card_bg=None):
    """Carte titrée (losange + titre majuscule). Renvoie le frame de contenu."""
    card = ctk.CTkFrame(parent, fg_color=card_bg or C["card"],
                        border_color=C["card_border"], border_width=1,
                        corner_radius=11)
    card.pack(fill="x", padx=2, pady=(0, 2))

    header = ctk.CTkFrame(card, fg_color="transparent")
    header.pack(fill="x", padx=14, pady=(12, 8))
    d = diamond(header)
    d.configure(bg=card_bg or C["card"])
    d.pack(side="left", padx=(0, 8))
    ctk.CTkLabel(header, text=title.upper(), font=font("head", 12, "bold"),
                 text_color=C["accent_lt"]).pack(side="left")
    if subtitle:
        ctk.CTkLabel(header, text=subtitle.upper(), font=font("head", 9),
                     text_color=C["dimmer"]).pack(side="left", padx=(8, 0))

    body = ctk.CTkFrame(card, fg_color="transparent")
    body.pack(fill="x", padx=14, pady=(0, 13))
    return body


def stat_box(parent, label, value="—", value_color=None):
    """Petite case « min / moy / max »… renvoie le label de valeur (à mettre à jour)."""
    box = ctk.CTkFrame(parent, fg_color=C["inset"], border_color=C["inset_border"],
                       border_width=1, corner_radius=7)
    ctk.CTkLabel(box, text=label.upper(), font=font("head", 9, "bold"),
                 text_color=C["dim"]).pack(anchor="w", padx=8, pady=(5, 0))
    val = ctk.CTkLabel(box, text=value, font=font("mono", 14),
                       text_color=value_color or C["text_norm"])
    val.pack(anchor="w", padx=8, pady=(0, 5))
    return box, val


def primary_button(parent, text, command=None, width=0, **kw):
    """Bouton d'action accentué (violet plein)."""
    return ctk.CTkButton(
        parent, text=text, command=command, width=width or 0,
        fg_color=C["accent"], hover_color=C["accent_dk"], text_color="#f6f2ff",
        border_width=0, corner_radius=7, font=font("head", 12, "bold"), **kw)
