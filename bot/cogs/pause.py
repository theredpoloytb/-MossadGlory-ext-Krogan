"""
cogs/pause.py — Pause / reprise des alertes par type.
/pause set [type] duree  → pause une alerte ou toutes pendant X heures
/pause off [type]        → reprend immédiatement
/pause status            → affiche l'état de toutes les alertes
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext import commands

from bot.database import db
from bot.utils import embeds
from bot.utils.checks import admin_only

log = logging.getLogger("krogan.pause")

PARIS = timezone(timedelta(hours=2))

ALERT_TYPES = {
    "action":       "⚠️ Action",
    "infiltration": "🚨 Infiltration",
    "laser":        "🔴 Laser",
    "toutes":       "🔔 Toutes",
}

def _db_key(atype: str) -> list[str]:
    if atype == "toutes":
        return ["action", "infiltration", "missile"]
    if atype == "laser":
        return ["missile"]
    return [atype]


class PauseCog(commands.Cog, name="Pause"):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    pause_group = app_commands.Group(
        name="pause",
        description="Mettre en pause les alertes de ping",
    )

    @pause_group.command(name="set", description="Suspendre une alerte pendant une durée")
    @app_commands.describe(
        type="Type d'alerte à suspendre",
        duree="Durée (ex: 2)",
        unite="Unité de temps",
    )
    @app_commands.choices(
        type=[
            app_commands.Choice(name="⚠️ Action",        value="action"),
            app_commands.Choice(name="🚨 Infiltration",  value="infiltration"),
            app_commands.Choice(name="🔴 Laser",         value="laser"),
            app_commands.Choice(name="🔔 Toutes",        value="toutes"),
        ],
        unite=[
            app_commands.Choice(name="Minutes", value="minutes"),
            app_commands.Choice(name="Heures",  value="heures"),
            app_commands.Choice(name="Jours",   value="jours"),
        ],
    )
    @admin_only()
    async def pause_set(self, interaction: discord.Interaction, type: str, duree: float, unite: str = "heures") -> None:
        if duree <= 0:
            await interaction.response.send_message(
                embed=embeds.embed_error("La durée doit être > 0."), ephemeral=True
            )
            return

        if unite == "minutes":
            delta = timedelta(minutes=duree)
            label_duree = f"{duree:.0f} minute(s)"
        elif unite == "jours":
            delta = timedelta(days=duree)
            label_duree = f"{duree:.0f} jour(s)"
        else:
            delta = timedelta(hours=duree)
            label_duree = f"{duree:.0f} heure(s)"

        until = datetime.now(timezone.utc) + delta
        until_paris = until.astimezone(PARIS)

        for key in _db_key(type):
            await db.cfg_set(f"pause_{key}_until", until.isoformat())
            await db.alert_clear("__global__", key)

        label = ALERT_TYPES[type]
        log.info("Pause %s %s jusqu'à %s (par %s)", type, label_duree, until_paris.strftime("%d/%m %H:%M"), interaction.user)
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"⏸️ **{label}** suspendue pendant **{label_duree}** (jusqu'à **{until_paris.strftime('%d/%m à %H:%M')}**).",
                color=0xE67E22,
            ),
        )

    @pause_group.command(name="off", description="Reprendre une alerte immédiatement")
    @app_commands.describe(type="Type d'alerte à reprendre")
    @app_commands.choices(type=[
        app_commands.Choice(name="⚠️ Action",        value="action"),
        app_commands.Choice(name="🚨 Infiltration",  value="infiltration"),
        app_commands.Choice(name="🔴 Laser",         value="laser"),
        app_commands.Choice(name="🔔 Toutes",        value="toutes"),
    ])
    @admin_only()
    async def pause_off(self, interaction: discord.Interaction, type: str) -> None:
        for key in _db_key(type):
            await db.cfg_set(f"pause_{key}_until", "")

        label = ALERT_TYPES[type]
        log.info("Pause %s reprise (par %s)", type, interaction.user)
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"▶️ **{label}** reprise.",
                color=0x2ECC71,
            ),
        )

    @pause_group.command(name="status", description="Voir l'état des alertes")
    async def pause_status(self, interaction: discord.Interaction) -> None:
        now = datetime.now(timezone.utc)
        embed = discord.Embed(title="🔔 État des alertes", color=0x3498DB)

        labels = {
            "action":       "⚠️ Action",
            "infiltration": "🚨 Infiltration",
            "missile":      "🔴 Laser",
        }
        for key, label in labels.items():
            val = await db.cfg_get(f"pause_{key}_until")
            if val:
                try:
                    dt = datetime.fromisoformat(val)
                    if now < dt:
                        dt_paris = dt.astimezone(PARIS)
                        embed.add_field(name=label, value=f"⏸️ jusqu'à `{dt_paris.strftime('%H:%M')}`", inline=True)
                        continue
                except Exception:
                    pass
            embed.add_field(name=label, value="▶️ Active", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PauseCog(bot))
