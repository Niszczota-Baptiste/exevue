"""Statut serveur (SLP via mcstatus) + latence.

Réutilise le champ `latency` renvoyé par mcstatus, et mesure en complément un
temps de connexion TCP vers :25565 par tick comme indicateur de perte.
"""
import socket
import time

try:
    from mcstatus import JavaServer
except Exception:  # pragma: no cover
    JavaServer = None


def server_status(host: str, port: int, timeout: float = 4.0):
    """Renvoie {online, max, sample, latency_ms} ou None si injoignable."""
    if JavaServer is None:
        return None
    try:
        srv = JavaServer.lookup(f"{host}:{port}", timeout=timeout)
        st = srv.status()
        sample = [pl.name for pl in (st.players.sample or [])]
        latency = getattr(st, "latency", None)
        return {
            "online": st.players.online,
            "max": st.players.max,
            "sample": sample,
            "latency_ms": float(latency) if latency is not None else None,
        }
    except Exception:
        return None


def tcp_connect_ms(host: str, port: int, timeout: float = 1.5):
    """Temps d'établissement TCP en ms, ou None si timeout/échec (= perte)."""
    start = time.perf_counter()
    s = None
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        return (time.perf_counter() - start) * 1000.0
    except Exception:
        return None
    finally:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass
