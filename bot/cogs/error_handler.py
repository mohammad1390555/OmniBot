# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Global error handling: friendly messages for every command failure."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from bot.core.bot import OmniBot
from bot.utils import embeds
from bot.utils.checks import ModuleDisabled

log = # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # logging.getLogger("omnibot.errors")


class ErrorHandler(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        # unwrap CommandInvokeError
        original = getattr(error, "original", error)

        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send(embed=embeds.error(
                f"Missing argument: `{error.param.name}`"))

        if isinstance(error, commands.BadArgument):
            return await ctx.send(embed=embeds.error(f"Invalid argument: {error}"))

        if isinstance(error, commands.NoPrivateMessage):
            return await ctx.send(embed=embeds.error("This command can't be used in DMs."))

        if isinstance(error, commands.MissingPermissions):
            perms = ", ".join(error.missing_permissions)
            return await ctx.send(embed=embeds.error(
                await self.bot.tr(ctx.guild.id if ctx.guild else None,
                                  "error_no_permission")))

        if isinstance(error, commands.BotMissingPermissions):
            perms = ", ".join(error.missing_permissions)
            return await ctx.send(embed=embeds.error(
                await self.bot.tr(ctx.guild.id if ctx.guild else None,
                                  "error_bot_no_permission", perms=perms)))

        if isinstance(error, commands.CommandOnCooldown):
            return await ctx.send(embed=embeds.error(
                await self.bot.tr(ctx.guild.id if ctx.guild else None,
                                  "error_cooldown", seconds=error.retry_after)))

        if isinstance(error, ModuleDisabled):
            return await ctx.send(embed=embeds.error(
                await self.bot.tr(ctx.guild.id if ctx.guild else None,
                                  "error_disabled_module", module=error.module)))

        if isinstance(error, commands.NotOwner):
            return await ctx.send(embed=embeds.error("Owner only command."))

        if isinstance(error, commands.CheckFailure):
            return await ctx.send(embed=embeds.error(
                await self.bot.tr(ctx.guild.id if ctx.guild else None, "error_no_permission")))

        log.exception("Unhandled command error", exc_info=original)
        await ctx.send(embed=embeds.error(
            await self.bot.tr(ctx.guild.id if ctx.guild else None, "error_generic")))


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(ErrorHandler(bot))
