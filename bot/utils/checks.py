"""Permission checks and module gating for commands."""

from __future__ import annotations

from discord.ext import commands

from bot.core.database import db


class ModuleDisabled(commands.CheckFailure):
    def __init__(self, module: str) -> None:
        self.module = module
        super().__init__(f"Module '{module}' is disabled on this server.")


def module_enabled(module: str):
    """Check that a feature module is enabled for the invoking guild."""

    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return True
        if not await db.module_enabled(ctx.guild.id, module):
            raise ModuleDisabled(module)
        return True

    return commands.check(predicate)


def is_staff():
    """Manage-guild permission or above."""
    return commands.has_guild_permissions(manage_guild=True)


def is_mod():
    return commands.has_guild_permissions(kick_members=True)


def is_admin():
    return commands.has_guild_permissions(administrator=True)
