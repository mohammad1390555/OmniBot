# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Auto-moderation: word filter, links, invites, mentions, caps, emoji."""

from __future__ import annotations

import re

import discord
from discord.ext import commands

from bot.core.bot import OmniBot
from bot.core.config import config
from bot.core.database import db
from bot.utils import embeds
from bot.utils.checks import is_mod, module_enabled
from bot.utils.timeutil import parse_duration

INVITE_RE = re.compile(r"(discord\.gg|discord(app)?\.com/invite)/[A-Za-z0-9]+", re.I)
LINK_RE = re.compile(r"https?://\S+", re.I)
EMOJI_RE = re.compile(r"<a?:\w+:\d+>")


class AutoMod(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot

    async def _automod_cfg(self, guild_id: int) -> dict:
        stored = await db.get_guild_setting(guild_id, "automod", {}) or {}
        return {
            "enabled": stored.get("enabled", bool(config.get("automod.enabled", True))),
            "banned_words": stored.get("banned_words", config.get("automod.banned_words", [])),
            "block_invite_links": stored.get("block_invite_links", bool(config.get("automod.block_invite_links", True))),
            "block_all_links": stored.get("block_all_links", bool(config.get("automod.block_all_links", False))),
            "max_mentions": stored.get("max_mentions", int(config.get("automod.max_mentions", 8))),
            "max_caps_percent": stored.get("max_caps_percent", int(config.get("automod.max_caps_percent", 0))),
            "max_emojis": stored.get("max_emojis", int(config.get("automod.max_emojis", 12))),
            "punishment": stored.get("punishment", config.get("automod.punishment", "delete")),
            "mute_duration": stored.get("mute_duration", config.get("automod.mute_duration", "10m")),
            "exempt_channels": stored.get("exempt_channels", []),
        }

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        if not await db.module_enabled(message.guild.id, "automod"):
            return
        if isinstance(message.author, discord.Member) and message.author.guild_permissions.manage_messages:
            return

        cfg = await self._automod_cfg(message.guild.id)
        if not cfg["enabled"]:
            return
        if message.channel.id in [int(c) for c in cfg["exempt_channels"]]:
            return

        content = message.content or ""
        reason_key = None

        lowered = content.lower()
        for word in cfg["banned_words"]:
            if word and word.lower() in lowered:
                reason_key = "automod_reason_word"
                break

        if reason_key is None and cfg["block_invite_links"] and INVITE_RE.search(content):
            reason_key = "automod_reason_invite"
        if reason_key is None and cfg["block_all_links"] and LINK_RE.search(content):
            reason_key = "automod_reason_link"
        if reason_key is None and cfg["max_mentions"] and len(message.mentions) > cfg["max_mentions"]:
            reason_key = "automod_reason_mentions"
        if reason_key is None and cfg["max_emojis"] and len(EMOJI_RE.findall(content)) > cfg["max_emojis"]:
            reason_key = "automod_reason_emoji"
        if reason_key is None and cfg["max_caps_percent"]:
            letters = [c for c in content if c.isalpha()]
            if len(letters) >= 10:
                caps = sum(1 for c in letters if c.isupper())
                if caps / len(letters) * 100 > cfg["max_caps_percent"]:
                    reason_key = "automod_reason_caps"

        if reason_key is None:
            return

        try:
            await message.delete()
        except discord.HTTPException:
            return

        lang_guild = message.guild.id
        try:
            await message.author.send(embed=embeds.error(await self.bot.tr(
                lang_guild, "automod_deleted", channel=message.channel.mention)))
        except discord.HTTPException:
            pass

        punishment = cfg["punishment"]
        if punishment in ("mute", "kick", "ban") and isinstance(message.author, discord.Member):
            try:
                if punishment == "mute":
                    delta = parse_duration(cfg["mute_duration"]) or parse_duration("10m")
                    await message.author.timeout(delta, reason="automod")
                elif punishment == "kick":
                    await message.author.kick(reason="automod")
                elif punishment == "ban":
                    await message.author.ban(reason="automod", delete_message_days=0)
            except discord.HTTPException:
                pass

    # ------------------------------------------------------------------
    @commands.hybrid_group(name="automod", description="Configure auto-moderation.", invoke_without_command=True)
    @commands.guild_only()
    @module_enabled("automod")
    @is_mod()
    async def automod(self, ctx: commands.Context) -> None:
        cfg = await self._automod_cfg(ctx.guild.id)
        lines = [
            f"**Enabled:** {cfg['enabled']}",
            f"**Block invites:** {cfg['block_invite_links']}",
            f"**Block all links:** {cfg['block_all_links']}",
            f"**Max mentions:** {cfg['max_mentions']}",
            f"**Max caps %:** {cfg['max_caps_percent']}",
            f"**Max emojis:** {cfg['max_emojis']}",
            f"**Punishment:** {cfg['punishment']}",
            f"**Banned words:** {len(cfg['banned_words'])}",
        ]
        await ctx.send(embed=embeds.titled("🛡️ AutoMod", "\n".join(lines)))

    @automod.command(name="toggle", description="Enable or disable automod.")
    async def automod_toggle(self, ctx: commands.Context, enabled: bool) -> None:
        cfg = await self._automod_cfg(ctx.guild.id)
        cfg["enabled"] = enabled
        await db.set_guild_setting(ctx.guild.id, "automod", cfg)
        await ctx.send(embed=embeds.success(await self.bot.tr(ctx.guild.id, "automod_config_updated")))

    @automod.command(name="addword", description="Add a banned word.")
    async def automod_addword(self, ctx: commands.Context, *, word: str) -> None:
        cfg = await self._automod_cfg(ctx.guild.id)
        if word.lower() not in [w.lower() for w in cfg["banned_words"]]:
            cfg["banned_words"].append(word)
        await db.set_guild_setting(ctx.guild.id, "automod", cfg)
        await ctx.send(embed=embeds.success(await self.bot.tr(ctx.guild.id, "automod_config_updated")))

    @automod.command(name="removeword", description="Remove a banned word.")
    async def automod_removeword(self, ctx: commands.Context, *, word: str) -> None:
        cfg = await self._automod_cfg(ctx.guild.id)
        cfg["banned_words"] = [w for w in cfg["banned_words"] if w.lower() != word.lower()]
        await db.set_guild_setting(ctx.guild.id, "automod", cfg)
        await ctx.send(embed=embeds.success(await self.bot.tr(ctx.guild.id, "automod_config_updated")))

    @automod.command(name="invites", description="Toggle invite link blocking.")
    async def automod_invites(self, ctx: commands.Context, enabled: bool) -> None:
        cfg = await self._automod_cfg(ctx.guild.id)
        cfg["block_invite_links"] = enabled
        await db.set_guild_setting(ctx.guild.id, "automod", cfg)
        await ctx.send(embed=embeds.success(await self.bot.tr(ctx.guild.id, "automod_config_updated")))

    @automod.command(name="punishment", description="Set punishment: delete | mute | kick | ban.")
    async def automod_punishment(self, ctx: commands.Context, punishment: str) -> None:
        if punishment not in ("delete", "warn", "mute", "kick", "ban"):
            return await ctx.send(embed=embeds.error("Choose: delete, warn, mute, kick, ban"))
        cfg = await self._automod_cfg(ctx.guild.id)
        cfg["punishment"] = punishment
        await db.set_guild_setting(ctx.guild.id, "automod", cfg)
        await ctx.send(embed=embeds.success(await self.bot.tr(ctx.guild.id, "automod_config_updated")))


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(AutoMod(bot))
