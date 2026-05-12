"""
main.py — Point d'entrée de MossadGlory ext Krogan.
Lance le bot Discord avec tous les cogs + serveur HTTP keep-alive pour Render Web Service.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

import aiohttp
from aiohttp import web
import discord
from discord.ext import commands

# Ajoute la racine au path pour les imports
sys.path.insert(0, str(Path(__file__).parent))

import config
from bot.database.db import init_db

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("krogan.main")

# ─── Bot ──────────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.guilds = True
intents.members = False  # pas besoin de privileged intents

bot = commands.Bot(
    command_prefix="!",  # non utilisé (slash only), juste requis
    intents=intents,
    help_command=None,
)

COGS: list[str] = [
    "bot.cogs.watchlist",
    "bot.cogs.out",
    "bot.cogs.scanner",
    "bot.cogs.admin_config",
    "bot.cogs.roles",
]


# ─── Events ───────────────────────────────────────────────────────────────────

@bot.event
async def on_ready() -> None:
    log.info("✅ Connecté en tant que %s (ID: %s)", bot.user, bot.user.id)
    # Sync les slash commands sur le guild configuré
    if config.GUILD_ID:
        guild = discord.Object(id=config.GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        log.info("Slash commands synchronisées sur guild %s", config.GUILD_ID)
    else:
        await bot.tree.sync()
        log.info("Slash commands synchronisées globalement (peut prendre 1h)")


@bot.event
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> None:
    """Gestion globale des erreurs de slash commands."""
    if isinstance(error, app_commands.CheckFailure):
        # Déjà géré dans les checks individuels
        return
    log.exception("Erreur slash command: %s", error)
    try:
        if interaction.response.is_done():
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ Erreur inattendue : `{error}`",
                    color=0xE74C3C,
                ),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"❌ Erreur inattendue : `{error}`",
                    color=0xE74C3C,
                ),
                ephemeral=True,
            )
    except discord.DiscordException:
        pass


# ─── Main ─────────────────────────────────────────────────────────────────────

# ─── Serveur HTTP keep-alive (requis pour Render Web Service) ─────────────────

async def handle_health(request: web.Request) -> web.Response:
    return web.Response(text="OK", status=200)


async def start_webserver() -> None:
    """Lance un mini serveur HTTP sur PORT pour que Render ne kill pas le service."""
    app = web.Application()
    app.router.add_get("/", handle_health)
    app.router.add_get("/health", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info("🌐 Serveur HTTP keep-alive démarré sur port %s", port)


async def self_ping() -> None:
    """Ping le service toutes les 10 min pour éviter le sleep de Render."""
    render_url = os.getenv("RENDER_EXTERNAL_URL", "")
    if not render_url:
        return
    url = render_url if render_url.startswith("http") else f"https://{render_url}"
    await asyncio.sleep(60)
    while True:
        try:
            async with aiohttp.ClientSession() as s:
                await s.get(url, timeout=aiohttp.ClientTimeout(total=10))
            log.debug("Self-ping OK → %s", url)
        except Exception:
            pass
        await asyncio.sleep(600)


async def main() -> None:
    if not config.DISCORD_TOKEN:
        log.critical("DISCORD_TOKEN manquant. Configure ton .env !")
        sys.exit(1)

    # Init DB
    await init_db()

    # Serveur HTTP keep-alive + self-ping (pour Render Web Service)
    await start_webserver()
    asyncio.ensure_future(self_ping())

    # Chargement des cogs
    async with bot:
        for cog in COGS:
            try:
                await bot.load_extension(cog)
                log.info("Cog chargé: %s", cog)
            except Exception as exc:
                log.exception("Erreur chargement cog %s: %s", cog, exc)

        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
