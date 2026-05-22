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
_CACHE_TTL = 1  # seconde
_last_403_log: float = 0.0
_403_LOG_INTERVAL = 60  # log le 403 max 1 fois par minute

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


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
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8), headers=_HEADERS) as resp:
            if resp.status != 200:
                global _last_403_log
                now2 = time.monotonic()
                if now2 - _last_403_log > _403_LOG_INTERVAL:
                    log.warning("dynmap HTTP %s pour %s", resp.status, url)
                    _last_403_log = now2
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
