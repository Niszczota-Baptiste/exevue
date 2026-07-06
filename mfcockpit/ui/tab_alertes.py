"""Onglet [Alertes] : quêtes dispo / échéances / ressources wanted du site.

Affiche le snapshot `quests` publié par le poller (flux cockpit du site).
Les listes ne sont reconstruites que quand le feed change (generatedAt),
le reste du refresh ne touche que la ligne d'état — l'onglet reste léger
même rafraîchi chaque seconde.
"""
import time

import customtkinter as ctk

from . import theme
from .base import ThemedScroll
from .theme import C
from .widgets import Indicator

# priorité wanted -> (couleur voyant, libellé)
_PRIORITY = {1: ("red", "haute"), 2: ("orange", "moyenne"), 3: ("grey", "basse")}

_OCC_LABELS = {
    "journaliere": "Journalières",
    "hebdomadaire": "Hebdomadaires",
    "mensuelle": "Mensuelles",
}


def _fmt_delay(seconds):
    """Durée relative compacte : 'dans 3 h', 'dans 45 min', 'dépassée'."""
    if seconds is None:
        return ""
    if seconds <= 0:
        return "dépassée"
    if seconds < 3600:
        return f"dans {int(seconds // 60)} min"
    if seconds < 48 * 3600:
        return f"dans {seconds / 3600:.0f} h"
    return f"dans {seconds / 86400:.0f} j"


