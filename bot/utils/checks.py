"""
utils/checks.py — Vérifications de permission pour les slash commands.
"""
from __future__ import annotations

import discord
from discord import app_commands

import config
from bot.database import db


async def _is_admin(interaction: discord.Interaction) -> bool:
    """Vérifie que l'utilisateur a un rôle admin configuré."""
    if not isinstance(interaction.user, discord.Member):
        return False
    # Charge les rôles admin depuis la DB (peut être surchargé depuis Discord)
    raw = await db.cfg_get("admin_roles")
    if raw:
        role_ids = [int(r) for r in raw.split(",") if r.strip().isdigit()]
    else:
        role_ids = list(config.ADMIN_ROLES)

    user_role_ids = {r.id for r in interaction.user.roles}
    return bool(user_role_ids & set(role_ids)) or interaction.user.guild_permissions.administrator


def admin_only():
    """Check discord.py pour slash commands admin."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if await _is_admin(interaction):
            return True
        await interaction.response.send_message(
            "❌ Tu n'as pas la permission.", ephemeral=True
        )
        return False
    return app_commands.check(predicate)
