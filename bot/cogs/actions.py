"""
cogs/actions.py — Mise à jour manuelle des actions d'un joueur.
/actions set pseudo nombre  → met à jour le nombre d'actions
/actions show               → affiche les actions de tous les joueurs
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.database import db
from bot.utils import embeds
from bot.utils.checks import admin_only

log = logging.getLogger("krogan.actions")


class ActionsCog(commands.Cog, name="Actions"):
    """Gestion manuelle des compteurs d'actions des joueurs."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    act_group = app_commands.Group(
        name="actions",
        description="Gérer les actions des joueurs surveillés",
    )

    @act_group.command(name="set", description="Définir le nombre d'actions d'un joueur")
    @app_commands.describe(
        pseudo="Pseudo du joueur",
        nombre="Nombre d'actions disponibles",
    )
    @admin_only()
    async def actions_set(
        self, interaction: discord.Interaction, pseudo: str, nombre: int
    ) -> None:
        pseudo = pseudo.strip()
        if not await db.wl_exists(pseudo):
            await interaction.response.send_message(
                embed=embeds.embed_error(f"**{pseudo}** n'est pas dans la watchlist."),
                ephemeral=True,
            )
            return
        if nombre < 0:
            await interaction.response.send_message(
                embed=embeds.embed_error("Le nombre d'actions doit être ≥ 0."),
                ephemeral=True,
            )
            return

        await db.upsert_player(pseudo, actions=nombre)
        log.info("Actions %s → %d (par %s)", pseudo, nombre, interaction.user)
        await interaction.response.send_message(
            embed=embeds.embed_success(f"**{pseudo}** → `{nombre}` action(s)."),
            ephemeral=True,
        )

    @act_group.command(name="show", description="Afficher les actions de tous les joueurs")
    async def actions_show(self, interaction: discord.Interaction) -> None:
        players = await db.get_all_players()
        if not players:
            await interaction.response.send_message(
                embed=embeds.embed_error("Watchlist vide."), ephemeral=True
            )
            return

        embed = discord.Embed(
            title="⚡ Actions par joueur",
            color=0xFFD700,
        )
        for p in players:
            status = "🟢" if p["online"] else "🔴"
            out = f" 🕒 OUT {p['out_until']}" if p.get("out_until") else ""
            embed.add_field(
                name=f"{status} {p['pseudo']}{out}",
                value=f"`{p.get('actions', 0)}` action(s)",
                inline=True,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Autocomplete ──────────────────────────────────────────────────────────
    @actions_set.autocomplete("pseudo")
    async def autocomplete_pseudo(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        pseudos = await db.wl_list()
        return [
            app_commands.Choice(name=p, value=p)
            for p in pseudos
            if current.lower() in p.lower()
        ][:25]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ActionsCog(bot))
