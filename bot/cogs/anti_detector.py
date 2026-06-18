"""
cogs/anti_detector.py — Détecte les swords (watchlist) qui se déconnectent
dans les 4 minutes suivant le passage à 2+ alliés connectés simultanément.

Logique CORRECTE :
  - On track combien d'alliés sont connectés en temps réel
  - Quand le compteur passe de 1 → 2 (ou plus) → timestamp "danger" enregistré
  - Un sword se déco dans les 240s qui suivent ce passage à 2 → alerte anti
  - Cooldown 5 min par sword pour éviter le spam

Commandes :
  /allies add <pseudo>    — Ajouter un allié
  /allies remove <pseudo> — Retirer un allié
  /allies list            — Lister les alliés
  /allies seed            — [ONE-SHOT] Importer la liste de base
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

# Cooldown anti-spam par sword
ALERT_COOLDOWN = 300  # 5 minutes

ALLIES_SEED = [
    "BRBradley70",
    "carpask",
    "Eri0ss",
    "Gencyvejunior",
    "grosbourrin",
    "Kyzzer_",
    "Madara__Uchiha",
    "Nathdu12",
    "Nonoz599",
    "poorayanez",
    "theredpoloytb",
    "toto132",
    "Tsuki_zZzZ",
    "xsaqm_m",
]


class AntiDetectorCog(commands.Cog, name="AntiDetector"):
    """Détecte les swords qui fuient quand 2 alliés sont connectés."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

        # Set des alliés actuellement connectés (lowercase)
        self._allies_online: set[str] = set()

        # Timestamp du dernier passage à 2+ alliés connectés
        # None = pas de "danger" actif
        self._danger_since: float | None = None

        # { sword_lower : timestamp dernière alerte }
        self._alert_cooldown: dict[str, float] = {}

    async def cog_load(self) -> None:
        self._cleanup.start()
        await self._restore_allies_online()
        log.info("AntiDetector démarré (fenêtre %ds, trigger = 2 alliés co)", ANTI_WINDOW)

    async def _restore_allies_online(self) -> None:
        """
        Au démarrage, compare la liste d'alliés en DB avec les joueurs
        actuellement en ligne sur le serveur NationsGlory pour reconstruire
        _allies_online sans attendre le prochain tick du scanner.
        """
        import aiohttp
        from bot.utils import ng_api
        try:
            async with aiohttp.ClientSession() as session:
                online_now = await ng_api.fetch_online_players(session)
            online_set = {p.lower() for p in online_now}
            allies = await db.ally_list()
            for ally in allies:
                if ally.lower() in online_set:
                    self._allies_online.add(ally.lower())
            nb = len(self._allies_online)
            log.info("[Anti] Restauration : %d allié(s) déjà connecté(s) → %s", nb, self._allies_online)
            if nb >= 2:
                self._danger_since = time.time()
                log.info("[Anti] ⚠️ 2+ alliés déjà co au démarrage → fenêtre danger ouverte")
        except Exception as exc:
            log.warning("[Anti] Restauration alliés échouée: %s", exc)

    async def cog_unload(self) -> None:
        self._cleanup.cancel()

    # ─── Nettoyage périodique ─────────────────────────────────────────────────

    @tasks.loop(minutes=5)
    async def _cleanup(self) -> None:
        # Si la fenêtre danger est expirée, on la reset
        if self._danger_since and time.time() - self._danger_since > ANTI_WINDOW:
            self._danger_since = None
            log.debug("[Anti] Fenêtre danger expirée, reset")

    @_cleanup.before_loop
    async def _before_cleanup(self) -> None:
        await self.bot.wait_until_ready()

    # ─── Hooks appelés par scanner.py ─────────────────────────────────────────

    async def on_ally_connect(self, pseudo: str) -> None:
        """
        Appelé par scanner.py quand un allié se connecte.
        Si ça fait passer le total à 2+, on ouvre la fenêtre danger.
        """
        self._allies_online.add(pseudo.lower())
        count = len(self._allies_online)
        log.info("[Anti] Allié connecté : %s (total alliés online : %d)", pseudo, count)

        if count >= 2 and self._danger_since is None:
            self._danger_since = time.time()
            log.info("[Anti] ⚠️ 2 alliés connectés → fenêtre danger ouverte")

    async def on_ally_disconnect(self, pseudo: str) -> None:
        """
        Appelé par scanner.py quand un allié se déconnecte.
        Si on tombe sous 2 alliés, on ferme la fenêtre danger.
        """
        self._allies_online.discard(pseudo.lower())
        count = len(self._allies_online)
        log.info("[Anti] Allié déconnecté : %s (total alliés online : %d)", pseudo, count)

        if count < 2:
            self._danger_since = None
            log.info("[Anti] Moins de 2 alliés → fenêtre danger fermée")

    async def on_sword_disconnect(self, pseudo: str) -> None:
        """
        Appelé par scanner.py quand un sword (watchlist) se déconnecte.
        Si la fenêtre danger est active → alerte anti.
        """
        now = time.time()

        if self._danger_since is None:
            return  # Pas de danger actif, rien à signaler

        if now - self._danger_since > ANTI_WINDOW:
            # Fenêtre expirée
            self._danger_since = None
            return

        # Cooldown par sword
        last_alert = self._alert_cooldown.get(pseudo.lower(), 0)
        if now - last_alert < ALERT_COOLDOWN:
            log.debug("[Anti] Cooldown actif pour sword %s", pseudo)
            return

        self._alert_cooldown[pseudo.lower()] = now
        delay = now - self._danger_since
        nb_allies = len(self._allies_online)
        await self._send_alert(pseudo, delay, nb_allies)

    # ─── Envoi de l'alerte ────────────────────────────────────────────────────

    async def _send_alert(self, sword: str, delay_seconds: float, nb_allies: int) -> None:
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

        embed = self._build_embed(sword, delay_seconds, nb_allies)
        try:
            await ch.send(embed=embed)
            log.info("[Anti] Alerte : %s a fui (%.0fs après passage à 2 alliés)", sword, delay_seconds)
        except discord.DiscordException as exc:
            log.warning("[Anti] Envoi alerte échoué: %s", exc)

    def _build_embed(self, sword: str, delay_seconds: float, nb_allies: int) -> discord.Embed:
        minutes = int(delay_seconds // 60)
        seconds = int(delay_seconds % 60)
        delay_str = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"

        allies_str = ", ".join(f"`{a}`" for a in self._allies_online) if self._allies_online else "?"

        embed = discord.Embed(
            title="🏃 Anti détecté !",
            description=(
                f"**`{sword}`** s'est déconnecté **{delay_str}** après le passage à **{nb_allies} alliés** connectés.\n"
                f"Il a fui pour éviter de se faire action."
            ),
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="⚔️ Sword", value=f"`{sword}`", inline=True)
        embed.add_field(name="👥 Alliés connectés", value=allies_str, inline=True)
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
        self._allies_online.discard(pseudo.lower())
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

        lines = []
        for a in allies:
            if a.lower() in self._allies_online:
                lines.append(f"🟢 `{a}` — connecté")
            else:
                lines.append(f"⚫ `{a}`")

        nb_online = len(self._allies_online)
        danger = self._danger_since is not None and time.time() - self._danger_since <= ANTI_WINDOW
        status = f"⚠️ Fenêtre danger ACTIVE ({nb_online} alliés co)" if danger else f"✅ Pas de danger ({nb_online} allié(s) co)"

        embed = discord.Embed(
            title="👥 Liste des alliés",
            description="\n".join(lines),
            color=discord.Color.red() if danger else discord.Color.blue(),
        )
        embed.add_field(name="Statut", value=status, inline=False)
        embed.set_footer(text=f"{len(allies)} allié(s) — trigger : 2 connectés simultanément")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @allies_group.command(name="seed", description="[ONE-SHOT] Importer la liste des alliés de base")
    @admin_only()
    async def allies_seed(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        added, skipped = 0, 0
        for pseudo in ALLIES_SEED:
            if await db.ally_add(pseudo):
                added += 1
            else:
                skipped += 1
        log.info("Seed alliés : %d ajoutés, %d skippés (par %s)", added, skipped, interaction.user)
        await interaction.followup.send(
            embed=discord.Embed(
                title="🌱 Seed alliés terminé",
                description=f"✅ **{added}** allié(s) ajouté(s)\n⏭️ **{skipped}** déjà présent(s)",
                color=discord.Color.green(),
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AntiDetectorCog(bot))
