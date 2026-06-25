"""Flashcards coréen — répétition espacée (SM-2 allégé).

Le deck vit dans config.json (korean.deck) : chaque carte porte ses échéances
(due/interval/ease/reps) et son historique. Persistant via la Config.
Import/export CSV/JSON (kr, romaja, fr, example).
"""
import csv
import io
import json
import time

DAY = 86400.0
FIELDS = ("kr", "romaja", "fr", "example")


def _new_card(kr, romaja="", fr="", example=""):
    return {
        "kr": kr, "romaja": romaja, "fr": fr, "example": example,
        "due": time.time(), "interval": 0.0, "ease": 2.5, "reps": 0,
        "history": [],
    }


class Deck:
    def __init__(self, config):
        self.config = config

    # ---- accès deck ----
    def cards(self):
        return self.config.get("korean.deck", []) or []

    def _save(self, cards):
        self.config.set("korean.deck", cards)

    def words_per_session(self):
        return int(self.config.get("korean.words_per_session", 3))

    # ---- sélection des cartes dues ----
    def due_cards(self, limit=None, now=None):
        now = time.time() if now is None else now
        limit = self.words_per_session() if limit is None else limit
        due = [c for c in self.cards() if float(c.get("due", 0)) <= now]
        due.sort(key=lambda c: float(c.get("due", 0)))
        return due[:limit]

    # ---- notation SM-2 allégé ----
    def grade(self, card, knew: bool, now=None):
        """Met à jour l'échéance d'une carte. `knew` = "su" / "pas su"."""
        now = time.time() if now is None else now
        cards = self.cards()
        # retrouve la carte par identité de contenu KR
        idx = next((i for i, c in enumerate(cards)
                    if c.get("kr") == card.get("kr")), None)
        if idx is None:
            return
        c = cards[idx]
        ease = float(c.get("ease", 2.5))
        reps = int(c.get("reps", 0))

        if knew:
            reps += 1
            if reps == 1:
                interval = 1 * DAY
            elif reps == 2:
                interval = 3 * DAY
            else:
                interval = float(c.get("interval", DAY)) * ease
            ease = min(3.0, ease + 0.1)
        else:
            reps = 0
            interval = 10 * 60.0  # 10 min : on revoit vite
            ease = max(1.3, ease - 0.2)

        c["reps"] = reps
        c["ease"] = round(ease, 3)
        c["interval"] = interval
        c["due"] = now + interval
        c.setdefault("history", []).append(
            {"t": int(now), "knew": bool(knew)})
        c["history"] = c["history"][-50:]
        cards[idx] = c
        self._save(cards)

    # ---- édition deck ----
    def add(self, kr, romaja="", fr="", example=""):
        cards = self.cards()
        cards.append(_new_card(kr.strip(), romaja.strip(), fr.strip(), example.strip()))
        self._save(cards)

    def update(self, index, kr, romaja, fr, example):
        cards = self.cards()
        if 0 <= index < len(cards):
            cards[index].update({"kr": kr, "romaja": romaja, "fr": fr,
                                 "example": example})
            self._save(cards)

    def remove(self, index):
        cards = self.cards()
        if 0 <= index < len(cards):
            cards.pop(index)
            self._save(cards)

    # ---- import / export ----
    def export_json(self) -> str:
        return json.dumps(self.cards(), ensure_ascii=False, indent="\t")

    def export_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(FIELDS)
        for c in self.cards():
            w.writerow([c.get(k, "") for k in FIELDS])
        return buf.getvalue()

    def import_json(self, text: str, replace=False):
        data = json.loads(text)
        cards = [] if replace else self.cards()
        for item in data:
            if not isinstance(item, dict) or not item.get("kr"):
                continue
            card = _new_card(item.get("kr", ""), item.get("romaja", ""),
                             item.get("fr", ""), item.get("example", ""))
            # conserve l'ordonnancement s'il est fourni
            for k in ("due", "interval", "ease", "reps", "history"):
                if k in item:
                    card[k] = item[k]
            cards.append(card)
        self._save(cards)

    def import_csv(self, text: str, replace=False):
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if rows and [h.strip().lower() for h in rows[0]][:1] == ["kr"]:
            rows = rows[1:]
        cards = [] if replace else self.cards()
        for row in rows:
            if not row or not row[0].strip():
                continue
            row = (row + ["", "", "", ""])[:4]
            cards.append(_new_card(*[x.strip() for x in row]))
        self._save(cards)
