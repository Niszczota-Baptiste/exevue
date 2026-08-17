"""Config persistante (config.json à côté de l'exe).

Un seul objet Config partagé. `get`/`set` lisent/écrivent des chemins pointés
("server.host"). Chaque `set`/`save` réécrit immédiatement le fichier : tout
réglage modifié dans l'UI est persisté sans recompiler.
"""
import copy
import json
import os
import threading
import time

from . import paths

# Seed ~10 mots coréens (mot KR, romanisation, FR, exemple) + champs SRS.
_KOREAN_SEED = [
    ("안녕하세요", "annyeonghaseyo", "bonjour", "안녕하세요, 잘 지내요?"),
    ("감사합니다", "gamsahamnida", "merci", "도와줘서 감사합니다."),
    ("네", "ne", "oui", "네, 맞아요."),
    ("아니요", "aniyo", "non", "아니요, 괜찮아요."),
    ("물", "mul", "eau", "물 좀 주세요."),
    ("사랑", "sarang", "amour", "사랑해요."),
    ("친구", "chingu", "ami", "제 친구예요."),
    ("학교", "hakgyo", "école", "학교에 가요."),
    ("밥", "bap", "repas / riz", "밥 먹었어요?"),
    ("시간", "sigan", "temps / heure", "시간이 없어요."),
]


def _seed_deck():
    now = time.time()
    deck = []
    for kr, romaja, fr, example in _KOREAN_SEED:
        deck.append({
            "kr": kr, "romaja": romaja, "fr": fr, "example": example,
            "due": now, "interval": 0.0, "ease": 2.5, "reps": 0,
            "history": [],
        })
    return deck


def default_config() -> dict:
    return {
        "server": {"host": "minefield.fr", "port": 25565},
        "discord_guild_id": "",
        "poll_seconds": 20,
        "always_on_top": False,
        "window_geometry": "440x820",
        # Latence (ms) : <= good = vert, <= warn = orange, > warn = rouge.
        "latency": {"good_ms": 60, "warn_ms": 120, "tcp_timeout_ms": 1500},
        # Alerte joueurs : notif au franchissement seulement.
        "player_alert": {"enabled": True, "low": 2, "high": 30},
        "break_reminder_hours": 2.0,
        "stack": {"size": 64, "chest_slots": 27},
        "clipboard": {"max_items": 20, "persist": False, "poll_seconds": 1.0},
        "site_health_url": "https://baptiste-niszczota.com/health",
        # Flux « cockpit » du site (quêtes + wanted) : URL secrète par membre,
        # à copier depuis le bouton « 🛰️ Cockpit MF » de /quetes.
        "quests_feed": {"url": "", "poll_seconds": 300, "notify": True},
        "mf_links": [
            {"label": "Money", "url": "https://www.minefield.fr/money.php"},
            {"label": "Carto", "url": "https://www.minefield.fr/carto.php"},
            {"label": "Panneaux", "url": "https://www.minefield.fr/panneaux.php"},
        ],
        "quick_links": [
            {"label": "Mes coffres", "url": "https://baptiste-niszczota.com"},
        ],
        "modo_commands": [
            "/kick <joueur> <raison>",
            "/mute <joueur> <durée>",
            "/tp <joueur>",
            "/warn <joueur> <raison>",
            "/ban <joueur> <raison>",
        ],
        "korean": {"words_per_session": 3, "deck": _seed_deck()},
    }


def _deep_merge(base: dict, override: dict) -> dict:
    """Complète `override` avec les clés manquantes de `base` (récursif)."""
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    def __init__(self, path: str = paths.CONFIG_FILE):
        self._path = path
        self._lock = threading.RLock()
        self._data = default_config()
        self.load()

    # ---- IO ----
    def load(self):
        with self._lock:
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    disk = json.load(f)
                # Fusionne avec les défauts : nouveaux réglages dispos sans casser.
                self._data = _deep_merge(default_config(), disk)
            except FileNotFoundError:
                self.save()
            except Exception:
                # Fichier corrompu : on garde les défauts, on n'écrase pas tout de suite.
                self._data = default_config()

    def save(self):
        with self._lock:
            data = copy.deepcopy(self._data)
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent="\t")
            os.replace(tmp, self._path)
        except Exception:
            pass  # disque plein / lecture seule : dégradation silencieuse

    # ---- accès ----
    def get(self, dotted: str, default=None):
        with self._lock:
            node = self._data
            for part in dotted.split("."):
                if not isinstance(node, dict) or part not in node:
                    return default
                node = node[part]
            return copy.deepcopy(node)

    def set(self, dotted: str, value):
        with self._lock:
            node = self._data
            parts = dotted.split(".")
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = value
        self.save()

    def snapshot(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._data)
