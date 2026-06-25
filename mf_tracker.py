#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MF Tracker — suit ton temps de jeu (solo / multi) + présences en jeu et Discord.
A lancer sur ton PC. Pour en faire un .exe :  voir README.txt

NOTE : ce fichier est le script CLI d'origine, conservé comme référence.
La logique est réutilisée et refactorée dans le paquet `mfcockpit/` (app fenêtrée).
"""
import os, sys, json, time, socket
from datetime import timedelta

# ----------------- CONFIG (à ajuster) -----------------
SERVER_HOST = "minefield.fr"
SERVER_PORT = 25565
DISCORD_GUILD_ID = ""   # active le widget (Param. serveur > Widget) puis colle l'ID du serveur ici
POLL_SECONDS = 15
# ------------------------------------------------------

try:
    import psutil
except ImportError:
    print("Manque psutil :  pip install psutil mcstatus"); sys.exit(1)
try:
    from mcstatus import JavaServer
except ImportError:
    JavaServer = None
import urllib.request, urllib.error

DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "mf_tracker")
os.makedirs(DATA_DIR, exist_ok=True)
STATE_FILE = os.path.join(DATA_DIR, "playtime.json")


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    d.setdefault("solo_seconds", 0.0)
    d.setdefault("multi_seconds", 0.0)
    d.setdefault("sessions", [])
    return d


def save_state(d):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent="\t")
    os.replace(tmp, STATE_FILE)


def fmt(seconds):
    return str(timedelta(seconds=int(seconds)))


def resolve_server_ips():
    ips = set()
    for host in {SERVER_HOST}:
        try:
            _, _, addrs = socket.gethostbyname_ex(host)
            ips.update(addrs)
        except Exception:
            pass
    return ips


def find_mc_process():
    """Cherche le client Minecraft/Minefield (javaw lançant le client)."""
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
    return None


def current_mode(proc, server_ips):
    """multi si une connexion établie vers le serveur, sinon solo."""
    try:
        for c in proc.net_connections(kind="inet"):
            if c.status == psutil.CONN_ESTABLISHED and c.raddr:
                if c.raddr.ip in server_ips or c.raddr.port == SERVER_PORT:
                    return "multi"
    except Exception:
        pass
    return "solo"


def server_status():
    if JavaServer is None:
        return None
    try:
        srv = JavaServer.lookup(f"{SERVER_HOST}:{SERVER_PORT}", timeout=4)
        st = srv.status()
        sample = [pl.name for pl in (st.players.sample or [])]
        return {"online": st.players.online, "max": st.players.max, "sample": sample}
    except Exception:
        return None


def discord_widget():
    if not DISCORD_GUILD_ID:
        return None
    url = f"https://discord.com/api/guilds/{DISCORD_GUILD_ID}/widget.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "mf-tracker"})
        with urllib.request.urlopen(req, timeout=5) as r:
            d = json.load(r)
        voice = []
        for m in d.get("members", []):
            if m.get("channel_id"):
                voice.append(m.get("username", "?"))
        return {"online": d.get("presence_count", len(d.get("members", []))),
                "voice": voice}
    except urllib.error.HTTPError as e:
        if e.code == 403:
            return {"error": "widget désactivé"}
        return {"error": f"HTTP {e.code}"}
    except Exception:
        return {"error": "injoignable"}


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def main():
    state = load_state()
    server_ips = resolve_server_ips()
    print(f"MF Tracker — données dans {STATE_FILE}")
    print(f"Total enregistré — Solo {fmt(state['solo_seconds'])} | "
          f"Multi {fmt(state['multi_seconds'])}\n")
    time.sleep(1.5)

    session = {"solo": 0.0, "multi": 0.0}
    last = time.time()
    last_save = 0.0
    try:
        while True:
            now = time.time()
            elapsed = now - last
            last = now

            proc = find_mc_process()
            mode = None
            if proc is not None:
                mode = current_mode(proc, server_ips)
                state[f"{mode}_seconds"] += elapsed
                session[mode] += elapsed

            srv = server_status()
            dis = discord_widget()

            clear()
            print("=" * 52)
            print("  MF TRACKER")
            print("=" * 52)
            jeu = "AUCUN" if proc is None else f"EN COURS ({mode.upper()})"
            print(f"  Jeu          : {jeu}")
            print(f"  Session      : solo {fmt(session['solo'])} | "
                  f"multi {fmt(session['multi'])}")
            print(f"  TOTAL solo   : {fmt(state['solo_seconds'])}")
            print(f"  TOTAL multi  : {fmt(state['multi_seconds'])}")
            tot = state['solo_seconds'] + state['multi_seconds']
            print(f"  TOTAL global : {fmt(tot)}")
            print("-" * 52)
            if srv:
                s = f"  Minefield    : {srv['online']}/{srv['max']} en ligne"
                if srv["sample"]:
                    s += "  (" + ", ".join(srv["sample"][:8]) + ")"
                print(s)
            else:
                print("  Minefield    : serveur injoignable")
            if dis is None:
                print("  Discord      : (renseigne DISCORD_GUILD_ID)")
            elif "error" in dis:
                print(f"  Discord      : {dis['error']}")
            else:
                d = f"  Discord      : {dis['online']} en ligne"
                if dis["voice"]:
                    d += f" | vocal: {', '.join(dis['voice'][:8])}"
                print(d)
            print("=" * 52)
            print("  Ctrl+C pour quitter (sauvegarde auto)")

            if now - last_save > 30:
                save_state(state); last_save = now
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        if session["solo"] + session["multi"] > 0:
            state["sessions"].append({
                "fin": time.strftime("%Y-%m-%d %H:%M"),
                "solo": int(session["solo"]), "multi": int(session["multi"])})
        save_state(state)
        print(f"\nSauvegardé. Session : solo {fmt(session['solo'])} | "
              f"multi {fmt(session['multi'])}")


if __name__ == "__main__":
    main()
