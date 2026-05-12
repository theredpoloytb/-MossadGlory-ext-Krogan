"""
database/db.py — Couche d'accès hybride :
  - Watchlist → MongoDB (persist entre redeploys)
  - Player state, config, alerts → SQLite (local, rapide)
"""
from __future__ import annotations

import aiosqlite
import logging
import os
from pathlib import Path
from typing import Any

import config

log = logging.getLogger("krogan.db")

# ─── MongoDB (motor) ──────────────────────────────────────────────────────────
_mongo_col = None  # collection "krogan_watchlist"

async def init_mongo() -> None:
    global _mongo_col
    mongo_url = os.getenv("MONGO_URL")
    if not mongo_url:
        log.warning("MONGO_URL non défini — watchlist en SQLite uniquement")
        return
    try:
        import motor.motor_asyncio as motor
        client = motor.AsyncIOMotorClient(
            mongo_url,
            serverSelectionTimeoutMS=8000,
            tls=True,
            tlsAllowInvalidCertificates=True,
        )
        await client.admin.command("ping")
        _mongo_col = client["mossadglory"]["krogan_watchlist"]
        log.info("✅ MongoDB connecté (collection krogan_watchlist)")
    except Exception as exc:
        log.warning("MongoDB indisponible: %s — fallback SQLite", exc)
        _mongo_col = None


# ─── Init SQLite ──────────────────────────────────────────────────────────────

async def init_db() -> None:
    """Crée les tables SQLite + init MongoDB."""
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS watchlist (
                pseudo      TEXT PRIMARY KEY COLLATE NOCASE,
                added_at    TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS player_state (
                pseudo          TEXT PRIMARY KEY COLLATE NOCASE,
                online          INTEGER NOT NULL DEFAULT 0,
                online_since    TEXT,
                offline_since   TEXT,
                out_until       TEXT,
                last_seen       TEXT
            );

            CREATE TABLE IF NOT EXISTS bot_config (
                key     TEXT PRIMARY KEY,
                value   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS alert_state (
                pseudo          TEXT NOT NULL,
                alert_type      TEXT NOT NULL,
                fired_at        TEXT NOT NULL,
                PRIMARY KEY (pseudo, alert_type)
            );
        """)
        await db.commit()
    await init_mongo()
    # Sync watchlist MongoDB → SQLite au démarrage
    if _mongo_col is not None:
        await _sync_mongo_to_sqlite()
    log.info("DB initialisée → %s", config.DB_PATH)


async def _sync_mongo_to_sqlite() -> None:
    """Importe la watchlist MongoDB dans SQLite local au démarrage."""
    try:
        cursor = _mongo_col.find({}, {"pseudo": 1})
        pseudos = [doc["pseudo"] async for doc in cursor]
        async with aiosqlite.connect(config.DB_PATH) as db:
            for pseudo in pseudos:
                await db.execute(
                    "INSERT OR IGNORE INTO watchlist (pseudo) VALUES (?)", (pseudo,)
                )
                await db.execute(
                    "INSERT OR IGNORE INTO player_state (pseudo) VALUES (?)", (pseudo,)
                )
            await db.commit()
        log.info("Sync MongoDB→SQLite: %d joueurs importés", len(pseudos))
    except Exception as exc:
        log.warning("Sync MongoDB→SQLite échouée: %s", exc)


# ─── Watchlist ────────────────────────────────────────────────────────────────

async def wl_add(pseudo: str) -> bool:
    """Ajoute dans MongoDB + SQLite. Retourne False si déjà présent."""
    # SQLite
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "SELECT 1 FROM watchlist WHERE pseudo = ?", (pseudo,)
        )
        if await cur.fetchone():
            return False
        await db.execute("INSERT INTO watchlist (pseudo) VALUES (?)", (pseudo,))
        await db.execute(
            "INSERT OR IGNORE INTO player_state (pseudo) VALUES (?)", (pseudo,)
        )
        await db.commit()
    # MongoDB
    if _mongo_col is not None:
        try:
            await _mongo_col.update_one(
                {"pseudo": pseudo},
                {"$setOnInsert": {"pseudo": pseudo}},
                upsert=True,
            )
        except Exception as exc:
            log.warning("MongoDB wl_add: %s", exc)
    return True


async def wl_remove(pseudo: str) -> bool:
    """Supprime de MongoDB + SQLite. Retourne False si introuvable."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM watchlist WHERE pseudo = ?", (pseudo,)
        )
        await db.execute("DELETE FROM player_state WHERE pseudo = ?", (pseudo,))
        await db.execute("DELETE FROM alert_state WHERE pseudo = ?", (pseudo,))
        await db.commit()
        removed = cur.rowcount > 0
    if _mongo_col is not None:
        try:
            await _mongo_col.delete_one({"pseudo": pseudo})
        except Exception as exc:
            log.warning("MongoDB wl_remove: %s", exc)
    return removed


async def wl_list() -> list[str]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "SELECT pseudo FROM watchlist ORDER BY pseudo COLLATE NOCASE"
        )
        rows = await cur.fetchall()
        return [r[0] for r in rows]


async def wl_exists(pseudo: str) -> bool:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "SELECT 1 FROM watchlist WHERE pseudo = ?", (pseudo,)
        )
        return await cur.fetchone() is not None


# ─── Player state ─────────────────────────────────────────────────────────────

async def get_player(pseudo: str) -> dict[str, Any] | None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM player_state WHERE pseudo = ?", (pseudo,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_all_players() -> list[dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT ps.* FROM player_state ps
            INNER JOIN watchlist w ON w.pseudo = ps.pseudo
            ORDER BY ps.pseudo COLLATE NOCASE
            """
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def upsert_player(pseudo: str, **kwargs: Any) -> None:
    if not kwargs:
        return
    cols = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [pseudo]
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            f"UPDATE player_state SET {cols} WHERE pseudo = ?", vals
        )
        await db.commit()


async def set_out(pseudo: str, out_until: str | None) -> None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE player_state SET out_until = ? WHERE pseudo = ?",
            (out_until, pseudo),
        )
        await db.commit()


# ─── Config bot ───────────────────────────────────────────────────────────────

async def cfg_get(key: str, default: str | None = None) -> str | None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "SELECT value FROM bot_config WHERE key = ?", (key,)
        )
        row = await cur.fetchone()
        return row[0] if row else default


async def cfg_set(key: str, value: str) -> None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO bot_config (key, value) VALUES (?, ?)",
            (key, value),
        )
        await db.commit()


async def cfg_get_int(key: str, default: int) -> int:
    val = await cfg_get(key)
    try:
        return int(val) if val is not None else default
    except (ValueError, TypeError):
        return default


# ─── Alert state ──────────────────────────────────────────────────────────────

async def alert_get(pseudo: str, alert_type: str) -> str | None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "SELECT fired_at FROM alert_state WHERE pseudo = ? AND alert_type = ?",
            (pseudo, alert_type),
        )
        row = await cur.fetchone()
        return row[0] if row else None


async def alert_set(pseudo: str, alert_type: str, fired_at: str) -> None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO alert_state (pseudo, alert_type, fired_at) VALUES (?, ?, ?)",
            (pseudo, alert_type, fired_at),
        )
        await db.commit()


async def alert_clear(pseudo: str, alert_type: str) -> None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "DELETE FROM alert_state WHERE pseudo = ? AND alert_type = ?",
            (pseudo, alert_type),
        )
        await db.commit()
