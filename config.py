"""
config.py — Configuration centrale de MossadGlory ext Krogan
Charge les variables d'environnement et expose des constantes typées.
"""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

# ─── Bot ──────────────────────────────────────────────────────────────────────
DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
GUILD_ID: int = int(os.getenv("GUILD_ID", "0"))

# ─── Salons par défaut (overridables depuis Discord) ──────────────────────────
CHANNEL_LIVE: int = int(os.getenv("CHANNEL_LIVE", "0"))
CHANNEL_LOGS: int = int(os.getenv("CHANNEL_LOGS", "0"))
CHANNEL_ALERTS: int = int(os.getenv("CHANNEL_ALERTS", "0"))

# ─── Rôles par défaut ─────────────────────────────────────────────────────────
ROLE_ALERT_ACTION: int = int(os.getenv("ROLE_ALERT_ACTION", "0"))
ROLE_ALERT_INFILTRATION: int = int(os.getenv("ROLE_ALERT_INFILTRATION", "0"))
ROLE_ALERT_MISSILE: int = int(os.getenv("ROLE_ALERT_MISSILE", "0"))

_raw_admin = os.getenv("ADMIN_ROLES", "")
ADMIN_ROLES: list[int] = [
    int(r.strip()) for r in _raw_admin.split(",") if r.strip().isdigit()
]

# ─── Seuils ───────────────────────────────────────────────────────────────────
THRESHOLD_ACTION: int = int(os.getenv("THRESHOLD_ACTION", "2"))
THRESHOLD_INFILTRATION: int = int(os.getenv("THRESHOLD_INFILTRATION", "3"))
THRESHOLD_MISSILE: int = int(os.getenv("THRESHOLD_MISSILE", "5"))

# ─── Cooldown alertes (secondes) ──────────────────────────────────────────────
ALERT_COOLDOWN: int = int(os.getenv("ALERT_COOLDOWN", "300"))

# ─── NationsGlory ─────────────────────────────────────────────────────────────
NG_SERVER: str = os.getenv("NG_SERVER", "lime")
NG_DYNMAP_URL: str = (
    f"https://{NG_SERVER}.nationsglory.fr/standalone/dynmap_world.json"
)
SCAN_INTERVAL: int = int(os.getenv("SCAN_INTERVAL", "30"))

# ─── SQLite ───────────────────────────────────────────────────────────────────
DB_PATH: str = os.getenv("DB_PATH", "bot/database/krogan.db")
