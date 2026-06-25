"""Thread de fond unique : TOUT le réseau/IO périodique.

- Ping serveur + latence, widget Discord, santé site, présences, média SMTC :
  toutes les `poll_seconds` (config).
- Presse-papier : poll léger à chaque base-tick (1 s).
- Publie un snapshot thread-safe ; l'UI ne fait que le lire (jamais de réseau).
- CPU ~0 entre deux ticks (sommeil court), erreurs réseau silencieuses.
- Gère les stats de latence glissantes, l'alerte seuil joueurs (anti-spam au
  franchissement) et le rappel pause.
"""
import threading
import time
from collections import deque

from . import discord, history, media, notify, server, site


class Poller:
    def __init__(self, config, tracker, clipboard):
        self.config = config
        self.tracker = tracker
        self.clipboard = clipboard

        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._snapshot = {}

        # latence glissante (≈ 1 h à POLL=20s -> 180 échantillons)
        self._lat_samples = deque(maxlen=200)
        self._loss = deque(maxlen=200)  # 1 = perte (timeout), 0 = ok

        # état alerte joueurs + rappel pause
        self._player_zone = None      # "high" | "low" | "mid"
        self._break_notified = False

        self._last_heavy = 0.0

    # ---- cycle de vie ----
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="mf-poller")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    # ---- snapshot ----
    def get_snapshot(self) -> dict:
        with self._lock:
            return dict(self._snapshot)

    def _publish(self, **kw):
        with self._lock:
            self._snapshot.update(kw)
            self._snapshot["ts"] = time.time()

    # ---- boucle ----
    def _run(self):
        # premier tick tout de suite
        self._last_heavy = 0.0
        last_clip = 0.0
        while not self._stop.is_set():
            now = time.time()
            clip_every = float(self.config.get("clipboard.poll_seconds", 1.0))
            if now - last_clip >= clip_every:
                try:
                    self.clipboard.poll()
                except Exception:
                    pass
                last_clip = now

            poll_seconds = max(5, int(self.config.get("poll_seconds", 20)))
            if now - self._last_heavy >= poll_seconds:
                elapsed = (now - self._last_heavy) if self._last_heavy else 0.0
                self._last_heavy = now
                try:
                    self._heavy_tick(elapsed)
                except Exception:
                    pass  # erreurs réseau/IO silencieuses

            # sommeil court : CPU ~0 entre deux ticks, réactif au stop
            self._stop.wait(0.5)

    def _heavy_tick(self, elapsed: float):
        cfg = self.config
        host = cfg.get("server.host", "minefield.fr")
        port = int(cfg.get("server.port", 25565))

        # 1) temps de jeu (psutil) — local mais IO, donc sur ce thread
        try:
            self.tracker.tick(elapsed)
        except Exception:
            pass

        # 2) statut serveur + latence
        srv = server.server_status(host, port)
        tcp_timeout = float(cfg.get("latency.tcp_timeout_ms", 1500)) / 1000.0
        tcp_ms = server.tcp_connect_ms(host, port, timeout=tcp_timeout)

        latency_ms = None
        if srv and srv.get("latency_ms") is not None:
            latency_ms = srv["latency_ms"]
        elif tcp_ms is not None:
            latency_ms = tcp_ms

        # perte = aucune mesure obtenue ce tick
        lost = 1 if (latency_ms is None and tcp_ms is None) else 0
        self._loss.append(lost)
        if latency_ms is not None:
            self._lat_samples.append(latency_ms)
        lat_stats = self._latency_stats(latency_ms)

        # 3) Discord (widget public)
        dis = discord.discord_widget(cfg.get("discord_guild_id", ""))

        # 4) santé site
        site_url = cfg.get("site_health_url", "")
        site_st = site.site_health(site_url) if site_url else None

        # 5) média SMTC (async, exécuté ici)
        med = media.poll()

        # 6) histo fréquentation
        if srv:
            try:
                history.log_players(srv["online"])
            except Exception:
                pass

        # 7) alertes
        if srv:
            self._check_player_alert(srv["online"])
        self._check_break_reminder()

        self._publish(
            server=srv, tcp_ms=tcp_ms, discord=dis, site=site_st, media=med,
            latency=lat_stats, playing=self.tracker.playing,
            mode=self.tracker.mode,
        )

    # ---- latence ----
    def _latency_stats(self, current):
        samples = list(self._lat_samples)
        loss = list(self._loss)
        stats = {
            "current_ms": current,
            "min": min(samples) if samples else None,
            "avg": (sum(samples) / len(samples)) if samples else None,
            "max": max(samples) if samples else None,
            "samples": len(samples),
            "loss_pct": (100.0 * sum(loss) / len(loss)) if loss else 0.0,
        }
        good = float(self.config.get("latency.good_ms", 60))
        warn = float(self.config.get("latency.warn_ms", 120))
        if current is None:
            stats["color"] = "red"
        elif current <= good:
            stats["color"] = "green"
        elif current <= warn:
            stats["color"] = "orange"
        else:
            stats["color"] = "red"
        return stats

    # ---- alerte joueurs (anti-spam : seulement au franchissement) ----
    def _check_player_alert(self, online: int):
        if not self.config.get("player_alert.enabled", True):
            self._player_zone = None
            return
        low = int(self.config.get("player_alert.low", 2))
        high = int(self.config.get("player_alert.high", 30))
        if online >= high:
            zone = "high"
        elif online <= low:
            zone = "low"
        else:
            zone = "mid"

        if self._player_zone is None:
            self._player_zone = zone  # premier relevé : pas de notif
            return
        if zone != self._player_zone:
            if zone == "high":
                notify.notify("Minefield — affluence",
                              f"{online} joueurs en ligne (seuil haut {high}).")
            elif zone == "low":
                notify.notify("Minefield — calme plat",
                              f"{online} joueurs en ligne (seuil bas {low}).")
            self._player_zone = zone

    # ---- rappel pause ----
    def _check_break_reminder(self):
        hours = float(self.config.get("break_reminder_hours", 2.0))
        if hours <= 0:
            return
        if not self.tracker.playing or self.tracker.continuous_seconds <= 0:
            self._break_notified = False
            return
        if (self.tracker.continuous_seconds >= hours * 3600
                and not self._break_notified):
            notify.notify("Pense à faire une pause",
                          f"{hours:g} h de jeu d'affilée. Étire-toi un peu !")
            self._break_notified = True
