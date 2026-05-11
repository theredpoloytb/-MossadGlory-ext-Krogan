"""
cogs/watchlist.py — Gestion de la watchlist Sword.
Commandes : /watchlist add | remove | list
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.database import db
from bot.utils import embeds
from bot.utils.checks import admin_only

log = logging.getLogger("krogan.watchlist")


class WatchlistCog(commands.Cog, name="Watchlist"):
    """Gestion de la watchlist des joueurs Sword surveillés."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── Groupe /watchlist ──────────────────────────────────────────────────────
    wl_group = app_commands.Group(
        name="watchlist",
        description="Gérer la watchlist Sword",
    )

    @wl_group.command(name="add", description="Ajouter un joueur à la watchlist")
    @app_commands.describe(pseudo="Pseudo exact du joueur NationsGlory")
    @admin_only()
    async def wl_add(self, interaction: discord.Interaction, pseudo: str) -> None:
        pseudo = pseudo.strip()
        if not pseudo:
            await interaction.response.send_message(
                embed=embeds.embed_error("Pseudo invalide."), ephemeral=True
            )
            return

        added = await db.wl_add(pseudo)
        if added:
            log.info("Watchlist + %s (par %s)", pseudo, interaction.user)
            await interaction.response.send_message(
                embed=embeds.embed_success(f"**{pseudo}** ajouté à la watchlist."),
                ephemeral=True,
            )
            # Notif dans les logs
            await self._send_log(
                interaction,
                f"📥 **{pseudo}** ajouté à la watchlist par {interaction.user.mention}",
            )
        else:
            await interaction.response.send_message(
                embed=embeds.embed_error(f"**{pseudo}** est déjà dans la watchlist."),
                ephemeral=True,
            )

    @wl_group.command(name="remove", description="Retirer un joueur de la watchlist")
    @app_commands.describe(pseudo="Pseudo exact du joueur à retirer")
    @admin_only()
    async def wl_remove(self, interaction: discord.Interaction, pseudo: str) -> None:
        pseudo = pseudo.strip()
        removed = await db.wl_remove(pseudo)
        if removed:
            log.info("Watchlist - %s (par %s)", pseudo, interaction.user)
            await interaction.response.send_message(
                embed=embeds.embed_success(f"**{pseudo}** retiré de la watchlist."),
                ephemeral=True,
            )
            await self._send_log(
                interaction,
                f"📤 **{pseudo}** retiré de la watchlist par {interaction.user.mention}",
            )
        else:
            await interaction.response.send_message(
                embed=embeds.embed_error(f"**{pseudo}** introuvable dans la watchlist."),
                ephemeral=True,
            )

    @wl_group.command(name="list", description="Afficher la watchlist complète")
    async def wl_list(self, interaction: discord.Interaction) -> None:
        pseudos = await db.wl_list()
        await interaction.response.send_message(
            embed=embeds.embed_wl_list(pseudos), ephemeral=True
        )

    # ── Autocomplete pseudo (depuis la watchlist) ──────────────────────────────
    @wl_remove.autocomplete("pseudo")
    async def autocomplete_pseudo(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        pseudos = await db.wl_list()
        return [
            app_commands.Choice(name=p, value=p)
            for p in pseudos
            if current.lower() in p.lower()
        ][:25]

    # ── Helper ────────────────────────────────────────────────────────────────
    async def _send_log(self, interaction: discord.Interaction, msg: str) -> None:
        ch_id = await db.cfg_get_int("channel_logs", 0)
        if ch_id:
            ch = interaction.guild and interaction.guild.get_channel(ch_id)
            if ch and isinstance(ch, discord.TextChannel):
                try:
                    await ch.send(embed=discord.Embed(description=msg, color=0x3498DB))
                except discord.DiscordException:
                    pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WatchlistCog(bot))
