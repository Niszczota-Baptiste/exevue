"""Détection du client + suivi temps solo/multi (réutilise mf_tracker.py).

Étendu à une persistance PAR JOUR : `days[YYYY-MM-DD] = {solo, multi}`, en plus
des totaux globaux. Le poller appelle `tick(elapsed)` à chaque cycle.
"""
import json
import os
import socket
import time
from datetime import date, datetime, timedelta

from . import paths

try:
    import psutil
except Exception:  # pragma: no cover - psutil requis en prod
    psutil = None


def fmt(seconds) -> str:
    return str(timedelta(seconds=int(max(0, seconds))))


def resolve_server_endpoints(host: str, default_port: int = 25565):
    """IPs + ports du serveur, en tenant compte de l'enregistrement SRV.

    Un client Minecraft résout `_minecraft._tcp.<host>` (SRV) : la cible a
    souvent une IP/un port différents de `host:25565`. On agrège tout pour
    reconnaître la connexion multi quel que soit le routage.
    """
    ips, ports = set(), {int(default_port)}
    hosts = {host}

    # SRV (best-effort, via dnspython fourni par mcstatus)
    try:
        import dns.resolver  # type: ignore
        ans = dns.resolver.resolve(f"_minecraft._tcp.{host}", "SRV")
        for r in ans:
            target = str(r.target).rstrip(".")
            if target:
                hosts.add(target)
            ports.add(int(r.port))
    except Exception:
        pass

    for h in hosts:
        try:
            _, _, addrs = socket.gethostbyname_ex(h)
            ips.update(addrs)
        except Exception:
            pass
    return ips, ports


def resolve_server_ips(host: str):
    """Compat : ne renvoie que les IPs (ancienne signature)."""
    return resolve_server_endpoints(host)[0]


def find_mc_process():
    """Cherche le client Minecraft/Minefield (javaw lançant le client)."""
    if psutil is None:
        return None
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (p.info["name"] or "").lower()
            if name not in ("javaw.exe", "java.exe", "java"):
                continue
            cmd = " ".join(p.info["cmdline"] or "").lower()
            if ("minefield" in cmd or ".minefield_1_18" in cmd
                    or "net.minecraft.client.main.main" in cmd):
                return p
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        except Exception:
            continue
    return None


def _proc_connections(proc):
    """Connexions du process, avec repli sur un scan système si refusé."""
    try:
        return proc.net_connections(kind="inet")
    except Exception:
        pass
    # Repli : certains environnements refusent net_connections() par process.
    try:
        return [c for c in psutil.net_connections(kind="inet")
                if c.pid == proc.pid]
    except Exception:
        return []


def current_mode(proc, server_ips, server_ports) -> str:
    """multi si une connexion établie vers le serveur (IP ou port SRV)."""
    if isinstance(server_ports, int):
        server_ports = {server_ports}
    for c in _proc_connections(proc):
        try:
            if c.status == psutil.CONN_ESTABLISHED and c.raddr:
                if c.raddr.ip in server_ips or c.raddr.port in server_ports:
                    return "multi"
        except Exception:
            continue
    return "solo"


class Tracker:
    def __init__(self, config):
        self.config = config
        self._state = self._load()
        self._server_ips = set()
        self._server_ports = {25565}
        self._ips_resolved_at = 0.0
        # session courante (depuis lancement de l'app)
        self.session = {"solo": 0.0, "multi": 0.0}
        self.playing = False
        self.mode = None  # "solo" | "multi" | None
        # durée de jeu continue (pour le rappel pause)
        self.continuous_seconds = 0.0
        self._last_save = 0.0

    # ---- persistance ----
    def _load(self) -> dict:
        try:
            with open(paths.PLAYTIME_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            d = {}
        d.setdefault("solo_seconds", 0.0)
        d.setdefault("multi_seconds", 0.0)
        d.setdefault("sessions", [])
        d.setdefault("days", {})  # "YYYY-MM-DD" -> {"solo": s, "multi": s}
        return d

    def save(self):
        tmp = paths.PLAYTIME_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False, indent="\t")
            os.replace(tmp, paths.PLAYTIME_FILE)
        except Exception:
            pass

    # ---- cycle ----
    def _server_endpoints_cached(self):
        host = self.config.get("server.host", "minefield.fr")
        port = int(self.config.get("server.port", 25565))
        now = time.time()
        if now - self._ips_resolved_at > 300 or not self._server_ips:
            self._server_ips, self._server_ports = resolve_server_endpoints(host, port)
            self._ips_resolved_at = now
        return self._server_ips, self._server_ports

    def tick(self, elapsed: float):
        """Attribue `elapsed` secondes au mode courant si le jeu tourne."""
        proc = find_mc_process()
        if proc is None:
            self.playing = False
            self.mode = None
            self.continuous_seconds = 0.0
        else:
            ips, ports = self._server_endpoints_cached()
            mode = current_mode(proc, ips, ports)
            self.playing = True
            self.mode = mode
            self.continuous_seconds += elapsed
            self.session[mode] += elapsed
            self._state[f"{mode}_seconds"] += elapsed
            day = date.today().isoformat()
            d = self._state["days"].setdefault(day, {"solo": 0.0, "multi": 0.0})
            d[mode] += elapsed

        self._prune_days()
        now = time.time()
        if now - self._last_save > 30:
            self.save()
            self._last_save = now

    def _prune_days(self, keep_days: int = 90):
        days = self._state.get("days", {})
        if len(days) <= keep_days:
            return
        cutoff = (date.today() - timedelta(days=keep_days)).isoformat()
        for k in [k for k in days if k < cutoff]:
            days.pop(k, None)

    def end_session(self):
        if self.session["solo"] + self.session["multi"] > 0:
            self._state["sessions"].append({
                "fin": time.strftime("%Y-%m-%d %H:%M"),
                "solo": int(self.session["solo"]),
                "multi": int(self.session["multi"]),
            })
        self.save()

    # ---- agrégats pour l'UI ----
    @property
    def total_solo(self):
        return self._state["solo_seconds"]

    @property
    def total_multi(self):
        return self._state["multi_seconds"]

    def today(self):
        d = self._state["days"].get(date.today().isoformat(), {})
        return float(d.get("solo", 0.0)), float(d.get("multi", 0.0))

    def last_n_days(self, n: int = 7):
        """Liste [(label, solo, multi)] du plus ancien au plus récent."""
        out = []
        for i in range(n - 1, -1, -1):
            day = (date.today() - timedelta(days=i))
            d = self._state["days"].get(day.isoformat(), {})
            out.append((day.strftime("%a"), float(d.get("solo", 0.0)),
                        float(d.get("multi", 0.0))))
        return out

    def week_stats(self):
        rows = self.last_n_days(7)
        solo = sum(r[1] for r in rows)
        multi = sum(r[2] for r in rows)
        total = solo + multi
        avg_per_day = total / 7.0
        ratio = (solo / multi) if multi > 0 else float("inf") if solo > 0 else 0.0
        return {"solo": solo, "multi": multi, "total": total,
                "avg_per_day": avg_per_day, "ratio": ratio}
