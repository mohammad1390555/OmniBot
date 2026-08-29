# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Async SQLite database layer with in-memory caching and robust indexing.

All persistent state (guild settings, cases, economy, leveling, tickets,
giveaways, reminders, timers, shop, starboard, birthdays) lives here so everything survives restarts.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import aiosqlite

from .config import config

log = logging.getLogger("omnibot.database")

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
    bank        INTEGER DEFAULT 0,
    last_daily  TEXT,
    last_weekly TEXT,
    last_work   TEXT,
    last_rob    TEXT,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS shop_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    name        TEXT NOT NULL,
    description TEXT,
    price       INTEGER NOT NULL,
    role_id     INTEGER
);

CREATE TABLE IF NOT EXISTS user_inventory (
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    item_id     INTEGER NOT NULL,
    quantity    INTEGER DEFAULT 1,
    PRIMARY KEY (guild_id, user_id, item_id)
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

CREATE TABLE IF NOT EXISTS level_roles (
    guild_id    INTEGER NOT NULL,
    level       INTEGER NOT NULL,
    role_id     INTEGER NOT NULL,
    PRIMARY KEY (guild_id, level)
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
    last_celebrated TEXT,
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

-- Performance Indices
CREATE INDEX IF NOT EXISTS idx_cases_guild_user ON cases (guild_id, user_id);
CREATE INDEX IF NOT EXISTS idx_warnings_guild_user ON warnings (guild_id, user_id);
CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders (done, remind_at);
CREATE INDEX IF NOT EXISTS idx_temp_actions_status ON temp_actions (done, expires_at);
CREATE INDEX IF NOT EXISTS idx_giveaways_active ON giveaways (ended, ends_at);
CREATE INDEX IF NOT EXISTS idx_economy_lb ON economy (guild_id, balance DESC);
CREATE INDEX IF NOT EXISTS idx_leveling_lb ON leveling (guild_id, xp DESC);
"""


class Database:
    """Async wrapper around aiosqlite with JSON helpers and guild memory cache."""

    def __init__(self) -> None:
        self._db: aiosqlite.Connection | None = None
        self._guild_cache: dict[int, dict[str, Any]] = {}

    async def connect(self) -> None:
        path = Path(config.sqlite_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        # Migrate columns safely if needed (e.g. bank in economy)
        try:
            await self._db.execute("ALTER TABLE economy ADD COLUMN bank INTEGER DEFAULT 0")
            await self._db.commit()
        except Exception:
            pass
        try:
            await self._db.execute("ALTER TABLE economy ADD COLUMN last_rob TEXT")
            await self._db.commit()
        except Exception:
            pass
        try:
            await self._db.execute("ALTER TABLE birthdays ADD COLUMN last_celebrated TEXT")
            await self._db.commit()
        except Exception:
            pass
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

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

    # -- guild settings with cache -----------------------------------
    async def ensure_guild(self, guild_id: int) -> None:
        await self.execute(
            "INSERT OR IGNORE INTO guilds (guild_id) VALUES (?)", (guild_id,)
        )

    async def get_guild(self, guild_id: int) -> dict[str, Any]:
        if guild_id in self._guild_cache:
            return self._guild_cache[guild_id]

        await self.ensure_guild(guild_id)
        row = await self.fetchone(
            "SELECT * FROM guilds WHERE guild_id = ?", (guild_id,)
        )
        if not row:
            data = {
                "guild_id": guild_id,
                "prefix": None,
                "language": config.default_language,
                "modules": {},
                "settings": {},
            }
        else:
            modules_raw = row["modules"] or "{}"
            settings_raw = row["settings"] or "{}"
            try:
                modules = json.loads(modules_raw) if isinstance(modules_raw, str) else dict(modules_raw)
            except Exception:
                modules = {}
            try:
                settings = json.loads(settings_raw) if isinstance(settings_raw, str) else dict(settings_raw)
            except Exception:
                settings = {}

            data = {
                "guild_id": row["guild_id"],
                "prefix": row["prefix"],
                "language": row["language"] or config.default_language,
                "modules": modules,
                "settings": settings,
            }

        self._guild_cache[guild_id] = data
        return data

    def invalidate_guild_cache(self, guild_id: int) -> None:
        self._guild_cache.pop(guild_id, None)

    async def set_guild_field(self, guild_id: int, field: str, value: Any) -> None:
        await self.ensure_guild(guild_id)
        db_val = json.dumps(value) if field in ("modules", "settings") else value
        await self.execute(
            f"UPDATE guilds SET {field} = ? WHERE guild_id = ?", (db_val, guild_id)
        )
        # Update cache directly
        if guild_id in self._guild_cache:
            self._guild_cache[guild_id][field] = value
        else:
            self.invalidate_guild_cache(guild_id)

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
