"""Serveur HTTP local — sert la page mobile et l'API au téléphone.

Un `ThreadingHTTPServer` sur `0.0.0.0:8790`, dans un **thread daemon** : c'est
le seul thread ajouté au cockpit. Tout est encapsulé pour que **rien ici ne
puisse faire tomber l'app** — port déjà pris, pare-feu, dossier `web/` absent :
`demarrer()` renvoie False, la carte « Accès téléphone » affiche l'état hors
ligne, et le cockpit continue de tourner normalement.

Toutes les routes exigent le jeton (`?t=` ou en-tête `X-Cockpit-Token`), y
compris les fichiers statiques : le panneau n'est pas ouvert à tout le LAN.
"""
import os
import posixpath
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import api, db, paths

PORT_DEFAUT = 8790
EN_TETE_JETON = "X-Cockpit-Token"
COOKIE_JETON = "cockpit_token"

MIME_STATIQUE = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".webmanifest": "application/manifest+json",
}

_serveur = None
_thread = None
_derniere_erreur = None
_derniere_visite = None


# ------------------------------------------------------------ jeton & IP

def jeton() -> str:
    """Jeton d'accès, créé au premier appel et conservé en base."""
    valeur = db.reglage("mobile.token")
    if not valeur:
        valeur = secrets.token_urlsafe(8)
        db.set_reglage("mobile.token", valeur)
    return valeur


def regenerer_jeton() -> str:
    valeur = secrets.token_urlsafe(8)
    db.set_reglage("mobile.token", valeur)
    return valeur


def port() -> int:
    return db.reglage_int("mobile.port", PORT_DEFAUT)


