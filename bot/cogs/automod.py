# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Auto-moderation: word filter, links, invites, mentions, caps, emoji, anti-spam, anti-phishing, ghost-ping."""

from __future__ import annotations

import collections
import re
import time

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
PHISHING_KEYWORDS = [
    "discorcl", "dlscord", "discorcd", "discord-nitro", "free-nitro", "steamcommunity-gift",
    "steamcomminuty", "gift-nitro", "claim-nitro", "discord-gifts", "nitro-free"
]


class AutoMod(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot
        # (guild_id, user_id) -> deque of message timestamps
        self._spam_tracker: dict[tuple[int, int], collections.deque[float]] = collections.defaultdict(
            lambda: collections.deque(maxlen=20)
        )
        # message_id -> (author, mentions, content, timestamp, channel_id)
        self._recent_mentions: dict[int, dict] = {}

    async def _automod_cfg(self, guild_id: int) -> dict:
        stored = await db.get_guild_setting(guild_id, "automod", {}) or {}
        return {
            "enabled": stored.get("enabled", bool(config.get("automod.enabled", True))),
            "banned_words": stored.get("banned_words", config.get("automod.banned_words", [])),
            "block_invite_links": stored.get("block_invite_links", bool(config.get("automod.block_invite_links", True))),
            "block_all_links": stored.get("block_all_links", bool(config.get("automod.block_all_links", False))),
            "block_phishing": stored.get("block_phishing", True),
            "max_mentions": stored.get("max_mentions", int(config.get("automod.max_mentions", 8))),
            "max_caps_percent": stored.get("max_caps_percent", int(config.get("automod.max_caps_percent", 0))),
            "max_emojis": stored.get("max_emojis", int(config.get("automod.max_emojis", 12))),
            "anti_spam": stored.get("anti_spam", True),
            "anti_ghostping": stored.get("anti_ghostping", True),
            "spam_rate": stored.get("spam_rate", 5),  # max messages
            "spam_per": stored.get("spam_per", 5),    # in seconds
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
        now = time.time()

        # Track ghost ping candidates
        if cfg["anti_ghostping"] and message.mentions:
            valid_mentions = [m for m in message.mentions if not m.bot and m.id != message.author.id]
            if valid_mentions:
                self._recent_mentions[message.id] = {
                    "author": message.author,
                    "mentions": valid_mentions,
                    "content": content,
                    "time": now,
                    "channel_id": message.channel.id,
                }
                # Cleanup old cache
                if len(self._recent_mentions) > 500:
                    cutoff = now - 120
                    self._recent_mentions = {k: v for k, v in self._recent_mentions.items() if v["time"] > cutoff}

        # Anti-Spam Check
        if cfg["anti_spam"]:
            key = (message.guild.id, message.author.id)
            timestamps = self._spam_tracker[key]
            timestamps.append(now)
            window = cfg["spam_per"]
            recent = [t for t in timestamps if now - t <= window]
            if len(recent) > cfg["spam_rate"]:
                reason_key = "automod_reason_spam"

        lowered = content.lower()

        # Phishing check
        if reason_key is None and cfg["block_phishing"]:
            for keyword in PHISHING_KEYWORDS:
                if keyword in lowered:
                    reason_key = "automod_reason_phishing"
                    break

        # Banned words check
        if reason_key is None:
            for word in cfg["banned_words"]:
                if word and word.lower() in lowered:
                    reason_key = "automod_reason_word"
                    break

        # Invites / Links / Limits
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
        if isinstance(message.author, discord.Member):
            try:
                if punishment == "warn":
                    bot_id = self.bot.user.id if self.bot.user else 0
                    await db.execute(
                        "INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)",
                        (message.guild.id, message.author.id, bot_id, f"AutoMod: {reason_key}"),
                    )
                elif punishment == "mute":
                    delta = parse_duration(cfg["mute_duration"]) or parse_duration("10m")
                    await message.author.timeout(delta, reason=f"AutoMod: {reason_key}")
                elif punishment == "kick":
                    await message.author.kick(reason=f"AutoMod: {reason_key}")
                elif punishment == "ban":
                    await message.author.ban(reason=f"AutoMod: {reason_key}", delete_message_days=0)
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild is None or message.id not in self._recent_mentions:
            return
        data = self._recent_mentions.pop(message.id)
        if time.time() - data["time"] > 60:
            return
        if not await db.module_enabled(message.guild.id, "automod"):
            return
        cfg = await self._automod_cfg(message.guild.id)
        if not cfg["anti_ghostping"]:
            return

        mentions_str = " ".join(m.mention for m in data["mentions"])
        embed = embeds.titled(
            "👻 Ghost Ping Detected",
            f"**Author:** {data['author'].mention}\n"
            f"**Mentions:** {mentions_str}\n"
            f"**Content:**\n{data['content'][:500] or '(no content)'}"
        )
        embed.color = discord.Color.orange()
        try:
            await message.channel.send(embed=embed)
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
            f"**Enabled:** {'✅' if cfg['enabled'] else '❌'}",
            f"**Anti-Spam:** {'✅' if cfg['anti_spam'] else '❌'} ({cfg['spam_rate']} msgs / {cfg['spam_per']}s)",
            f"**Anti-Phishing:** {'✅' if cfg['block_phishing'] else '❌'}",
            f"**Anti-GhostPing:** {'✅' if cfg['anti_ghostping'] else '❌'}",
            f"**Block Invites:** {'✅' if cfg['block_invite_links'] else '❌'}",
            f"**Block All Links:** {'✅' if cfg['block_all_links'] else '❌'}",
            f"**Max Mentions:** `{cfg['max_mentions']}`",
            f"**Max Caps %:** `{cfg['max_caps_percent']}%`",
            f"**Max Emojis:** `{cfg['max_emojis']}`",
            f"**Punishment:** `{cfg['punishment']}` ({cfg['mute_duration']})",
            f"**Banned Words:** `{len(cfg['banned_words'])}`",
        ]
        await ctx.send(embed=embeds.titled("🛡️ AutoMod Configuration", "\n".join(lines)))

    @automod.command(name="toggle", description="Enable or disable automod.")
    async def automod_toggle(self, ctx: commands.Context, enabled: bool) -> None:
        cfg = await self._automod_cfg(ctx.guild.id)
        cfg["enabled"] = enabled
        await db.set_guild_setting(ctx.guild.id, "automod", cfg)
        await ctx.send(embed=embeds.success(await self.bot.tr(ctx.guild.id, "automod_config_updated")))

    @automod.command(name="antispam", description="Configure anti-spam filter.")
    async def automod_antispam(self, ctx: commands.Context, enabled: bool, max_msgs: int = 5, seconds: int = 5) -> None:
        cfg = await self._automod_cfg(ctx.guild.id)
        cfg["anti_spam"] = enabled
        cfg["spam_rate"] = max(2, min(max_msgs, 20))
        cfg["spam_per"] = max(2, min(seconds, 30))
        await db.set_guild_setting(ctx.guild.id, "automod", cfg)
        await ctx.send(embed=embeds.success(f"Anti-spam set: enabled={enabled}, {cfg['spam_rate']} msgs in {cfg['spam_per']}s."))

    @automod.command(name="ghostping", description="Toggle anti-ghostping notifications.")
    async def automod_ghostping(self, ctx: commands.Context, enabled: bool) -> None:
        cfg = await self._automod_cfg(ctx.guild.id)
        cfg["anti_ghostping"] = enabled
        await db.set_guild_setting(ctx.guild.id, "automod", cfg)
        await ctx.send(embed=embeds.success(f"Anti-ghostping set to: {enabled}."))

    @automod.command(name="phishing", description="Toggle anti-phishing/scam filter.")
    async def automod_phishing(self, ctx: commands.Context, enabled: bool) -> None:
        cfg = await self._automod_cfg(ctx.guild.id)
        cfg["block_phishing"] = enabled
        await db.set_guild_setting(ctx.guild.id, "automod", cfg)
        await ctx.send(embed=embeds.success(f"Anti-phishing set to: {enabled}."))

    @automod.command(name="links", description="Toggle blocking all links.")
    async def automod_links(self, ctx: commands.Context, enabled: bool) -> None:
        cfg = await self._automod_cfg(ctx.guild.id)
        cfg["block_all_links"] = enabled
        await db.set_guild_setting(ctx.guild.id, "automod", cfg)
        await ctx.send(embed=embeds.success(f"Block all links set to: {enabled}."))

    @automod.command(name="caps", description="Set max caps percentage (0 to disable).")
    async def automod_caps(self, ctx: commands.Context, percent: int) -> None:
        percent = max(0, min(percent, 100))
        cfg = await self._automod_cfg(ctx.guild.id)
        cfg["max_caps_percent"] = percent
        await db.set_guild_setting(ctx.guild.id, "automod", cfg)
        await ctx.send(embed=embeds.success(f"Max caps percentage set to: {percent}%."))

    @automod.command(name="mentions", description="Set max user mentions allowed per message (0 to disable).")
    async def automod_mentions(self, ctx: commands.Context, max_count: int) -> None:
        max_count = max(0, min(max_count, 50))
        cfg = await self._automod_cfg(ctx.guild.id)
        cfg["max_mentions"] = max_count
        await db.set_guild_setting(ctx.guild.id, "automod", cfg)
        await ctx.send(embed=embeds.success(f"Max mentions set to: {max_count}."))

    @automod.command(name="emojis", description="Set max emojis allowed per message (0 to disable).")
    async def automod_emojis(self, ctx: commands.Context, max_count: int) -> None:
        max_count = max(0, min(max_count, 100))
        cfg = await self._automod_cfg(ctx.guild.id)
        cfg["max_emojis"] = max_count
        await db.set_guild_setting(ctx.guild.id, "automod", cfg)
        await ctx.send(embed=embeds.success(f"Max emojis set to: {max_count}."))

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

    @automod.command(name="punishment", description="Set punishment: delete | warn | mute | kick | ban.")
    async def automod_punishment(self, ctx: commands.Context, punishment: str, mute_duration: str = "10m") -> None:
        if punishment not in ("delete", "warn", "mute", "kick", "ban"):
            return await ctx.send(embed=embeds.error("Choose: delete, warn, mute, kick, ban"))
        cfg = await self._automod_cfg(ctx.guild.id)
        cfg["punishment"] = punishment
        cfg["mute_duration"] = mute_duration
        await db.set_guild_setting(ctx.guild.id, "automod", cfg)
        await ctx.send(embed=embeds.success(await self.bot.tr(ctx.guild.id, "automod_config_updated")))


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(AutoMod(bot))
