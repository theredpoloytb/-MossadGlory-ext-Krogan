"""
utils/embeds.py — Fabrique d'embeds Discord.
Tous les embeds visuels du bot sont construits ici.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

import discord

PARIS = timezone(timedelta(hours=2))  # UTC+2 (heure d'été France)

def _ts() -> str:
    return datetime.now(PARIS).strftime("%H:%M:%S")

# ─── Palette ──────────────────────────────────────────────────────────────────
COLOR_GREEN   = 0x2ECC71
COLOR_RED     = 0xE74C3C
COLOR_ORANGE  = 0xE67E22
COLOR_YELLOW  = 0xF1C40F
COLOR_BLUE    = 0x3498DB
COLOR_DARK    = 0x2B2D31
COLOR_GOLD    = 0xFFD700
COLOR_GREY    = 0x95A5A6

FOOTER_TEXT = "MossadGlory ext Krogan • lime.nationsglory.fr"


# ─── Live watchlist ───────────────────────────────────────────────────────────

def embed_live(players: list[dict[str, Any]], nb_active: int) -> discord.Embed:
    online  = [p for p in players if p["online"] and not p["out_until"]]
    offline = [p for p in players if not p["online"] and not p["out_until"]]
    out     = [p for p in players if p["out_until"]]

    embed = discord.Embed(
        title="🛡️ Watchlist Sword — Live",
        color=COLOR_GOLD,
        timestamp=datetime.now(PARIS),
    )
    embed.set_footer(text=FOOTER_TEXT)

    if online:
        lines = [f"🟢 **{p['pseudo']}**" for p in online]
        embed.add_field(name=f"Connectés ({len(online)})", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="Connectés (0)", value="*Aucun*", inline=False)

    if offline:
        lines = []
        for p in offline:
            since = ""
            if p.get("offline_since"):
                try:
                    dt = datetime.fromisoformat(p["offline_since"]).replace(tzinfo=timezone.utc).astimezone(PARIS)
                    since = f" *(vu {dt.strftime('%H:%M')})*"
                except Exception:
                    since = ""
            lines.append(f"🔴 **{p['pseudo']}**{since}")
        embed.add_field(name=f"Déconnectés ({len(offline)})", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="Déconnectés (0)", value="*Aucun*", inline=False)

    if out:
        lines = [f"🕒 **{p['pseudo']}** — retour `{p['out_until']}`" for p in out]
        embed.add_field(name=f"OUT ({len(out)})", value="\n".join(lines), inline=False)

    embed.add_field(name="🔄 Dernière MAJ", value=f"`{_ts()}`", inline=True)
    return embed


# ─── Logs ─────────────────────────────────────────────────────────────────────

def embed_log_connect(pseudo: str) -> discord.Embed:
    e = discord.Embed(color=COLOR_GREEN, timestamp=datetime.now(PARIS))
    e.set_footer(text=FOOTER_TEXT)
    e.description = f"🟢 **{pseudo}** connecté"
    return e

def embed_log_disconnect(pseudo: str) -> discord.Embed:
    e = discord.Embed(color=COLOR_RED, timestamp=datetime.now(PARIS))
    e.set_footer(text=FOOTER_TEXT)
    e.description = f"🔴 **{pseudo}** déconnecté"
    return e

def embed_log_out_set(pseudo: str, out_until: str) -> discord.Embed:
    e = discord.Embed(color=COLOR_ORANGE, timestamp=datetime.now(PARIS))
    e.set_footer(text=FOOTER_TEXT)
    e.description = f"🕒 **{pseudo}** passé OUT — retour prévu `{out_until}`"
    return e

def embed_log_out_returned(pseudo: str) -> discord.Embed:
    e = discord.Embed(color=COLOR_BLUE, timestamp=datetime.now(PARIS))
    e.set_footer(text=FOOTER_TEXT)
    e.description = f"✅ **{pseudo}** est revenu de OUT"
    return e


# ─── Alertes ──────────────────────────────────────────────────────────────────

def embed_alert(alert_type: str, actions: int, players_online: list[str]) -> discord.Embed:
    templates = {
        "action":          (COLOR_YELLOW, "⚠️",  "Action possible",          "alerte"),
        "infiltration":    (COLOR_ORANGE, "🚨",  "Infiltration possible",    "alerte"),
        "missile":         (COLOR_RED,    "🔴",  "Laser possible",           "ALERTE CRITIQUE"),
        "no_action":       (COLOR_GREEN,  "✅",  "Action plus possible",     "info"),
        "no_infiltration": (COLOR_GREEN,  "✅",  "Infiltration plus possible","info"),
        "no_missile":      (COLOR_GREEN,  "✅",  "Laser plus possible",      "info"),
    }
    color, icon, title, label = templates.get(alert_type, (COLOR_GREY, "ℹ️", alert_type, "info"))
    e = discord.Embed(title=f"{icon} {title}", color=color, timestamp=datetime.now(PARIS))
    e.set_footer(text=FOOTER_TEXT)
    if players_online:
        e.add_field(name="Joueurs connectés", value="\n".join(f"• **{p}**" for p in players_online), inline=False)
    e.add_field(name="Joueurs connectés (hors OUT)", value=f"`{actions}`", inline=True)
    return e


# ─── Watchlist management ─────────────────────────────────────────────────────

def embed_wl_list(pseudos: list[str]) -> discord.Embed:
    e = discord.Embed(title="📋 Watchlist Sword", color=COLOR_GOLD, timestamp=datetime.now(PARIS))
    e.set_footer(text=FOOTER_TEXT)
    e.description = "\n".join(f"`{i+1}.` **{p}**" for i, p in enumerate(pseudos)) if pseudos else "*Watchlist vide*"
    e.add_field(name="Total", value=f"`{len(pseudos)}` joueur(s)", inline=True)
    return e


# ─── Config panel ─────────────────────────────────────────────────────────────

def embed_config(cfg: dict[str, str]) -> discord.Embed:
    e = discord.Embed(title="⚙️ Configuration du bot", color=COLOR_BLUE, timestamp=datetime.now(PARIS))
    e.set_footer(text=FOOTER_TEXT)
    for key, val in cfg.items():
        e.add_field(name=key, value=f"`{val}`", inline=True)
    return e


# ─── Succès / Erreur génériques ───────────────────────────────────────────────

def embed_success(msg: str) -> discord.Embed:
    return discord.Embed(description=f"✅ {msg}", color=COLOR_GREEN)

def embed_error(msg: str) -> discord.Embed:
    return discord.Embed(description=f"❌ {msg}", color=COLOR_RED)
