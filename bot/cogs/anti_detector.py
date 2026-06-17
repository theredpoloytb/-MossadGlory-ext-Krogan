"""
cogs/anti_detector.py — Détecte les swords (watchlist) qui se déconnectent
dans les 4 minutes suivant la connexion d'un allié.

Logique :
  - Un allié se connecte → timestamp enregistré
  - Un sword se déco dans les 240s qui suivent → alerte "anti" dans channel dédié
  - Cooldown 5 min par paire (ally, sword) pour éviter le spam

Commandes :
  /allies add <pseudo>    — Ajouter un allié
  /allies remove <pseudo> — Retirer un allié
  /allies list            — Lister les alliés
"""
from __future__ import annotations

import logging
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.database import db
from bot.utils.checks import admin_only

log = logging.getLogger("krogan.anti")

# Fenêtre de détection en secondes (4 minutes)
ANTI_WINDOW = 240

# Cooldown anti-spam entre deux alertes identiques (paire ally+sword)
ALERT_COOLDOWN = 300  # 5 minutes


class AntiDetectorCog(commands.Cog, name="AntiDetector"):
    """Détecte les swords qui fuient à la connexion d'un allié."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # { pseudo_ally (lowercase) : timestamp float }
        self._ally_connect_times: dict[str, float] = {}
        # { (ally_lower, sword_lower) : timestamp dernière alerte }
        self._alert_cooldown: dict[tuple[str, str], float] = {}

    async def cog_load(self) -> None:
        self._cleanup.start()
        log.info("AntiDetector démarré (fenêtre %ds)", ANTI_WINDOW)

    async def cog_unload(self) -> None:
        self._cleanup.cancel()

    # ─── Nettoyage périodique du cache ────────────────────────────────────────

    @tasks.loop(minutes=5)
    async def _cleanup(self) -> None:
        now = time.time()
        expired = [k for k, t in self._ally_connect_times.items() if now - t > ANTI_WINDOW]
        for k in expired:
            del self._ally_connect_times[k]
        if expired:
            log.debug("AntiDetector: %d entrées expirées nettoyées", len(expired))

    @_cleanup.before_loop
    async def _before_cleanup(self) -> None:
        await self.bot.wait_until_ready()

    # ─── Hooks appelés par scanner.py ─────────────────────────────────────────

    async def on_ally_connect(self, pseudo: str) -> None:
        """
        Appelé par scanner.py quand un allié se connecte.
        Enregistre le timestamp de connexion.
        """
        self._ally_connect_times[pseudo.lower()] = time.time()
        log.info("[Anti] Allié connecté : %s", pseudo)

    async def on_sword_disconnect(self, pseudo: str) -> None:
        """
        Appelé par scanner.py quand un sword (watchlist) se déconnecte.
        Vérifie si un allié s'est connecté dans les 4 dernières minutes.
        """
        now = time.time()

        # Cherche tous les alliés connectés dans la fenêtre
        triggered_by = [
            ally for ally, t in self._ally_connect_times.items()
            if now - t <= ANTI_WINDOW
        ]

        if not triggered_by:
            return

        for ally in triggered_by:
            pair = (ally, pseudo.lower())
            last_alert = self._alert_cooldown.get(pair, 0)
            if now - last_alert < ALERT_COOLDOWN:
                log.debug("[Anti] Cooldown actif pour paire (%s, %s)", ally, pseudo)
                continue

            self._alert_cooldown[pair] = now
            delay = now - self._ally_connect_times[ally]
            await self._send_alert(pseudo, ally, delay)

    # ─── Envoi de l'alerte ────────────────────────────────────────────────────

    async def _send_alert(self, sword: str, ally: str, delay_seconds: float) -> None:
        ch_id = await db.cfg_get_int("channel_anti", 0)
        if not ch_id:
            log.warning("[Anti] channel_anti non configuré — utilise /config set_channel anti #salon")
            return

        guild = self.bot.guilds[0] if self.bot.guilds else None
        if not guild:
            return

        ch = guild.get_channel(ch_id)
        if not ch or not isinstance(ch, discord.TextChannel):
            log.warning("[Anti] channel_anti introuvable (id=%s)", ch_id)
            return

        embed = self._build_embed(sword, ally, delay_seconds)
        try:
            await ch.send(embed=embed)
            log.info("[Anti] Alerte envoyée : %s a fui après co de %s (%.0fs)", sword, ally, delay_seconds)
        except discord.DiscordException as exc:
            log.warning("[Anti] Envoi alerte échoué: %s", exc)

    def _build_embed(self, sword: str, ally: str, delay_seconds: float) -> discord.Embed:
        minutes = int(delay_seconds // 60)
        seconds = int(delay_seconds % 60)
        delay_str = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"

        embed = discord.Embed(
            title="🏃 Anti détecté !",
            description=(
                f"**`{sword}`** s'est déconnecté **{delay_str}** après la connexion de **`{ally}`**.\n"
                f"Il avait probablement **2 actions** et a fui pour éviter d'être actionné."
            ),
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="⚔️ Sword", value=f"`{sword}`", inline=True)
        embed.add_field(name="🟢 Allié connecté", value=f"`{ally}`", inline=True)
        embed.add_field(name="⏱️ Délai de fuite", value=f"`{delay_str}`", inline=True)
        embed.set_footer(text="MossadGlory • Anti Detector")
        return embed

    # ─── Commandes slash /allies ───────────────────────────────────────────────

    allies_group = app_commands.Group(
        name="allies",
        description="Gérer la liste des membres de ton camp",
    )

    @allies_group.command(name="add", description="Ajouter un allié à surveiller")
    @app_commands.describe(pseudo="Pseudo Minecraft de l'allié")
    @admin_only()
    async def allies_add(self, interaction: discord.Interaction, pseudo: str) -> None:
        added = await db.ally_add(pseudo)
        if not added:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"⚠️ **{pseudo}** est déjà dans la liste des alliés.",
                    color=discord.Color.yellow(),
                ),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"✅ **{pseudo}** ajouté à la liste des alliés.",
                color=discord.Color.green(),
            ),
            ephemeral=True,
        )
        log.info("Allié ajouté : %s (par %s)", pseudo, interaction.user)

    @allies_group.command(name="remove", description="Retirer un allié")
    @app_commands.describe(pseudo="Pseudo Minecraft de l'allié")
    @admin_only()
    async def allies_remove(self, interaction: discord.Interaction, pseudo: str) -> None:
        removed = await db.ally_remove(pseudo)
        # Nettoyage du cache live
        self._ally_connect_times.pop(pseudo.lower(), None)
        if not removed:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"⚠️ **{pseudo}** n'est pas dans la liste des alliés.",
                    color=discord.Color.yellow(),
                ),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"✅ **{pseudo}** retiré de la liste des alliés.",
                color=discord.Color.green(),
            ),
            ephemeral=True,
        )
        log.info("Allié retiré : %s (par %s)", pseudo, interaction.user)

    @allies_group.command(name="list", description="Voir la liste des alliés")
    async def allies_list(self, interaction: discord.Interaction) -> None:
        allies = await db.ally_list()
        if not allies:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="📭 Aucun allié dans la liste.\nUtilise `/allies add <pseudo>` pour en ajouter.",
                    color=discord.Color.light_grey(),
                ),
                ephemeral=True,
            )
            return

        # Indique lesquels sont actuellement en cache (connectés récemment)
        now = time.time()
        lines = []
        for a in allies:
            t = self._ally_connect_times.get(a.lower())
            if t and now - t <= ANTI_WINDOW:
                remaining = int(ANTI_WINDOW - (now - t))
                lines.append(f"🟢 `{a}` — connecté il y a {int(now - t)}s (fenêtre active : {remaining}s)")
            else:
                lines.append(f"⚫ `{a}`")

        embed = discord.Embed(
            title="👥 Liste des alliés",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        embed.set_footer(text=f"{len(allies)} allié(s) — fenêtre anti : {ANTI_WINDOW}s")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AntiDetectorCog(bot))
