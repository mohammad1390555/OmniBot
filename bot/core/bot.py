# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""The OmniBot client class.

Wires together config, database, i18n and cog loading.
"""

from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord.ext import commands

from .config import config
from .database import db

log = # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # logging.getLogger("omnibot")

COGS_DIR = Path(__file__).resolve().parents[1] / "cogs"


class OmniBot(commands.Bot):
    """commands.Bot subclass with config/db/i18n conveniences."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = bool(config.get("bot.intents.message_content", True))
        intents.members = bool(config.get("bot.intents.members", True))
        intents.voice_states = bool(config.get("bot.intents.voice_states", True))
        intents.presences = bool(config.get("bot.intents.presences", False))

        super().__init__(
            command_prefix=self._prefix,
            intents=intents,
            help_command=None,  # custom interactive help cog
            case_insensitive=True,
        )

    # -- dynamic per-guild prefix -------------------------------------
    async def _prefix(self, bot: commands.Bot, message: discord.Message):
        if message.guild is None:
            return commands.when_mentioned_or(config.default_prefix)(bot, message)
        g = await db.get_guild(message.guild.id)
        prefix = g["prefix"] or config.default_prefix
        return commands.when_mentioned_or(prefix)(bot, message)

    # -- i18n ----------------------------------------------------------
    async def tr(self, guild_id: int | None, key: str, **kwargs) -> str:
        lang = config.default_language
        if guild_id is not None:
            g = await db.get_guild(guild_id)
            lang = g["language"]
        return config.tr(lang, key, **kwargs)

    def tr_sync(self, lang: str, key: str, **kwargs) -> str:
        return config.tr(lang, key, **kwargs)

    # -- lifecycle -----------------------------------------------------
    async def setup_hook(self) -> None:
        await db.connect()
        log.info("Database connected.")

        for path in sorted(COGS_DIR.glob("*.py")):
            if path.name.startswith("_"):
                continue
            ext = f"bot.cogs.{path.stem}"
            try:
                await self.load_extension(ext)
                log.info("Loaded cog: %s", ext)
            except Exception:
                log.exception("Failed to load cog: %s", ext)

        await self.tree.sync()
        log.info("Slash commands synced.")

    async def on_ready(self) -> None:
        log.info("Logged in as %s (id=%s) | %s guild(s)",
                 self.user, self.user.id, len(self.guilds))
        await self._apply_presence()

    async def _apply_presence(self) -> None:
        text = config.get("bot.presence.text", "/help | OmniBot")
        kind = str(config.get("bot.presence.activity", "watching")).lower()
        status_raw = str(config.get("bot.presence.status", "online")).lower()
        status = getattr(discord.Status, status_raw, discord.Status.online)
        activity_map = {
            "playing": discord.ActivityType.playing,
            "watching": discord.ActivityType.watching,
            "listening": discord.ActivityType.listening,
            "competing": discord.ActivityType.competing,
        }
        activity = discord.Activity(
            type=activity_map.get(kind, discord.ActivityType.watching), name=text
        )
        await self.change_presence(activity=activity, status=status)

    async def is_owner_id(self, user_id: int) -> bool:
        if user_id in config.owner_ids:
            return True
        app = await self.application_info()
        if app.team:
            return user_id in {m.id for m in app.team.members}
        return user_id == app.owner.id
