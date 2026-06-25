"""Gestionnaire d'historique du presse-papier.

Poll léger (pyperclip si dispo, sinon Tk). Garde les N derniers extraits.
En mémoire par défaut ; persiste vers clipboard.json si l'option est active.
N'historise pas tant que `paused` est vrai.
"""
import json
import threading

from . import paths

try:
    import pyperclip
except Exception:
    pyperclip = None


class ClipboardManager:
    def __init__(self, config, tk_root_getter=None):
        self.config = config
        self._lock = threading.Lock()
        self._items = []          # plus récent en tête
        self._last_seen = None
        self.paused = False
        self._tk_root_getter = tk_root_getter  # fallback lecture via Tk
        if config.get("clipboard.persist", False):
            self._load()

    # ---- lecture brute du presse-papier ----
    def _read_clipboard(self):
        if pyperclip is not None:
            try:
                return pyperclip.paste()
            except Exception:
                return None
        if self._tk_root_getter is not None:
            try:
                root = self._tk_root_getter()
                if root is not None:
                    return root.clipboard_get()
            except Exception:
                return None
        return None

    def set_clipboard(self, text: str):
        if pyperclip is not None:
            try:
                pyperclip.copy(text)
                self._last_seen = text  # évite de re-historiser notre propre copie
                return True
            except Exception:
                return False
        if self._tk_root_getter is not None:
            try:
                root = self._tk_root_getter()
                if root is not None:
                    root.clipboard_clear()
                    root.clipboard_append(text)
                    self._last_seen = text
                    return True
            except Exception:
                return False
        return False

    # ---- poll (appelé par le thread de fond) ----
    def poll(self):
        if self.paused:
            return
        text = self._read_clipboard()
        if not text or text == self._last_seen:
            return
        self._last_seen = text
        with self._lock:
            if self._items and self._items[0] == text:
                return
            self._items = [x for x in self._items if x != text]
            self._items.insert(0, text)
            max_items = int(self.config.get("clipboard.max_items", 20))
            del self._items[max_items:]
        if self.config.get("clipboard.persist", False):
            self._save()

    # ---- accès UI ----
    def items(self):
        with self._lock:
            return list(self._items)

    def clear(self):
        with self._lock:
            self._items = []
        if self.config.get("clipboard.persist", False):
            self._save()

    # ---- persistance optionnelle ----
    def _load(self):
        try:
            with open(paths.CLIPBOARD_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._items = [str(x) for x in data]
        except Exception:
            pass

    def _save(self):
        tmp = paths.CLIPBOARD_FILE + ".tmp"
        try:
            with self._lock:
                data = list(self._items)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent="\t")
            import os
            os.replace(tmp, paths.CLIPBOARD_FILE)
        except Exception:
            pass
