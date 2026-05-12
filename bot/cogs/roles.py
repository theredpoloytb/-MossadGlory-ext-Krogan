"""
cogs/roles.py — Salon rôles avec explication OUT + boutons self-role.
Commande : /setup_roles  → poste le message dans le salon courant
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.database import db
from bot.utils.checks import admin_only

log = logging.getLogger("krogan.roles")

# ─── Texte du message ─────────────────────────────────────────────────────────

EXPLICATION = """
## 🛡️ Bienvenue sur le système de surveillance Sword

Ce bot surveille en temps réel les joueurs **Sword** connectés sur **lime.nationsglory.fr**.

---

### 🕒 Système OUT

Si un joueur **Sword** est OUT (indisponible, pas en jeu), signalez-le pour qu'il ne soit pas compté dans les alertes.

**Comment ça marche :**
> Utilise la commande `/out set` dans n'importe quel salon.
> **Exemple :** `/out set SnipperA 16:30`
> → SnipperA sera marqué OUT jusqu'à `16:30`, le bot le retirera automatiquement à cette heure.

Si le joueur revient avant l'heure prévue :
> `/out clear SnipperA`

---

### 🔔 Alertes automatiques

Le bot envoie des alertes selon le nombre de joueurs Sword connectés **et non OUT** :

> ⚠️ **Action possible** — 2 joueurs connectés
> 🚨 **Infiltration possible** — 3 joueurs connectés
> 🔴 **Laser possible** — 5 joueurs connectés

Quand le seuil redescend, une alerte **"plus possible"** est envoyée.

---

### 📌 Choisis tes rôles de ping ci-dessous
"""

# ─── Vue boutons self-role ────────────────────────────────────────────────────

class RoleView(discord.ui.View):
    """Boutons persistants pour récupérer/retirer les rôles d'alerte."""

    def __init__(self) -> None:
        super().__init__(timeout=None)  # persistant après restart

    async def _toggle_role(
        self,
        interaction: discord.Interaction,
        role_key: str,
        role_name: str,
        emoji: str,
    ) -> None:
        """Toggle un rôle sur le membre."""
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ Erreur.", ephemeral=True)
            return

        # Récupère l'ID du rôle depuis la DB ou config
        import config as cfg
        defaults = {
            "role_action":       cfg.ROLE_ALERT_ACTION,
            "role_infiltration": cfg.ROLE_ALERT_INFILTRATION,
            "role_missile":      cfg.ROLE_ALERT_MISSILE,
        }
        role_id = await db.cfg_get_int(role_key, defaults.get(role_key, 0))
        if not role_id:
            await interaction.response.send_message(
                f"❌ Le rôle **{role_name}** n'est pas configuré. Demande à un admin.",
                ephemeral=True,
            )
            return

        role = interaction.guild and interaction.guild.get_role(role_id)
        if not role:
            await interaction.response.send_message(
                f"❌ Rôle introuvable. Demande à un admin de reconfigurer.",
                ephemeral=True,
            )
            return

        member = interaction.user
        if role in member.roles:
            await member.remove_roles(role, reason="Self-role Krogan")
            await interaction.response.send_message(
                f"{emoji} Rôle **{role_name}** retiré — tu ne recevras plus ces pings.",
                ephemeral=True,
            )
        else:
            await member.add_roles(role, reason="Self-role Krogan")
            await interaction.response.send_message(
                f"{emoji} Rôle **{role_name}** obtenu — tu recevras les pings.",
                ephemeral=True,
            )

    @discord.ui.button(
        label="⚠️ Action (2+)",
        style=discord.ButtonStyle.secondary,
        custom_id="krogan:role_action",
    )
    async def btn_action(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._toggle_role(interaction, "role_action", "Action", "⚠️")

    @discord.ui.button(
        label="🚨 Infiltration (3+)",
        style=discord.ButtonStyle.secondary,
        custom_id="krogan:role_infiltration",
    )
    async def btn_infiltration(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._toggle_role(interaction, "role_infiltration", "Infiltration", "🚨")

    @discord.ui.button(
        label="🔴 Laser (5+)",
        style=discord.ButtonStyle.danger,
        custom_id="krogan:role_missile",
    )
    async def btn_laser(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._toggle_role(interaction, "role_missile", "Laser", "🔴")

    @discord.ui.button(
        label="🔔 Tous les rôles",
        style=discord.ButtonStyle.primary,
        custom_id="krogan:role_all",
    )
    async def btn_all(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Donne ou retire les 3 rôles d'un coup."""
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ Erreur.", ephemeral=True)
            return

        import config as cfg
        role_keys = {
            "role_action":       (cfg.ROLE_ALERT_ACTION,       "⚠️ Action"),
            "role_infiltration": (cfg.ROLE_ALERT_INFILTRATION, "🚨 Infiltration"),
            "role_missile":      (cfg.ROLE_ALERT_MISSILE,      "🔴 Laser"),
        }

        added, removed, missing = [], [], []
        member = interaction.user

        for key, (default_id, label) in role_keys.items():
            role_id = await db.cfg_get_int(key, default_id)
            if not role_id:
                missing.append(label)
                continue
            role = interaction.guild and interaction.guild.get_role(role_id)
            if not role:
                missing.append(label)
                continue
            if role in member.roles:
                await member.remove_roles(role, reason="Self-role all Krogan")
                removed.append(label)
            else:
                await member.add_roles(role, reason="Self-role all Krogan")
                added.append(label)

        lines = []
        if added:
            lines.append("✅ **Rôles obtenus :** " + ", ".join(added))
        if removed:
            lines.append("❌ **Rôles retirés :** " + ", ".join(removed))
        if missing:
            lines.append("⚠️ **Non configurés :** " + ", ".join(missing))

        await interaction.response.send_message(
            "\n".join(lines) or "Rien à faire.",
            ephemeral=True,
        )


# ─── Cog ──────────────────────────────────────────────────────────────────────

class RolesCog(commands.Cog, name="Roles"):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Réenregistre la vue persistante au démarrage
        self.bot.add_view(RoleView())

    @app_commands.command(
        name="setup_roles",
        description="Poster le message d'explication + boutons de rôles dans ce salon",
    )
    @admin_only()
    async def setup_roles(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            description=EXPLICATION,
            color=0xFFD700,
        )
        embed.set_footer(text="MossadGlory ext Krogan • lime.nationsglory.fr")

        await interaction.channel.send(embed=embed, view=RoleView())
        await interaction.response.send_message(
            "✅ Message posté.", ephemeral=True
        )
        log.info("setup_roles posté dans #%s par %s", interaction.channel, interaction.user)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RolesCog(bot))
