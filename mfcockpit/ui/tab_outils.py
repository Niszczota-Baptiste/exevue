"""Onglet [Outils] : calculateur de stacks, commandes modo, presse-papier, liens."""
import webbrowser

import customtkinter as ctk

from ..backend import stacks
from . import theme
from .base import ThemedScroll
from .theme import C


def _accent(parent, text, command, width=0, **kw):
    return ctk.CTkButton(parent, text=text, command=command, width=width,
                         fg_color=C["accent"], hover_color=C["accent_dk"],
                         text_color="#f6f2ff", border_width=0,
                         font=theme.font("head", 11, "bold"), **kw)


class OutilsTab(ThemedScroll):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.clipboard = app.clipboard
        self._clip_sig = None
        self._build()

    def _build(self):
        self._build_stacks()
        self._build_modo()
        self._build_clipboard()
        self._build_links()

    # ---- 6) calculateur de stacks ----
    def _build_stacks(self):
        f = self._section("Calculateur de stacks")
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(row, text="Nombre", font=theme.font("body", 13),
                     text_color=C["muted"]).pack(side="left")
        self.stack_input = ctk.CTkEntry(row, width=120, font=theme.font("mono", 14))
        self.stack_input.pack(side="left", padx=8)
        self.stack_input.bind("<KeyRelease>", lambda e: self._calc_stacks())

        row2 = ctk.CTkFrame(f, fg_color="transparent")
        row2.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(row2, text="taille stack", font=theme.font("head", 10, "bold"),
                     text_color=C["muted"]).pack(side="left")
        self.stack_size = ctk.CTkEntry(row2, width=52, justify="center",
                                       font=theme.font("mono", 13))
        self.stack_size.insert(0, str(self.cfg.get("stack.size", 64)))
        self.stack_size.pack(side="left", padx=(4, 12))
        ctk.CTkLabel(row2, text="slots/coffre", font=theme.font("head", 10, "bold"),
                     text_color=C["muted"]).pack(side="left")
        self.chest_slots = ctk.CTkEntry(row2, width=52, justify="center",
                                        font=theme.font("mono", 13))
        self.chest_slots.insert(0, str(self.cfg.get("stack.chest_slots", 27)))
        self.chest_slots.pack(side="left", padx=4)
        for e in (self.stack_size, self.chest_slots):
            e.bind("<KeyRelease>", lambda ev: self._calc_stacks())

        out = ctk.CTkFrame(f, fg_color=C["inset"], corner_radius=8,
                           border_color=C["inset_border"], border_width=1)
        out.pack(fill="x")
        self.stack_out = ctk.CTkLabel(out, text="=  …", anchor="w", justify="left",
                                      font=theme.font("mono", 13),
                                      text_color=C["accent_lt2"])
        self.stack_out.pack(fill="x", padx=10, pady=8)

    def _calc_stacks(self):
        try:
            n = int(self.stack_input.get())
        except ValueError:
            self.stack_out.configure(text="=  …")
            return
        try:
            size = int(self.stack_size.get())
            self.cfg.set("stack.size", size)
        except ValueError:
            size = 64
        try:
            slots = int(self.chest_slots.get())
            self.cfg.set("stack.chest_slots", slots)
        except ValueError:
            slots = 27
        self.stack_out.configure(text="=  " + stacks.describe(n, size, slots))

    # ---- 7) commandes modo ----
    def _build_modo(self):
        f = self._section("Commandes modo")
        self.modo_frame = ctk.CTkFrame(f, fg_color="transparent")
        self.modo_frame.pack(fill="x", pady=(0, 6))
        _accent(f, "+  Ajouter une commande", self._modo_add, height=28).pack(
            fill="x")
        self._render_modo()

    def _render_modo(self):
        for w in self.modo_frame.winfo_children():
            w.destroy()
        self._modo_entries = []
        cmds = self.cfg.get("modo_commands", []) or []
        for i, cmd in enumerate(cmds):
            row = ctk.CTkFrame(self.modo_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            entry = ctk.CTkEntry(row, font=theme.font("mono", 12))
            entry.insert(0, cmd)
            entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
            entry.bind("<FocusOut>", lambda e: self._modo_save())
            entry.bind("<Return>", lambda e: self._modo_save())
            self._modo_entries.append(entry)
            ctk.CTkButton(row, text="📋", width=30,
                          command=lambda i=i: self._modo_copy(i)).pack(side="left", padx=1)
            ctk.CTkButton(row, text="↑", width=26,
                          command=lambda i=i: self._modo_move(i, -1)).pack(side="left", padx=1)
            ctk.CTkButton(row, text="↓", width=26,
                          command=lambda i=i: self._modo_move(i, 1)).pack(side="left", padx=1)
            ctk.CTkButton(row, text="✕", width=26, fg_color="#5a2740",
                          hover_color="#7a3b3b",
                          command=lambda i=i: self._modo_del(i)).pack(side="left", padx=1)

    def _modo_save(self):
        self.cfg.set("modo_commands",
                     [e.get() for e in getattr(self, "_modo_entries", [])])

    def _modo_copy(self, i):
        if 0 <= i < len(self._modo_entries):
            self.clipboard.set_clipboard(self._modo_entries[i].get())

    def _modo_add(self):
        cmds = self.cfg.get("modo_commands", []) or []
        cmds.append("/commande <args>")
        self.cfg.set("modo_commands", cmds)
        self._render_modo()

    def _modo_del(self, i):
        self._modo_save()
        cmds = self.cfg.get("modo_commands", []) or []
        if 0 <= i < len(cmds):
            cmds.pop(i)
            self.cfg.set("modo_commands", cmds)
        self._render_modo()

    def _modo_move(self, i, d):
        self._modo_save()
        cmds = self.cfg.get("modo_commands", []) or []
        j = i + d
        if 0 <= i < len(cmds) and 0 <= j < len(cmds):
            cmds[i], cmds[j] = cmds[j], cmds[i]
            self.cfg.set("modo_commands", cmds)
        self._render_modo()

    # ---- 8) presse-papier ----
    def _build_clipboard(self):
        f = self._section("Presse-papier")
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", pady=(0, 6))
        self.clip_pause = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(row, text="Pause", variable=self.clip_pause,
                      command=self._clip_toggle_pause, width=68,
                      font=theme.font("body", 12)).pack(side="left")
        self.clip_persist = ctk.BooleanVar(
            value=bool(self.cfg.get("clipboard.persist", False)))
        ctk.CTkSwitch(row, text="Persister", variable=self.clip_persist,
                      command=self._clip_toggle_persist, width=92,
                      font=theme.font("body", 12)).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Vider", width=58, command=self._clip_clear,
                      fg_color="#5a2740", hover_color="#7a3b3b",
                      font=theme.font("head", 11, "bold")).pack(side="right")
        ctk.CTkLabel(row, text="N", font=theme.font("head", 10, "bold"),
                     text_color=C["muted"]).pack(side="right", padx=(8, 2))
        self.clip_max = ctk.CTkEntry(row, width=44, justify="center",
                                     font=theme.font("mono", 13))
        self.clip_max.insert(0, str(self.cfg.get("clipboard.max_items", 20)))
        self.clip_max.pack(side="right")
        self.clip_max.bind("<Return>", lambda e: self._clip_save_max())
        self.clip_max.bind("<FocusOut>", lambda e: self._clip_save_max())

        self.clip_list = ctk.CTkFrame(f, fg_color="transparent")
        self.clip_list.pack(fill="x")

    def _clip_toggle_pause(self):
        self.clipboard.paused = bool(self.clip_pause.get())

    def _clip_toggle_persist(self):
        self.cfg.set("clipboard.persist", bool(self.clip_persist.get()))

    def _clip_save_max(self):
        try:
            self.cfg.set("clipboard.max_items", int(self.clip_max.get()))
        except ValueError:
            pass

    def _clip_clear(self):
        self.clipboard.clear()
        self._render_clipboard(force=True)

    def _render_clipboard(self, force=False):
        items = self.clipboard.items()
        sig = tuple(items)
        if not force and sig == self._clip_sig:
            return
        self._clip_sig = sig
        for w in self.clip_list.winfo_children():
            w.destroy()
        if not items:
            ctk.CTkLabel(self.clip_list, text="(vide)", text_color=C["dim"],
                         font=theme.font("body", 12)).pack(anchor="w")
            return
        for text in items:
            preview = text.replace("\n", " ⏎ ")
            if len(preview) > 46:
                preview = preview[:46] + "…"
            ctk.CTkButton(self.clip_list, text=preview, anchor="w", height=26,
                          font=theme.font("mono", 11),
                          command=lambda t=text: self.clipboard.set_clipboard(t)
                          ).pack(fill="x", pady=1)

    # ---- 9) liens rapides ----
    def _build_links(self):
        f = self._section("Liens rapides")
        self.links_list = ctk.CTkFrame(f, fg_color="transparent")
        self.links_list.pack(fill="x", pady=(0, 6))
        addrow = ctk.CTkFrame(f, fg_color="transparent")
        addrow.pack(fill="x")
        self.link_label = ctk.CTkEntry(addrow, placeholder_text="libellé", width=110,
                                       font=theme.font("body", 12))
        self.link_label.pack(side="left", padx=(0, 4))
        self.link_url = ctk.CTkEntry(addrow, placeholder_text="https://…",
                                     font=theme.font("body", 12))
        self.link_url.pack(side="left", fill="x", expand=True, padx=(0, 4))
        _accent(addrow, "+", self._link_add, width=36).pack(side="left")
        self._render_links()

    def _render_links(self):
        for w in self.links_list.winfo_children():
            w.destroy()
        links = self.cfg.get("quick_links", []) or []
        for i, link in enumerate(links):
            row = ctk.CTkFrame(self.links_list, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkButton(row, text=link.get("label", "?"), anchor="w",
                          font=theme.font("head", 12, "bold"),
                          command=lambda u=link.get("url", ""): webbrowser.open(u)
                          ).pack(side="left", fill="x", expand=True, padx=(0, 4))
            ctk.CTkButton(row, text="✕", width=26, fg_color="#5a2740",
                          hover_color="#7a3b3b",
                          command=lambda i=i: self._link_del(i)).pack(side="left")

    def _link_add(self):
        label = self.link_label.get().strip()
        url = self.link_url.get().strip()
        if not label or not url:
            return
        links = self.cfg.get("quick_links", []) or []
        links.append({"label": label, "url": url})
        self.cfg.set("quick_links", links)
        self.link_label.delete(0, "end")
        self.link_url.delete(0, "end")
        self._render_links()

    def _link_del(self, i):
        links = self.cfg.get("quick_links", []) or []
        if 0 <= i < len(links):
            links.pop(i)
            self.cfg.set("quick_links", links)
        self._render_links()

    def refresh(self, snap):
        self._render_clipboard()
