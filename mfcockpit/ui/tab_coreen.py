"""Onglet [Coréen] : micro-révision (SM-2 allégé) + deck éditable + CSV/JSON."""
from tkinter import filedialog, messagebox

import customtkinter as ctk

from . import theme
from .base import ThemedScroll
from .theme import C


class CoreenTab(ThemedScroll):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.deck = app.deck
        self._queue = []
        self._current = None
        self._build()

    def _build(self):
        # --- révision ---
        f = self._section("Micro-révision")
        card = ctk.CTkFrame(f, fg_color=C["inset"], corner_radius=10,
                            border_color=C["inset_border"], border_width=1)
        card.pack(fill="x", pady=(0, 8))
        self.card_kr = ctk.CTkLabel(card, text="—", font=theme.font("body", 30, "bold"),
                                    text_color=C["accent_lt2"])
        self.card_kr.pack(fill="x", padx=10, pady=(16, 2))
        self.card_romaja = ctk.CTkLabel(card, text="", text_color=C["dim"],
                                        font=theme.font("mono", 12))
        self.card_romaja.pack(fill="x", padx=10)
        self.card_answer = ctk.CTkLabel(card, text="", font=theme.font("body", 14),
                                        wraplength=320, justify="center",
                                        text_color=C["text"])
        self.card_answer.pack(fill="x", padx=10, pady=(6, 14))

        self.btn_reveal = ctk.CTkButton(f, text="Révéler", command=self._reveal,
                                        fg_color=C["accent"], hover_color=C["accent_dk"],
                                        text_color="#f6f2ff", border_width=0,
                                        font=theme.font("head", 13, "bold"))
        self.btn_reveal.pack(fill="x", pady=(0, 6))
        grade = ctk.CTkFrame(f, fg_color="transparent")
        grade.pack(fill="x")
        ctk.CTkButton(grade, text="Pas su", fg_color="#5a2740", hover_color="#7a3b3b",
                      font=theme.font("head", 13, "bold"),
                      command=lambda: self._grade(False)).pack(
            side="left", expand=True, fill="x", padx=(0, 4))
        ctk.CTkButton(grade, text="Su", fg_color="#1f6b48", hover_color="#2e7d4f",
                      font=theme.font("head", 13, "bold"),
                      command=lambda: self._grade(True)).pack(
            side="left", expand=True, fill="x", padx=(4, 0))
        self.session_info = ctk.CTkLabel(f, text="", text_color=C["dim"],
                                         font=theme.font("body", 11))
        self.session_info.pack(fill="x", pady=(6, 6))
        ctk.CTkButton(f, text="Lancer une révision", command=self.start_session,
                      font=theme.font("head", 12, "bold")).pack(fill="x")

        # --- réglages ---
        f = self._section("Réglages")
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(row, text="Mots / session", font=theme.font("body", 13),
                     text_color=C["muted"]).pack(side="left")
        ctk.CTkButton(row, text="OK", width=42, command=self._save_wps,
                      fg_color=C["accent"], hover_color=C["accent_dk"],
                      text_color="#f6f2ff", border_width=0,
                      font=theme.font("head", 11, "bold")).pack(side="right")
        self.wps = ctk.CTkEntry(row, width=52, justify="center",
                                font=theme.font("mono", 13))
        self.wps.insert(0, str(self.cfg.get("korean.words_per_session", 3)))
        self.wps.pack(side="right", padx=6)

        # --- deck ---
        f = self._section("Deck")
        impexp = ctk.CTkFrame(f, fg_color="transparent")
        impexp.pack(fill="x", pady=(0, 6))
        for txt, kind, fn in (("Imp. CSV", "csv", self._import),
                              ("Imp. JSON", "json", self._import),
                              ("Exp. CSV", "csv", self._export),
                              ("Exp. JSON", "json", self._export)):
            ctk.CTkButton(impexp, text=txt, width=82, font=theme.font("head", 11, "bold"),
                          command=lambda k=kind, f=fn: f(k)).pack(side="left", padx=2)

        addrow = ctk.CTkFrame(f, fg_color="transparent")
        addrow.pack(fill="x", pady=(0, 6))
        self.add_kr = ctk.CTkEntry(addrow, placeholder_text="한국어", width=82,
                                   font=theme.font("body", 13))
        self.add_kr.pack(side="left", padx=2)
        self.add_romaja = ctk.CTkEntry(addrow, placeholder_text="romaja", width=80,
                                       font=theme.font("body", 12))
        self.add_romaja.pack(side="left", padx=2)
        self.add_fr = ctk.CTkEntry(addrow, placeholder_text="français",
                                   font=theme.font("body", 12))
        self.add_fr.pack(side="left", fill="x", expand=True, padx=2)
        ctk.CTkButton(addrow, text="+", width=32, command=self._add_card,
                      fg_color=C["accent"], hover_color=C["accent_dk"],
                      text_color="#f6f2ff", border_width=0,
                      font=theme.font("head", 13, "bold")).pack(side="left", padx=2)

        self.deck_list = ctk.CTkFrame(f, fg_color="transparent")
        self.deck_list.pack(fill="x")
        self._render_deck()

    # ---- session ----
    def start_session(self):
        self._queue = list(self.deck.due_cards())
        self._next_card()

    def _next_card(self):
        if not self._queue:
            self._current = None
            self.card_kr.configure(text="✓", text_color=C["green"])
            self.card_romaja.configure(text="")
            self.card_answer.configure(text="Rien à réviser pour l'instant.")
            self.session_info.configure(text="")
            return
        self._current = self._queue[0]
        self.card_kr.configure(text=self._current.get("kr", "—"),
                               text_color=C["accent_lt2"])
        self.card_romaja.configure(text="")
        self.card_answer.configure(text="")
        self.session_info.configure(text=f"{len(self._queue)} carte(s) en file")

    def _reveal(self):
        if not self._current:
            return
        c = self._current
        self.card_romaja.configure(text=c.get("romaja", ""))
        ans = c.get("fr", "")
        if c.get("example"):
            ans += f"\n\n{c['example']}"
        self.card_answer.configure(text=ans)

    def _grade(self, knew):
        if not self._current:
            return
        self.deck.grade(self._current, knew)
        if self._queue:
            self._queue.pop(0)
        self._next_card()
        self._render_deck()

    def _save_wps(self):
        try:
            self.cfg.set("korean.words_per_session", int(self.wps.get()))
        except ValueError:
            pass

    # ---- deck ----
    def _add_card(self):
        kr = self.add_kr.get().strip()
        if not kr:
            return
        self.deck.add(kr, self.add_romaja.get(), self.add_fr.get())
        for e in (self.add_kr, self.add_romaja, self.add_fr):
            e.delete(0, "end")
        self._render_deck()

    def _render_deck(self):
        for w in self.deck_list.winfo_children():
            w.destroy()
        for i, c in enumerate(self.deck.cards()):
            row = ctk.CTkFrame(self.deck_list, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=f"{c.get('kr', '')}   {c.get('fr', '')}",
                         anchor="w", font=theme.font("body", 12),
                         text_color=C["text_norm"]).pack(
                side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="✕", width=26, fg_color="#5a2740",
                          hover_color="#7a3b3b",
                          command=lambda i=i: self._del_card(i)).pack(side="left")

    def _del_card(self, i):
        self.deck.remove(i)
        self._render_deck()

    # ---- import / export ----
    def _export(self, kind):
        ext = "csv" if kind == "csv" else "json"
        path = filedialog.asksaveasfilename(defaultextension=f".{ext}",
                                            filetypes=[(ext.upper(), f"*.{ext}")])
        if not path:
            return
        try:
            data = self.deck.export_csv() if kind == "csv" else self.deck.export_json()
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(data)
        except Exception as e:
            messagebox.showerror("Export", str(e))

    def _import(self, kind):
        ext = "csv" if kind == "csv" else "json"
        path = filedialog.askopenfilename(filetypes=[(ext.upper(), f"*.{ext}")])
        if not path:
            return
        replace = messagebox.askyesno("Import",
                                      "Remplacer le deck existant ?\n(Non = ajouter)")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
            if kind == "csv":
                self.deck.import_csv(text, replace=replace)
            else:
                self.deck.import_json(text, replace=replace)
        except Exception as e:
            messagebox.showerror("Import", str(e))
        self._render_deck()

    def refresh(self, snap):
        pass
