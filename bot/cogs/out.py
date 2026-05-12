"""
cogs/out.py — Système OUT.
/out set pseudo heure   → marque un joueur OUT avec heure de retour
/out clear pseudo       → retire le OUT manuellement
Le scan loop retire automatiquement le OUT quand l'heure est passée.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from bot.database import db
from bot.utils import embeds
from bot.utils.checks import admin_only

log = logging.getLogger("krogan.out")

# Format heure accepté : HH:MM
_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


class OutCog(commands.Cog, name="OUT"):
    """Gestion du statut OUT des joueurs surveillés."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    out_group = app_commands.Group(
        name="out",
        description="Gérer le statut OUT d'un joueur",
    )

    @out_group.command(name="set", description="Marquer un joueur OUT jusqu'à une heure")
    @app_commands.describe(
        pseudo="Pseudo du joueur",
        heure="Heure de retour (format HH:MM, ex: 16:30)",
    )
    async def out_set(
        self, interaction: discord.Interaction, pseudo: str, heure: str
    ) -> None:
        pseudo = pseudo.strip()
        heure = heure.strip()

        # Validation format
        if not _TIME_RE.match(heure):
            await interaction.response.send_message(
                embed=embeds.embed_error("Format heure invalide. Utilise `HH:MM` (ex: `16:30`)."),
                ephemeral=True,
            )
            return

        # Vérif que le joueur est dans la watchlist
        if not await db.wl_exists(pseudo):
            await interaction.response.send_message(
                embed=embeds.embed_error(f"**{pseudo}** n'est pas dans la watchlist."),
                ephemeral=True,
            )
            return

        await db.set_out(pseudo, heure)
        log.info("OUT set: %s → %s (par %s)", pseudo, heure, interaction.user)

        await interaction.response.send_message(
            embed=embeds.embed_success(f"**{pseudo}** marqué OUT — retour prévu à `{heure}`."),
            ephemeral=True,
        )
        # Log salon
        await self._send_log(
            interaction,
            embed=embeds.embed_log_out_set(pseudo, heure),
        )

    @out_group.command(name="clear", description="Retirer le statut OUT d'un joueur")
    @app_commands.describe(pseudo="Pseudo du joueur")
    async def out_clear(self, interaction: discord.Interaction, pseudo: str) -> None:
        pseudo = pseudo.strip()
        player = await db.get_player(pseudo)
        if not player or not player.get("out_until"):
            await interaction.response.send_message(
                embed=embeds.embed_error(f"**{pseudo}** n'est pas marqué OUT."),
                ephemeral=True,
            )
            return

        await db.set_out(pseudo, None)
        log.info("OUT cleared: %s (par %s)", pseudo, interaction.user)

        await interaction.response.send_message(
            embed=embeds.embed_success(f"Statut OUT de **{pseudo}** retiré."),
            ephemeral=True,
        )
        await self._send_log(
            interaction,
            embed=embeds.embed_log_out_returned(pseudo),
        )

    # ── Autocomplete ──────────────────────────────────────────────────────────
    @out_set.autocomplete("pseudo")
    @out_clear.autocomplete("pseudo")
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
    async def _send_log(
        self, interaction: discord.Interaction, embed: discord.Embed
    ) -> None:
        ch_id = await db.cfg_get_int("channel_logs", 0)
        if ch_id:
            ch = interaction.guild and interaction.guild.get_channel(ch_id)
            if ch and isinstance(ch, discord.TextChannel):
                try:
                    await ch.send(embed=embed)
                except discord.DiscordException:
                    pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OutCog(bot))
