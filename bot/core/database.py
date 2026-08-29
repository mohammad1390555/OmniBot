# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Async SQLite database layer.

All persistent state (guild settings, cases, economy, leveling, tickets,
giveaways, reminders, timers) lives here so everything survives restarts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

from .config import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS guilds (
    guild_id    INTEGER PRIMARY KEY,
    prefix      TEXT,
    language    TEXT DEFAULT 'en',
    modules     TEXT DEFAULT '{}',
    settings    TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS cases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    moderator_id INTEGER,
    action      TEXT NOT NULL,
    reason      TEXT,
    duration    TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS warnings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    moderator_id INTEGER,
    reason      TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS economy (
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    balance     INTEGER DEFAULT 0,
    last_daily  TEXT,
    last_weekly TEXT,
    last_work   TEXT,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS leveling (
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    xp          INTEGER DEFAULT 0,
    level       INTEGER DEFAULT 0,
    messages    INTEGER DEFAULT 0,
    last_xp     TEXT,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS tickets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    channel_id  INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    status      TEXT DEFAULT 'open',
    claimed_by  INTEGER,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS giveaways (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    channel_id  INTEGER NOT NULL,
    message_id  INTEGER NOT NULL,
    prize       TEXT NOT NULL,
    winners     INTEGER DEFAULT 1,
    ends_at     TEXT NOT NULL,
    host_id     INTEGER,
    entries     TEXT DEFAULT '[]',
    ended       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reminders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER,
    channel_id  INTEGER,
    user_id     INTEGER NOT NULL,
    message     TEXT,
    remind_at   TEXT NOT NULL,
    done        INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS temp_actions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    action      TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    done        INTEGER DEFAULT 0,
    meta        TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS tags (
    guild_id    INTEGER NOT NULL,
    name        TEXT NOT NULL,
    content     TEXT NOT NULL,
    author_id   INTEGER,
    uses        INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id, name)
);

CREATE TABLE IF NOT EXISTS autoroles (
    guild_id    INTEGER NOT NULL,
    role_id     INTEGER NOT NULL,
    PRIMARY KEY (guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS starboard (
    guild_id    INTEGER NOT NULL,
    message_id  INTEGER NOT NULL,
    channel_id  INTEGER NOT NULL,
    stars       INTEGER DEFAULT 0,
    posted_id   INTEGER,
    PRIMARY KEY (guild_id, message_id)
);

CREATE TABLE IF NOT EXISTS birthdays (
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    month       INTEGER NOT NULL,
    day         INTEGER NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS counters (
    guild_id    INTEGER PRIMARY KEY,
    count       INTEGER DEFAULT 0,
    last_user   INTEGER
);

CREATE TABLE IF NOT EXISTS afk (
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    reason      TEXT,
    since       TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS suggestions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    content     TEXT NOT NULL,
    message_id  INTEGER,
    status      TEXT DEFAULT 'pending',
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS snipes (
    guild_id    INTEGER NOT NULL,
    channel_id  INTEGER NOT NULL,
    author      TEXT,
    content     TEXT,
    kind        TEXT DEFAULT 'delete',
    at          TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (guild_id, channel_id, kind)
);
"""


class Database:
    """Thin async wrapper around aiosqlite with JSON helpers."""

    def __init__(self) -> None:
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        path = Path(config.sqlite_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    @property
    def db(self) -> aiosqlite.Connection:
        assert self._db is not None, "Database not connected"
        return self._db

    # -- generic helpers ---------------------------------------------
    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        cur = await self.db.execute(sql, params)
        await self.db.commit()
        return cur

    async def fetchone(self, sql: str, params: tuple = ()) -> Any:
        cur = await self.db.execute(sql, params)
        return await cur.fetchone()

    async def fetchall(self, sql: str, params: tuple = ()) -> list[Any]:
        cur = await self.db.execute(sql, params)
        return await cur.fetchall()

    # -- guild settings ----------------------------------------------
    async def ensure_guild(self, guild_id: int) -> None:
        await self.execute(
            "INSERT OR IGNORE INTO guilds (guild_id) VALUES (?)", (guild_id,)
        )

    async def get_guild(self, guild_id: int) -> dict[str, Any]:
        await self.ensure_guild(guild_id)
        row = await self.fetchone(
            "SELECT * FROM guilds WHERE guild_id = ?", (guild_id,)
        )
        return {
            "guild_id": row["guild_id"],
            "prefix": row["prefix"],
            "language": row["language"] or config.default_language,
            "modules": json.loads(row["modules"] or "{}"),
            "settings": json.loads(row["settings"] or "{}"),
        }

    async def set_guild_field(self, guild_id: int, field: str, value: Any) -> None:
        await self.ensure_guild(guild_id)
        if field in ("modules", "settings"):
            value = json.dumps(value)
        await self.execute(
            f"UPDATE guilds SET {field} = ? WHERE guild_id = ?", (value, guild_id)
        )

    async def set_guild_setting(self, guild_id: int, key: str, value: Any) -> None:
        g = await self.get_guild(guild_id)
        g["settings"][key] = value
        await self.set_guild_field(guild_id, "settings", g["settings"])

    async def get_guild_setting(self, guild_id: int, key: str, default: Any = None) -> Any:
        g = await self.get_guild(guild_id)
        return g["settings"].get(key, default)

    async def set_module(self, guild_id: int, module: str, enabled: bool) -> None:
        g = await self.get_guild(guild_id)
        g["modules"][module] = enabled
        await self.set_guild_field(guild_id, "modules", g["modules"])

    async def module_enabled(self, guild_id: int, module: str) -> bool:
        g = await self.get_guild(guild_id)
        if module in g["modules"]:
            return bool(g["modules"][module])
        return bool(config.get(f"modules.{module}", True))


db = Database()
