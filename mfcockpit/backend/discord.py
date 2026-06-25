"""Widget Discord PUBLIC uniquement (pas de self-bot — ToS/ban).

Dégrade proprement si le widget est désactivé ou injoignable.
"""
import json
import urllib.error
import urllib.request


def discord_widget(guild_id: str, timeout: float = 5.0):
    """Renvoie {online, voice:[...]} ou {error:...} ou None si pas configuré."""
    if not guild_id:
        return None
    url = f"https://discord.com/api/guilds/{guild_id}/widget.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "mf-cockpit"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
        voice = []
        for m in d.get("members", []):
            if m.get("channel_id"):
                voice.append(m.get("username", "?"))
        return {
            "online": d.get("presence_count", len(d.get("members", []))),
            "voice": voice,
        }
    except urllib.error.HTTPError as e:
        if e.code == 403:
            return {"error": "widget désactivé"}
        return {"error": f"HTTP {e.code}"}
    except Exception:
        return {"error": "injoignable"}
