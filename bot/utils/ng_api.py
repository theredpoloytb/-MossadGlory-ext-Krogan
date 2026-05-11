"""
utils/ng_api.py — Fetcher NationsGlory dynmap
Récupère la liste des joueurs connectés sur un serveur via son dynmap.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp
import config

log = logging.getLogger("krogan.ng_api")

_cache: dict[str, Any] = {"players": [], "ts": 0.0}
_CACHE_TTL = 20  # secondes


async def fetch_online_players(session: aiohttp.ClientSession) -> list[str]:
    """
    Retourne la liste des pseudos connectés sur config.NG_SERVER.
    Utilise un cache TTL pour ne pas spammer le dynmap.
    """
    now = time.monotonic()
    if now - _cache["ts"] < _CACHE_TTL:
        return list(_cache["players"])

    url = config.NG_DYNMAP_URL
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                log.warning("dynmap HTTP %s pour %s", resp.status, url)
                return list(_cache["players"])
            data = await resp.json(content_type=None)
            players: list[str] = [
                p["account"] for p in data.get("players", []) if "account" in p
            ]
            _cache["players"] = players
            _cache["ts"] = now
            return players
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        log.warning("Erreur fetch dynmap: %s", exc)
        return list(_cache["players"])


def invalidate_cache() -> None:
    _cache["ts"] = 0.0
