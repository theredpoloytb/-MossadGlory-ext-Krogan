"""
cogs/scanner.py — Boucle de scan NationsGlory.

Toutes les SCAN_INTERVAL secondes :
  1. Fetch les joueurs connectés sur lime
  2. Compare avec l'état DB
  3. Détecte connexions / déconnexions / retours OUT
  4. Met à jour l'embed live
  5. Envoie les alertes si seuils dépassés (avec cooldown anti-spam)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta

PARIS = timezone(timedelta(hours=2))

import aiohttp
import discord
from discord.ext import commands, tasks

import config
from bot.database import db
from bot.utils import embeds, ng_api

log = logging.getLogger("krogan.scanner")

# Types d'alertes suivies
ALERT_TYPES = ("action", "infiltration", "missile")


class ScannerCog(commands.Cog, name="Scanner"):
    """Boucle de scan et gestion des alertes automatiques."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._session: aiohttp.ClientSession | None = None
        # ID du message live (persisté en DB)
        self._live_msg_id: int | None = None

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    async def cog_load(self) -> None:
        self._session = aiohttp.ClientSession()
        # Récupère le message live depuis la DB
        raw = await db.cfg_get("live_msg_id")
        if raw and raw.isdigit():
            self._live_msg_id = int(raw)
        self.scan_loop.change_interval(seconds=1)
        self.scan_loop.start()
        log.info("Scanner démarré (intervalle %ss, serveur %s)", config.SCAN_INTERVAL, config.NG_SERVER)

    async def cog_unload(self) -> None:
        self.scan_loop.cancel()
        if self._session:
            await self._session.close()

    # ─── Boucle principale ────────────────────────────────────────────────────

    @tasks.loop(seconds=30)
    async def scan_loop(self) -> None:
        """Tick principal du scanner."""
        try:
            await self._tick()
        except Exception as exc:
            log.exception("Erreur dans scan_loop: %s", exc)

    @scan_loop.before_loop
    async def before_scan(self) -> None:
        await self.bot.wait_until_ready()

    # ─── Tick ─────────────────────────────────────────────────────────────────

    async def _tick(self) -> None:
        if not self._session:
            return

        # 1. Joueurs connectés sur lime
        online_now: list[str] = await ng_api.fetch_online_players(self._session)
        online_set = {p.lower() for p in online_now}

        # 2. Watchlist
        pseudos = await db.wl_list()
        if not pseudos:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        now_time = datetime.now(PARIS).strftime("%H:%M")

        logs_to_send: list[discord.Embed] = []

        for pseudo in pseudos:
            player = await db.get_player(pseudo)
            if not player:
                continue

            was_online = bool(player["online"])
            is_online = pseudo.lower() in online_set

            # ── Retrait OUT automatique ────────────────────────────────────
            if player.get("out_until"):
                if now_time >= player["out_until"]:
                    await db.set_out(pseudo, None)
                    log.info("OUT expiré auto: %s", pseudo)
                    logs_to_send.append(embeds.embed_log_out_returned(pseudo))
                    # Recharge le state
                    player = await db.get_player(pseudo) or player

            # ── Transition connexion ───────────────────────────────────────
            if not was_online and is_online:
                await db.upsert_player(
                    pseudo,
                    online=1,
                    online_since=now_iso,
                    offline_since=player.get("offline_since"),
                    last_seen=now_iso,
                )
                log.info("🟢 %s connecté", pseudo)
                logs_to_send.append(embeds.embed_log_connect(pseudo))

            elif was_online and not is_online:
                await db.upsert_player(
                    pseudo,
                    online=0,
                    offline_since=now_iso,
                    last_seen=now_iso,
                )
                log.info("🔴 %s déconnecté", pseudo)
                logs_to_send.append(embeds.embed_log_disconnect(pseudo))

            elif is_online:
                await db.upsert_player(pseudo, last_seen=now_iso)

        # 3. Joueurs actifs (connectés hors OUT)
        all_players = await db.get_all_players()
        active = [
            p for p in all_players
            if p["online"] and not p["out_until"]
        ]
        nb_active = len(active)

        # 4. Update embed live
        await self._update_live(all_players, nb_active)

        # 5. Envoi logs
        await self._send_logs(logs_to_send)

        # 6. Alertes basées sur le nombre de joueurs connectés
        await self._check_alerts(nb_active, [p["pseudo"] for p in active])

    # ─── Live embed ───────────────────────────────────────────────────────────

    async def _update_live(
        self, players: list[dict], actions_total: int
    ) -> None:
        ch_id = await db.cfg_get_int("channel_live", config.CHANNEL_LIVE)
        if not ch_id:
            return
        guild = self.bot.guilds[0] if self.bot.guilds else None
        if not guild:
            return
        ch = guild.get_channel(ch_id)
        if not ch or not isinstance(ch, discord.TextChannel):
            return

        emb = embeds.embed_live(players, actions_total)

        # Edition ou création du message live
        if self._live_msg_id:
            try:
                msg = await ch.fetch_message(self._live_msg_id)
                await msg.edit(embed=emb)
                return
            except (discord.NotFound, discord.HTTPException):
                self._live_msg_id = None

        # Crée un nouveau message live
        try:
            msg = await ch.send(embed=emb)
            self._live_msg_id = msg.id
            await db.cfg_set("live_msg_id", str(msg.id))
        except discord.DiscordException as exc:
            log.warning("Impossible de créer le message live: %s", exc)

    # ─── Logs ────────────────────────────────────────────────────────────────

    async def _send_logs(self, log_embeds: list[discord.Embed]) -> None:
        if not log_embeds:
            return
        ch_id = await db.cfg_get_int("channel_logs", config.CHANNEL_LOGS)
        if not ch_id:
            return
        guild = self.bot.guilds[0] if self.bot.guilds else None
        if not guild:
            return
        ch = guild.get_channel(ch_id)
        if not ch or not isinstance(ch, discord.TextChannel):
            return
        for emb in log_embeds:
            try:
                await ch.send(embed=emb)
                await asyncio.sleep(0.3)  # anti rate-limit
            except discord.DiscordException as exc:
                log.warning("Envoi log échoué: %s", exc)

    # ─── Alertes ─────────────────────────────────────────────────────────────

    async def _check_alerts(self, actions: int, online_pseudos: list[str]) -> None:
        """
        Vérifie les seuils et envoie les alertes avec cooldown.
        Gère aussi les messages "plus possible".
        """
        ch_id = await db.cfg_get_int("channel_alerts", config.CHANNEL_ALERTS)
        if not ch_id:
            return
        guild = self.bot.guilds[0] if self.bot.guilds else None
        if not guild:
            return
        ch = guild.get_channel(ch_id)
        if not ch or not isinstance(ch, discord.TextChannel):
            return

        # Récupère les seuils (DB override ou config.py)
        thr_action       = await db.cfg_get_int("threshold_action",       config.THRESHOLD_ACTION)
        thr_infiltration = await db.cfg_get_int("threshold_infiltration",  config.THRESHOLD_INFILTRATION)
        thr_missile      = await db.cfg_get_int("threshold_missile",       config.THRESHOLD_MISSILE)
        cooldown         = await db.cfg_get_int("alert_cooldown",          config.ALERT_COOLDOWN)

        thresholds = {
            "action":       (thr_action,        config.ROLE_ALERT_ACTION),
            "infiltration": (thr_infiltration,  config.ROLE_ALERT_INFILTRATION),
            "missile":      (thr_missile,       config.ROLE_ALERT_MISSILE),
        }

        now = datetime.now(timezone.utc)

        for atype, (threshold, role_id) in thresholds.items():
            # Alerte "possible"
            fired_at_raw = await db.alert_get("__global__", atype)
            fired_at = (
                datetime.fromisoformat(fired_at_raw) if fired_at_raw else None
            )

            if actions >= threshold:
                # Déjà envoyé + cooldown pas expiré ?
                if fired_at:
                    elapsed = (now - fired_at).total_seconds()
                    if elapsed < cooldown:
                        continue

                # Ping rôle
                role_mention = ""
                raw_role_id = await db.cfg_get_int(f"role_{atype}", role_id)
                if raw_role_id:
                    role = guild.get_role(raw_role_id)
                    role_mention = role.mention if role else ""

                emb = embeds.embed_alert(atype, actions, online_pseudos)
                try:
                    await ch.send(content=role_mention or None, embed=emb)
                    await db.alert_set("__global__", atype, now.isoformat())
                    # Efface le flag "plus possible" correspondant
                    await db.alert_clear("__global__", f"no_{atype}")
                    log.info("Alerte %s envoyée (%d actions)", atype, actions)
                except discord.DiscordException as exc:
                    log.warning("Envoi alerte %s échoué: %s", atype, exc)

            else:
                # Seuil redescendu → envoie "plus possible" si on avait alerté
                if fired_at:
                    no_fired_raw = await db.alert_get("__global__", f"no_{atype}")
                    if not no_fired_raw:
                        emb = embeds.embed_alert(f"no_{atype}", actions, [])
                        try:
                            await ch.send(embed=emb)
                            await db.alert_set("__global__", f"no_{atype}", now.isoformat())
                            await db.alert_clear("__global__", atype)
                            log.info("Alerte no_%s envoyée", atype)
                        except discord.DiscordException as exc:
                            log.warning("Envoi no_alerte %s échoué: %s", atype, exc)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ScannerCog(bot))
