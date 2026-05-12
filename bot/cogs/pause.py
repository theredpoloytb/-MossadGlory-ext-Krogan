"""
cogs/pause.py — Pause / reprise des alertes.
/pause set duree  → pause les alertes pendant X heures (ou minutes)
/pause off        → reprend immédiatement
/pause status     → affiche l'état
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


class PauseCog(commands.Cog, name="Pause"):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    pause_group = app_commands.Group(
        name="pause",
        description="Mettre en pause les alertes de ping",
    )

    @pause_group.command(name="set", description="Suspendre les alertes pendant X heures")
    @app_commands.describe(heures="Durée en heures (ex: 2)")
    @admin_only()
    async def pause_set(self, interaction: discord.Interaction, heures: float) -> None:
        if heures <= 0:
            await interaction.response.send_message(
                embed=embeds.embed_error("La durée doit être > 0."), ephemeral=True
            )
            return

        until = datetime.now(timezone.utc) + timedelta(hours=heures)
        until_paris = until.astimezone(PARIS)
        await db.cfg_set("alerts_paused_until", until.isoformat())

        # Efface les alertes actives pour qu'elles re-pingent après la pause
        for atype in ("action", "infiltration", "missile"):
            await db.alert_clear("__global__", atype)

        log.info("Alertes pausées jusqu'à %s (par %s)", until_paris.strftime("%H:%M"), interaction.user)
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"⏸️ Alertes suspendues jusqu'à **{until_paris.strftime('%H:%M')}**.",
                color=0xE67E22,
            ),
            ephemeral=False,
        )

    @pause_group.command(name="off", description="Reprendre les alertes immédiatement")
    @admin_only()
    async def pause_off(self, interaction: discord.Interaction) -> None:
        await db.cfg_set("alerts_paused_until", "")
        log.info("Alertes reprises (par %s)", interaction.user)
        await interaction.response.send_message(
            embed=discord.Embed(
                description="▶️ Alertes **reprises**.",
                color=0x2ECC71,
            ),
            ephemeral=False,
        )

    @pause_group.command(name="status", description="Voir si les alertes sont en pause")
    async def pause_status(self, interaction: discord.Interaction) -> None:
        pause_until = await db.cfg_get("alerts_paused_until")
        if pause_until:
            try:
                dt = datetime.fromisoformat(pause_until)
                if datetime.now(timezone.utc) < dt:
                    dt_paris = dt.astimezone(PARIS)
                    await interaction.response.send_message(
                        embed=discord.Embed(
                            description=f"⏸️ Alertes en pause jusqu'à **{dt_paris.strftime('%H:%M')}**.",
                            color=0xE67E22,
                        ),
                        ephemeral=True,
                    )
                    return
            except Exception:
                pass
        await interaction.response.send_message(
            embed=discord.Embed(
                description="▶️ Alertes **actives**.",
                color=0x2ECC71,
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PauseCog(bot))
