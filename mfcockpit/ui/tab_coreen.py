"""Onglet [Coréen] : micro-révision (SM-2 allégé) + deck éditable + CSV/JSON."""
from tkinter import filedialog, messagebox

import customtkinter as ctk


class CoreenTab(ctk.CTkScrollableFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.cfg = app.config_store
        self.deck = app.deck
        self._queue = []
        self._current = None
        self._revealed = False
        self._build()

    def _section(self, title):
        ctk.CTkLabel(self, text=title, font=("", 13, "bold"),
                     anchor="w").pack(fill="x", padx=4, pady=(10, 2))
        frame = ctk.CTkFrame(self)
        frame.pack(fill="x", padx=4, pady=2)
        return frame

    def _build(self):
        # --- révision ---
        f = self._section("Micro-révision")
        self.card_kr = ctk.CTkLabel(f, text="—", font=("", 26, "bold"))
        self.card_kr.pack(fill="x", padx=8, pady=(12, 2))
        self.card_romaja = ctk.CTkLabel(f, text="", text_color="#888")
        self.card_romaja.pack(fill="x", padx=8)
        self.card_answer = ctk.CTkLabel(f, text="", font=("", 14),
                                        wraplength=380, justify="center")
        self.card_answer.pack(fill="x", padx=8, pady=(6, 8))

        self.btn_reveal = ctk.CTkButton(f, text="Révéler",
                                        command=self._reveal)
        self.btn_reveal.pack(fill="x", padx=8, pady=2)
        grade = ctk.CTkFrame(f, fg_color="transparent")
        grade.pack(fill="x", padx=8, pady=(2, 10))
        self.btn_no = ctk.CTkButton(grade, text="Pas su", fg_color="#7a3b3b",
                                    command=lambda: self._grade(False))
        self.btn_no.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.btn_yes = ctk.CTkButton(grade, text="Su", fg_color="#2e7d4f",
                                     command=lambda: self._grade(True))
        self.btn_yes.pack(side="left", expand=True, fill="x", padx=(4, 0))
        self.session_info = ctk.CTkLabel(f, text="", text_color="#888")
        self.session_info.pack(fill="x", padx=8, pady=(0, 8))

        ctk.CTkButton(f, text="Lancer une révision",
                      command=self.start_session).pack(fill="x", padx=8, pady=(0, 8))

        # --- réglages ---
        f = self._section("Réglages")
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=8)
        ctk.CTkLabel(row, text="Mots / session :").pack(side="left")
        self.wps = ctk.CTkEntry(row, width=50)
        self.wps.insert(0, str(self.cfg.get("korean.words_per_session", 3)))
        self.wps.pack(side="left", padx=6)
        ctk.CTkButton(row, text="OK", width=40, command=self._save_wps).pack(side="left")

        # --- deck éditable ---
        f = self._section("Deck")
        impexp = ctk.CTkFrame(f, fg_color="transparent")
        impexp.pack(fill="x", padx=8, pady=(8, 2))
        ctk.CTkButton(impexp, text="Import CSV", width=86,
                      command=lambda: self._import("csv")).pack(side="left", padx=2)
        ctk.CTkButton(impexp, text="Import JSON", width=86,
                      command=lambda: self._import("json")).pack(side="left", padx=2)
        ctk.CTkButton(impexp, text="Export CSV", width=86,
                      command=lambda: self._export("csv")).pack(side="left", padx=2)
        ctk.CTkButton(impexp, text="Export JSON", width=86,
                      command=lambda: self._export("json")).pack(side="left", padx=2)

        addrow = ctk.CTkFrame(f, fg_color="transparent")
        addrow.pack(fill="x", padx=8, pady=4)
        self.add_kr = ctk.CTkEntry(addrow, placeholder_text="한국어", width=80)
        self.add_kr.pack(side="left", padx=2)
        self.add_romaja = ctk.CTkEntry(addrow, placeholder_text="romaja", width=80)
        self.add_romaja.pack(side="left", padx=2)
        self.add_fr = ctk.CTkEntry(addrow, placeholder_text="français", width=90)
        self.add_fr.pack(side="left", padx=2)
        ctk.CTkButton(addrow, text="+", width=30,
                      command=self._add_card).pack(side="left", padx=2)

        self.deck_list = ctk.CTkFrame(f, fg_color="transparent")
        self.deck_list.pack(fill="x", padx=8, pady=(4, 8))
        self._render_deck()

    # ---- session ----
    def start_session(self):
        self._queue = list(self.deck.due_cards())
        self._next_card()

    def _next_card(self):
        self._revealed = False
        if not self._queue:
            self._current = None
            self.card_kr.configure(text="✓")
            self.card_romaja.configure(text="")
            self.card_answer.configure(text="Rien à réviser pour l'instant.")
            self.session_info.configure(text="")
            return
        self._current = self._queue[0]
        self.card_kr.configure(text=self._current.get("kr", "—"))
        self.card_romaja.configure(text="")
        self.card_answer.configure(text="")
        self.session_info.configure(text=f"{len(self._queue)} carte(s) en file")

    def _reveal(self):
        if not self._current:
            return
        self._revealed = True
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
        cards = self.deck.cards()
        for i, c in enumerate(cards):
            row = ctk.CTkFrame(self.deck_list, fg_color="transparent")
            row.pack(fill="x", pady=1)
            txt = f"{c.get('kr', '')}  ·  {c.get('fr', '')}"
            ctk.CTkLabel(row, text=txt, anchor="w").pack(
                side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="✕", width=26, fg_color="#7a3b3b",
                          command=lambda i=i: self._del_card(i)).pack(side="left")

    def _del_card(self, i):
        self.deck.remove(i)
        self._render_deck()

    # ---- import / export ----
    def _export(self, kind):
        ext = "csv" if kind == "csv" else "json"
        path = filedialog.asksaveasfilename(
            defaultextension=f".{ext}",
            filetypes=[(ext.upper(), f"*.{ext}")])
        if not path:
            return
        try:
            data = (self.deck.export_csv() if kind == "csv"
                    else self.deck.export_json())
            with open(path, "w", encoding="utf-8") as f:
                f.write(data)
        except Exception as e:
            messagebox.showerror("Export", str(e))

    def _import(self, kind):
        ext = "csv" if kind == "csv" else "json"
        path = filedialog.askopenfilename(
            filetypes=[(ext.upper(), f"*.{ext}")])
        if not path:
            return
        replace = messagebox.askyesno(
            "Import", "Remplacer le deck existant ?\n(Non = ajouter)")
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            if kind == "csv":
                self.deck.import_csv(text, replace=replace)
            else:
                self.deck.import_json(text, replace=replace)
        except Exception as e:
            messagebox.showerror("Import", str(e))
        self._render_deck()

    def refresh(self, snap):
        pass  # rien de périodique ici
