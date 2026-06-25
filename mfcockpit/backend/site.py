"""Santé du site (GET sur une URL /health configurable)."""
import time
import urllib.error
import urllib.request


def site_health(url: str, timeout: float = 5.0):
    """Renvoie {up:bool, status:int|None, ms:float|None}."""
    if not url:
        return {"up": False, "status": None, "ms": None}
    start = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "mf-cockpit"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = getattr(r, "status", None) or r.getcode()
        ms = (time.perf_counter() - start) * 1000.0
        return {"up": 200 <= int(code) < 400, "status": int(code), "ms": ms}
    except urllib.error.HTTPError as e:
        ms = (time.perf_counter() - start) * 1000.0
        return {"up": False, "status": int(e.code), "ms": ms}
    except Exception:
        return {"up": False, "status": None, "ms": None}