def ip_lan() -> str:
    """IP de la machine sur le LAN. Aucun paquet n'est envoyé : un socket UDP
    « connecté » sert juste à demander au noyau quelle interface il choisirait."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def url() -> str:
    return f"http://{ip_lan()}:{port()}/?t={jeton()}"


# ------------------------------------------------------------- handler

class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "MFCockpit"
    sys_version = ""

    # Pas de spam console : on ne garde que la dernière visite.
    def log_message(self, fmt, *args):
        global _derniere_visite
        _derniere_visite = time.time()

    # ---- utilitaires ----
    def _repondre(self, statut, mime, corps: bytes, cache=None, cookie=None):
        self.send_response(statut)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", cache or "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        try:
            self.wfile.write(corps)
        except (BrokenPipeError, ConnectionResetError):
            pass       # l'iPhone a fermé l'onglet en cours de route

    def _cookie_jeton(self):
        brut = self.headers.get("Cookie") or ""
        for morceau in brut.split(";"):
            cle, _, valeur = morceau.strip().partition("=")
            if cle == COOKIE_JETON:
                return valeur
        return None

    def _jeton_ok(self, params) -> bool:
        """Jeton accepté par query, en-tête **ou cookie**.

        Le cookie n'est pas un confort : `index.html` référence `style.css` et
        `app.js` en relatif, et un navigateur ne recopie pas le `?t=` de la page
        sur ses sous-ressources. Sans cookie, la page se charge nue.
        """
        attendu = jeton()
        fourni = (params.get("t", [None])[0]
                  or self.headers.get(EN_TETE_JETON)
                  or self._cookie_jeton())
        return bool(fourni) and secrets.compare_digest(str(fourni), attendu)

    def _statique(self, chemin: str):
        """Sert `web/`, en refusant tout ce qui sort du dossier."""
        if chemin in ("", "/"):
            chemin = "/index.html"
        relatif = posixpath.normpath(unquote(chemin)).lstrip("/")
        cible = os.path.normpath(os.path.join(paths.WEB_DIR, relatif))
        racine = os.path.normpath(paths.WEB_DIR)
        if not cible.startswith(racine + os.sep) or not os.path.isfile(cible):
            self._repondre(404, "text/plain; charset=utf-8",
                           b"introuvable")
            return
        ext = os.path.splitext(cible)[1].lower()
        try:
            with open(cible, "rb") as fh:
                corps = fh.read()
        except OSError:
            self._repondre(500, "text/plain; charset=utf-8", b"lecture KO")
            return
        # L'app doit pouvoir se recharger après une mise à jour du cockpit :
        # cache long sur les assets, jamais sur la page elle-même.
        cache = ("no-store" if ext == ".html"
                 else "public, max-age=604800, immutable")
        # En servant la page, on dépose le jeton en cookie : les requêtes
        # suivantes (CSS, JS, médias) l'emportent toutes seules.
        cookie = None
        if ext == ".html":
            cookie = (f"{COOKIE_JETON}={jeton()}; Path=/; Max-Age=31536000; "
                      f"SameSite=Strict")
        self._repondre(200, MIME_STATIQUE.get(ext, "application/octet-stream"),
                       corps, cache=cache, cookie=cookie)

    # ---- verbes ----
    def do_GET(self):
        decoupe = urlparse(self.path)
        params = parse_qs(decoupe.query)
        if not self._jeton_ok(params):
            self._repondre(401, "text/plain; charset=utf-8",
                           "Jeton manquant ou invalide.\n"
                           "Rescanne le QR code depuis l'onglet Système."
                           .encode("utf-8"))
            return
        if decoupe.path == "/ouvrir":
            # Cible du bouton « Ouvrir le cockpit » des notifications.
            try:
                from . import notify, rappels
                notify.revenir_au_premier_plan("aujourdhui")
                rappels.marquer_ouvert()
            except Exception:
                pass
            self._repondre(
                200, "text/html; charset=utf-8",
                "<!doctype html><meta charset=utf-8>"
                "<title>MF Cockpit</title>"
                "<body style='background:#0c0a13;color:#e7e2f5;"
                "font:600 18px system-ui;display:grid;place-items:center;"
                "height:100vh;margin:0'>"
                "<p>Cockpit au premier plan — tu peux fermer cet onglet.</p>"
                .encode("utf-8"))
            return
        if decoupe.path.startswith("/api/"):
            plats = {k: v[0] for k, v in params.items()}
            statut, mime, corps = api.traiter(decoupe.path, plats,
                                              methode="GET")
            # Les médias d'exercice ne bougent pas : cache long. Le reste de
            # l'API est de l'état vivant, jamais mis en cache.
            cache = ("public, max-age=604800"
                     if statut == 200 and decoupe.path.startswith("/api/media/")
                     else "no-store")
            self._repondre(statut, mime, corps, cache=cache)
            return
        self._statique(decoupe.path)

    def do_POST(self):
        decoupe = urlparse(self.path)
        params = parse_qs(decoupe.query)
        if not self._jeton_ok(params):
            self._repondre(401, "text/plain; charset=utf-8", b"jeton invalide")
            return
        try:
            taille = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            taille = 0
        corps = self.rfile.read(taille) if taille > 0 else b""
        plats = {k: v[0] for k, v in params.items()}
        statut, mime, sortie = api.traiter(decoupe.path, plats, corps=corps,
                                           methode="POST")
        self._repondre(statut, mime, sortie)


# ------------------------------------------------------------ cycle de vie

def demarrer() -> bool:
    """Lance le serveur. Renvoie False (sans lever) si c'est impossible."""
    global _serveur, _thread, _derniere_erreur
    if actif():
        return True
    _derniere_erreur = None
    try:
        jeton()                                  # garantit qu'il existe
        srv = ThreadingHTTPServer(("0.0.0.0", port()), _Handler)
        srv.daemon_threads = True
        srv.timeout = 5
    except OSError as exc:
        _derniere_erreur = (f"port {port()} indisponible ({exc.strerror or exc})"
                            " — un autre programme l'utilise déjà ?")
        return False
    except Exception as exc:
        _derniere_erreur = str(exc)
        return False

    _serveur = srv
    _thread = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.5},
                               daemon=True, name="mf-webserver")
    _thread.start()
    return True


def arreter():
    global _serveur, _thread
    srv, _serveur = _serveur, None
    if srv is not None:
        try:
            srv.shutdown()
        except Exception:
            pass
        try:
            srv.server_close()
        except Exception:
            pass
    if _thread is not None:
        _thread.join(timeout=2.0)
        _thread = None


def actif() -> bool:
    return _serveur is not None and _thread is not None and _thread.is_alive()


def etat() -> dict:
    """Ce qu'affiche la carte « Accès téléphone »."""
    return {
        "actif": actif(),
        "url": url() if actif() else None,
        "ip": ip_lan(),
        "port": port(),
        "jeton": jeton(),
        "erreur": _derniere_erreur,
        "derniere_visite": _derniere_visite,
        "jamais_visite": _derniere_visite is None,
        "en_attente": api.ops_en_attente(),
        "web_present": os.path.isdir(paths.WEB_DIR),
    }


AIDE_PARE_FEU = (
    "Windows bloque les connexions entrantes par défaut. Si le téléphone "
    "n'arrive pas à ouvrir la page alors que le serveur est en ligne :\n"
    "Panneau de configuration → Pare-feu Windows Defender → Paramètres "
    "avancés → Règles de trafic entrant → Nouvelle règle → Port → TCP "
    "{port} → Autoriser la connexion → cocher « Privé » uniquement "
    "(surtout pas Public) → nommer la règle « MF Cockpit mobile ».\n"
    "Le PC et l'iPhone doivent être sur le même réseau wifi."
)


def aide_pare_feu() -> str:
    return AIDE_PARE_FEU.format(port=port())
