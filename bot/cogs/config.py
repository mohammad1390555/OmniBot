# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Server configuration: prefix, language, module toggles, settings viewer."""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.core.bot import OmniBot
from bot.core.config import config
from bot.core.database import db
from bot.utils import embeds
from bot.utils.checks import is_admin, is_mod, module_enabled

ALL_MODULES = ["moderation", "automod", "logging", "utility", "fun",
               "economy", "leveling", "tickets", "giveaways", "welcome",
               "roles", "music"]


class Config(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot

    @commands.hybrid_group(name="config", description="Server configuration.",
                           invoke_without_command=True)
    @commands.guild_only()
    @is_mod()
    async def config_group(self, ctx: commands.Context) -> None:
        g = await db.get_guild(ctx.guild.id)
        lines = [
            f"**Prefix:** `{g['prefix'] or config.default_prefix}`",
            f"**Language:** {g['language']}",
        ]
        for mod in ALL_MODULES:
            enabled = await db.module_enabled(ctx.guild.id, mod)
            lines.append(f"**{mod}:** {'✅' if enabled else '❌'}")
        settings = g["settings"]
        if settings:
            keys = ", ".join(f"`{k}`" for k in list(settings)[:15])
            lines.append(f"\n**Configured keys:** {keys}")
        await ctx.send(embed=embeds.titled(
            await self.bot.tr(ctx.guild.id, "config_title"), "\n".join(lines)))

    @config_group.command(name="prefix", description="Set the command prefix.")
    @is_admin()
    async def config_prefix(self, ctx: commands.Context, prefix: str) -> None:
        if len(prefix) > 10:
            return await ctx.send(embed=embeds.error("Prefix too long (max 10 chars)."))
        await db.set_guild_field(ctx.guild.id, "prefix", prefix)
        await ctx.send(embed=embeds.success(await self.bot.tr(
            ctx.guild.id, "config_prefix_set", prefix=prefix)))

    @config_group.command(name="language", description="Set the bot language (en | fa).")
    @is_admin()
    async def config_language(self, ctx: commands.Context, lang: str) -> None:
        if lang not in config.messages:
            langs = ", ".join(config.messages.keys())
            return await ctx.send(embed=embeds.error(f"Available languages: {langs}"))
        await db.set_guild_field(ctx.guild.id, "language", lang)
        await ctx.send(embed=embeds.success(await self.bot.tr(
            ctx.guild.id, "config_lang_set", lang=lang)))

    @config_group.command(name="modules", description="Enable/disable a feature module.")
    @is_admin()
    async def config_modules(self, ctx: commands.Context, module: str, enabled: bool) -> None:
        module = module.lower()
        if module not in ALL_MODULES:
            return await ctx.send(embed=embeds.error(
                f"Unknown module. Available: {', '.join(ALL_MODULES)}"))
        await db.set_module(ctx.guild.id, module, enabled)
        await ctx.send(embed=embeds.success(await self.bot.tr(
            ctx.guild.id, "config_updated", key=f"modules.{module}", value=enabled)))

    @config_group.command(name="set", description="Set a channel setting (welcome_channel, suggestion_channel, ...).")
    @is_mod()
    async def config_set(self, ctx: commands.Context, key: str,
                         channel: discord.TextChannel) -> None:
        allowed = {"welcome_channel", "leave_channel", "suggestion_channel",
                   "message_log_channel", "member_log_channel", "voice_log_channel",
                   "server_log_channel", "mod_log_channel", "ticket_log_channel"}
        if key not in allowed:
            return await ctx.send(embed=embeds.error(
                f"Allowed keys: {', '.join(sorted(allowed))}"))
        await db.set_guild_setting(ctx.guild.id, key, channel.id)
        await ctx.send(embed=embeds.success(await self.bot.tr(
            ctx.guild.id, "config_updated", key=key, value=channel.mention)))


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(Config(bot))
