"""
cogs/admin_config.py — Panneau de configuration du bot depuis Discord.
Commandes : /config show | set_channel | set_role | set_threshold | reset_live
Utilise des embeds + boutons pour une UX propre.
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

import config as cfg
from bot.database import db
from bot.utils import embeds
from bot.utils.checks import admin_only

log = logging.getLogger("krogan.admin")


# ─── Vue boutons pour le panneau config ───────────────────────────────────────

class ConfigView(discord.ui.View):
    """Boutons d'action rapide sur le panneau config."""

    def __init__(self) -> None:
        super().__init__(timeout=120)

    @discord.ui.button(label="Recharger live", style=discord.ButtonStyle.primary, emoji="🔄")
    async def reload_live(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        # Réinitialise le message live pour forcer une recréation
        await db.cfg_set("live_msg_id", "0")
        await interaction.response.send_message(
            embed=embeds.embed_success("Message live réinitialisé. Il sera recréé au prochain scan."),
            ephemeral=True,
        )

    @discord.ui.button(label="Voir watchlist", style=discord.ButtonStyle.secondary, emoji="📋")
    async def show_wl(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        pseudos = await db.wl_list()
        await interaction.response.send_message(
            embed=embeds.embed_wl_list(pseudos), ephemeral=True
        )


# ─── Cog ──────────────────────────────────────────────────────────────────────

class AdminConfigCog(commands.Cog, name="Config"):
    """Configuration du bot depuis Discord."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    cfg_group = app_commands.Group(
        name="config",
        description="Configurer le bot MossadGlory ext Krogan",
    )

    # ── /config show ──────────────────────────────────────────────────────────
    @cfg_group.command(name="show", description="Afficher la configuration actuelle")
    @admin_only()
    async def cfg_show(self, interaction: discord.Interaction) -> None:
        keys = [
            ("channel_live",         str(cfg.CHANNEL_LIVE)),
            ("channel_logs",         str(cfg.CHANNEL_LOGS)),
            ("channel_alerts",       str(cfg.CHANNEL_ALERTS)),
            ("role_action",          str(cfg.ROLE_ALERT_ACTION)),
            ("role_infiltration",    str(cfg.ROLE_ALERT_INFILTRATION)),
            ("role_missile",         str(cfg.ROLE_ALERT_MISSILE)),
            ("threshold_action",     str(cfg.THRESHOLD_ACTION)),
            ("threshold_infiltration", str(cfg.THRESHOLD_INFILTRATION)),
            ("threshold_missile",    str(cfg.THRESHOLD_MISSILE)),
            ("alert_cooldown",       str(cfg.ALERT_COOLDOWN)),
            ("ng_server",            cfg.NG_SERVER),
            ("scan_interval",        str(cfg.SCAN_INTERVAL)),
        ]
        current: dict[str, str] = {}
        for key, default in keys:
            val = await db.cfg_get(key)
            current[key] = val if val is not None else f"{default} (défaut)"

        embed = embeds.embed_config(current)
        await interaction.response.send_message(
            embed=embed, view=ConfigView(), ephemeral=True
        )

    # ── /config set_channel ────────────────────────────────────────────────────
    @cfg_group.command(
        name="set_channel",
        description="Définir un salon (live / logs / alertes)",
    )
    @app_commands.describe(
        type="Type de salon",
        channel="Salon Discord cible",
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="Live watchlist", value="channel_live"),
        app_commands.Choice(name="Logs",           value="channel_logs"),
        app_commands.Choice(name="Alertes",        value="channel_alerts"),
    ])
    @admin_only()
    async def cfg_set_channel(
        self,
        interaction: discord.Interaction,
        type: str,
        channel: discord.TextChannel,
    ) -> None:
        await db.cfg_set(type, str(channel.id))
        label = type.replace("channel_", "").capitalize()
        log.info("Config %s → %s (par %s)", type, channel.id, interaction.user)
        await interaction.response.send_message(
            embed=embeds.embed_success(f"Salon **{label}** → {channel.mention}"),
            ephemeral=True,
        )

    # ── /config set_role ───────────────────────────────────────────────────────
    @cfg_group.command(
        name="set_role",
        description="Définir le rôle pingé pour une alerte",
    )
    @app_commands.describe(
        type="Type d'alerte",
        role="Rôle à pinger",
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="Action (2+)",       value="role_action"),
        app_commands.Choice(name="Infiltration (3+)", value="role_infiltration"),
        app_commands.Choice(name="Missile (5+)",      value="role_missile"),
        app_commands.Choice(name="Admin bot",         value="admin_roles"),
    ])
    @admin_only()
    async def cfg_set_role(
        self,
        interaction: discord.Interaction,
        type: str,
        role: discord.Role,
    ) -> None:
        await db.cfg_set(type, str(role.id))
        label = type.replace("role_", "").replace("_", " ").capitalize()
        log.info("Config %s → %s (par %s)", type, role.id, interaction.user)
        await interaction.response.send_message(
            embed=embeds.embed_success(f"Rôle **{label}** → {role.mention}"),
            ephemeral=True,
        )

    # ── /config set_threshold ──────────────────────────────────────────────────
    @cfg_group.command(
        name="set_threshold",
        description="Modifier un seuil d'alerte",
    )
    @app_commands.describe(
        type="Type de seuil",
        valeur="Nombre d'actions requis",
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="Action",       value="threshold_action"),
        app_commands.Choice(name="Infiltration", value="threshold_infiltration"),
        app_commands.Choice(name="Missile",      value="threshold_missile"),
        app_commands.Choice(name="Cooldown alerte (secondes)", value="alert_cooldown"),
        app_commands.Choice(name="Intervalle scan (secondes)", value="scan_interval"),
    ])
    @admin_only()
    async def cfg_set_threshold(
        self,
        interaction: discord.Interaction,
        type: str,
        valeur: int,
    ) -> None:
        if valeur < 1:
            await interaction.response.send_message(
                embed=embeds.embed_error("La valeur doit être ≥ 1."), ephemeral=True
            )
            return
        await db.cfg_set(type, str(valeur))
        label = type.replace("threshold_", "").replace("_", " ").capitalize()
        log.info("Config %s → %s (par %s)", type, valeur, interaction.user)
        await interaction.response.send_message(
            embed=embeds.embed_success(f"**{label}** → `{valeur}`"),
            ephemeral=True,
        )

    # ── /config reset_live ─────────────────────────────────────────────────────
    @cfg_group.command(
        name="reset_live",
        description="Forcer la recréation du message live",
    )
    @admin_only()
    async def cfg_reset_live(self, interaction: discord.Interaction) -> None:
        await db.cfg_set("live_msg_id", "0")
        await interaction.response.send_message(
            embed=embeds.embed_success(
                "Message live réinitialisé. Il sera recréé au prochain scan."
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminConfigCog(bot))