class AlertesTab(ThemedScroll):
    def __init__(self, master, app):
        super().__init__(master, app)
        self._rendered_at = None  # generatedAt du dernier feed affiché
        self._build()

    # ---- construction ----
    def _build(self):
        # 1) Flux du site (config)
        f = self._section("Flux du site", "quêtes + wanted")
        ctk.CTkLabel(
            f, text="URL secrète du flux — bouton « 🛰️ Cockpit MF » sur /quetes",
            font=theme.font("body", 11), text_color=C["dim"], anchor="w",
        ).pack(fill="x")
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", pady=(4, 0))
        self.url_entry = ctk.CTkEntry(
            row, font=theme.font("mono", 11),
            placeholder_text="https://…/api/quests/cockpit/<token>.json")
        self.url_entry.insert(0, str(self.cfg.get("quests_feed.url", "")))
        self.url_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="OK", width=42, command=self._save_feed,
                      fg_color=C["accent"], hover_color=C["accent_dk"],
                      text_color="#f6f2ff", border_width=0,
                      font=theme.font("head", 11, "bold")).pack(side="left",
                                                                padx=(6, 0))
        opts = ctk.CTkFrame(f, fg_color="transparent")
        opts.pack(fill="x", pady=(8, 0))
        self.notify_var = ctk.BooleanVar(
            value=bool(self.cfg.get("quests_feed.notify", True)))
        ctk.CTkSwitch(opts, text="Notifications Windows", variable=self.notify_var,
                      command=self._save_feed,
                      font=theme.font("body", 12)).pack(side="left")
        self.status = Indicator(opts, text="flux non configuré")
        self.status.set("grey")
        self.status.pack(side="right")

        # 2) Résumé
        f = self._section("Résumé")
        boxes = ctk.CTkFrame(f, fg_color="transparent")
        boxes.pack(fill="x")
        self.count_avail = self._stat(boxes, "dispo", 0)
        self.count_due = self._stat(boxes, "échéances", 1, color=C["orange"])
        self.count_wanted = self._stat(boxes, "wanted", 2, color=C["pink"])
        for i in range(3):
            boxes.grid_columnconfigure(i, weight=1, uniform="alr")

        # 3) Listes (reconstruites quand le feed change)
        self.due_frame = self._section("Quêtes à échéance", "sous 72 h")
        self.avail_frame = self._section("Quêtes disponibles",
                                         "non faites cette période")
        self.wanted_frame = self._section("Ressources recherchées",
                                          "wanted non récupérées")
        for frame in (self.due_frame, self.avail_frame, self.wanted_frame):
            self._placeholder(frame, "…")

    def _stat(self, parent, label, col, color=None):
        box, val = theme.stat_box(parent, label, "—", color)
        box.grid(row=0, column=col, padx=(0 if col == 0 else 6, 0), sticky="ew")
        return val

    def _placeholder(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=theme.font("body", 12),
                     text_color=C["dim"], anchor="w").pack(fill="x")

    def _save_feed(self):
        self.cfg.set("quests_feed.url", self.url_entry.get().strip())
        self.cfg.set("quests_feed.notify", bool(self.notify_var.get()))
        self._rendered_at = None  # force le re-rendu au prochain snapshot

    # ---- rendu des listes ----
    def _clear(self, frame):
        for w in frame.winfo_children():
            w.destroy()

    def _item_row(self, parent, dot_color, title, right="", detail=""):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=2)
        ind = Indicator(row, text=title)
        ind.set(dot_color, title)
        ind.pack(side="left")
        if right:
            ctk.CTkLabel(row, text=right, font=theme.font("mono", 11),
                         text_color=C["muted"]).pack(side="right")
        if detail:
            ctk.CTkLabel(parent, text=detail, anchor="w", justify="left",
                         font=theme.font("body", 11), text_color=C["dim"],
                         wraplength=300).pack(fill="x", padx=(25, 0))

    def _render_feed(self, feed):
        now = time.time()

        # échéances : rouge < 24 h, orange sinon
        self._clear(self.due_frame)
        deadlines = feed.get("deadlines") or []
        for q in deadlines:
            left = (q.get("dueDate") or 0) - now
            self._item_row(self.due_frame,
                           "red" if left < 24 * 3600 else "orange",
                           str(q.get("titre", "?")), _fmt_delay(left),
                           str(q.get("faction") or ""))
        if not deadlines:
            self._placeholder(self.due_frame, "aucune échéance proche")

        # disponibles : groupées par occurrence, avec compte à rebours de reset
        self._clear(self.avail_frame)
        available = feed.get("available") or {}
        total = 0
        for occ in ("journaliere", "hebdomadaire", "mensuelle"):
            quests = available.get(occ) or []
            if not quests:
                continue
            total += len(quests)
            ctk.CTkLabel(self.avail_frame, text=_OCC_LABELS[occ].upper(),
                         font=theme.font("head", 10, "bold"),
                         text_color=C["accent_lt"], anchor="w"
                         ).pack(fill="x", pady=(6 if total > len(quests) else 0, 1))
            for q in quests:
                reset_at = q.get("nextResetAt")
                self._item_row(
                    self.avail_frame, "accent", str(q.get("titre", "?")),
                    f"reset {_fmt_delay(reset_at - now)}" if reset_at else "",
                    str(q.get("faction") or ""))
        if not total:
            msg = ("tout est fait, bravo !"
                   if feed.get("remindersEnabled", True)
                   else "rappels désactivés côté site (bouton 🛰️ sur /quetes)")
            self._placeholder(self.avail_frame, msg)

        # wanted : voyant par priorité, quantité, workspace + note
        self._clear(self.wanted_frame)
        wanted = feed.get("wanted")
        if wanted is None:
            self._placeholder(
                self.wanted_frame,
                "non fourni par le site (feed cockpit sans les wanted)")
        elif not wanted:
            self._placeholder(self.wanted_frame, "aucune ressource en attente")
        else:
            for w in wanted:
                color, prio = _PRIORITY.get(int(w.get("priority", 2)),
                                            ("grey", "?"))
                qty = int(w.get("quantity", 1))
                detail = " · ".join(x for x in (
                    str(w.get("workspace") or ""),
                    f"priorité {prio}",
                    str(w.get("note") or "")) if x)
                self._item_row(self.wanted_frame, color,
                               str(w.get("name", "?")),
                               f"×{qty}" if qty > 1 else "", detail)

    # ---- refresh (chaque seconde ; re-rendu seulement si feed changé) ----
    def refresh(self, snap):
        state = snap.get("quests")
        if not state:
            self.status.set("grey", "flux non configuré")
            for val in (self.count_avail, self.count_due, self.count_wanted):
                val.configure(text="—")
            if self._rendered_at is not None:
                self._rendered_at = None
                for frame in (self.due_frame, self.avail_frame,
                              self.wanted_frame):
                    self._clear(frame)
                    self._placeholder(frame, "configure l'URL du flux ci-dessus")
            return

        feed = state.get("feed")
        if state.get("ok"):
            age = time.time() - (state.get("fetched_at") or 0)
            self.status.set("green", f"sync il y a {int(age // 60)} min"
                            if age >= 60 else "sync à l'instant")
        else:
            self.status.set("red", state.get("error") or "erreur")
        if not feed:
            return

        counts = feed.get("counts") or {}
        wanted = feed.get("wanted")
        self.count_avail.configure(text=str(counts.get("availableTotal", 0)))
        self.count_due.configure(text=str(counts.get("deadlines", 0)))
        self.count_wanted.configure(
            text="—" if wanted is None else str(len(wanted)))

        generated = feed.get("generatedAt")
        if generated != self._rendered_at:
            self._rendered_at = generated
            self._render_feed(feed)
