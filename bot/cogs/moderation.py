# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Moderation: ban, kick, mute, warn, purge, lock, slowmode, cases."""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.core.bot import OmniBot
from bot.core.config import config
from bot.core.database import db
from bot.utils import embeds
from bot.utils.checks import is_mod, module_enabled
from bot.utils.timeutil import discord_ts, format_duration, parse_duration, utcnow
from bot.utils.views import ConfirmView


class Moderation(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    async def _log_case(self, guild: discord.Guild, user_id: int,
                        moderator: discord.abc.User, action: str,
                        reason: str, duration: str | None = None) -> int:
        cur = await db.execute(
            "INSERT INTO cases (guild_id, user_id, moderator_id, action, reason, duration)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (guild.id, user_id, moderator.id, action, reason, duration),
        )
        return cur.lastrowid or 0

    async def _notify_log(self, guild: discord.Guild, text: str) -> None:
        channel_id = await db.get_guild_setting(guild.id, "mod_log_channel")
        if not channel_id:
            return
        channel = guild.get_channel(int(channel_id))
        if channel:
            try:
                await channel.send(embed=embeds.info(text))
            except discord.HTTPException:
                pass

    def _hierarchy_ok(self, me: discord.Member, target: discord.Member) -> bool:
        return me.top_role > target.top_role

    # ------------------------------------------------------------------
    @commands.hybrid_command(name="ban", description="Ban a member from the server.")
    @commands.guild_only()
    @module_enabled("moderation")
    @is_mod()
    @commands.bot_has_guild_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member,
                  reason: str = "No reason provided") -> None:
        if member.id == ctx.author.id:
            return await ctx.send(embed=embeds.error(await self.bot.tr(ctx.guild.id, "mod_cannot_punish_self")))
        if member.id == ctx.guild.owner_id:
            return await ctx.send(embed=embeds.error(await self.bot.tr(ctx.guild.id, "mod_cannot_punish_owner")))
        if not self._hierarchy_ok(ctx.guild.me, member):
            return await ctx.send(embed=embeds.error(await self.bot.tr(ctx.guild.id, "mod_cannot_punish")))

        await member.ban(reason=f"{ctx.author} | {reason}", delete_message_days=0)
        case_id = await self._log_case(ctx.guild, member.id, ctx.author, "ban", reason)
        await ctx.send(embed=embeds.success(
            await self.bot.tr(ctx.guild.id, "mod_ban_success", user=str(member))))
        await self._notify_log(ctx.guild, f"🔨 **{member}** banned by {ctx.author} — `{reason}` (case #{case_id})")

    @commands.hybrid_command(name="unban", description="Unban a user by ID or name#discriminator.")
    @commands.guild_only()
    @module_enabled("moderation")
    @is_mod()
    @commands.bot_has_guild_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user: discord.User,
                    reason: str = "No reason provided") -> None:
        await ctx.guild.unban(user, reason=f"{ctx.author} | {reason}")
        await self._log_case(ctx.guild, user.id, ctx.author, "unban", reason)
        await ctx.send(embed=embeds.success(
            await self.bot.tr(ctx.guild.id, "mod_unban_success", user=str(user))))

    @commands.hybrid_command(name="kick", description="Kick a member from the server.")
    @commands.guild_only()
    @module_enabled("moderation")
    @is_mod()
    @commands.bot_has_guild_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member,
                   reason: str = "No reason provided") -> None:
        if member.id == ctx.author.id:
            return await ctx.send(embed=embeds.error(await self.bot.tr(ctx.guild.id, "mod_cannot_punish_self")))
        if not self._hierarchy_ok(ctx.guild.me, member):
            return await ctx.send(embed=embeds.error(await self.bot.tr(ctx.guild.id, "mod_cannot_punish")))

        await member.kick(reason=f"{ctx.author} | {reason}")
        case_id = await self._log_case(ctx.guild, member.id, ctx.author, "kick", reason)
        await ctx.send(embed=embeds.success(
            await self.bot.tr(ctx.guild.id, "mod_kick_success", user=str(member))))
        await self._notify_log(ctx.guild, f"👢 **{member}** kicked by {ctx.author} — `{reason}` (case #{case_id})")

    @commands.hybrid_command(name="softban", description="Ban then immediately unban to delete messages.")
    @commands.guild_only()
    @module_enabled("moderation")
    @is_mod()
    @commands.bot_has_guild_permissions(ban_members=True)
    async def softban(self, ctx: commands.Context, member: discord.Member,
                      reason: str = "No reason provided") -> None:
        if not self._hierarchy_ok(ctx.guild.me, member):
            return await ctx.send(embed=embeds.error(await self.bot.tr(ctx.guild.id, "mod_cannot_punish")))

        await member.ban(reason=f"softban by {ctx.author} | {reason}", delete_message_days=1)
        await ctx.guild.unban(member, reason="softban unban")
        await self._log_case(ctx.guild, member.id, ctx.author, "softban", reason)
        await ctx.send(embed=embeds.success(
            await self.bot.tr(ctx.guild.id, "mod_softban_success", user=str(member))))

    @commands.hybrid_command(name="mute", description="Timeout a member (e.g. 10m, 1h, 1d).")
    @commands.guild_only()
    @module_enabled("moderation")
    @is_mod()
    @commands.bot_has_guild_permissions(moderate_members=True)
    async def mute(self, ctx: commands.Context, member: discord.Member,
                   duration: str, *, reason: str = "No reason provided") -> None:
        delta = parse_duration(duration)
        if delta is None:
            return await ctx.send(embed=embeds.error("Invalid duration. Examples: `10m`, `1h`, `1d`."))
        if not self._hierarchy_ok(ctx.guild.me, member):
            return await ctx.send(embed=embeds.error(await self.bot.tr(ctx.guild.id, "mod_cannot_punish")))

        until = utcnow() + delta
        await member.timeout(delta, reason=f"{ctx.author} | {reason}")
        await self._log_case(ctx.guild, member.id, ctx.author, "mute", reason, duration)
        await ctx.send(embed=embeds.success(await self.bot.tr(
            ctx.guild.id, "mod_timeout_success", user=str(member), until=discord_ts(until, "R"))))

    @commands.hybrid_command(name="unmute", description="Remove a timeout from a member.")
    @commands.guild_only()
    @module_enabled("moderation")
    @is_mod()
    @commands.bot_has_guild_permissions(moderate_members=True)
    async def unmute(self, ctx: commands.Context, member: discord.Member) -> None:
        await member.timeout(None, reason=f"unmute by {ctx.author}")
        await self._log_case(ctx.guild, member.id, ctx.author, "unmute", "Manual unmute")
        await ctx.send(embed=embeds.success(
            await self.bot.tr(ctx.guild.id, "mod_unmute_success", user=str(member))))

    @commands.hybrid_command(name="warn", description="Warn a member (DM + logged).")
    @commands.guild_only()
    @module_enabled("moderation")
    @is_mod()
    async def warn(self, ctx: commands.Context, member: discord.Member,
                   *, reason: str = "No reason provided") -> None:
        if member.id == ctx.author.id:
            return await ctx.send(embed=embeds.error(await self.bot.tr(ctx.guild.id, "mod_cannot_punish_self")))

        await db.execute(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)",
            (ctx.guild.id, member.id, ctx.author.id, reason),
        )
        row = await db.fetchone(
            "SELECT COUNT(*) AS c FROM warnings WHERE guild_id = ? AND user_id = ?",
            (ctx.guild.id, member.id),
        )
        count = row["c"] if row else 1
        try:
            await member.send(await self.bot.tr(
                ctx.guild.id, "mod_warn_dm", server=ctx.guild.name, reason=reason))
        except discord.HTTPException:
            pass
        await self._log_case(ctx.guild, member.id, ctx.author, "warn", reason)
        await ctx.send(embed=embeds.success(await self.bot.tr(
            ctx.guild.id, "mod_warn_success", user=str(member), count=count)))

    @commands.hybrid_command(name="warnings", description="View a member's warning history.")
    @commands.guild_only()
    @module_enabled("moderation")
    @is_mod()
    async def warnings(self, ctx: commands.Context, member: discord.Member) -> None:
        rows = await db.fetchall(
            "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT 25",
            (ctx.guild.id, member.id),
        )
        if not rows:
            return await ctx.send(embed=embeds.info(
                await self.bot.tr(ctx.guild.id, "mod_warnings_empty", user=str(member))))
        lines = []
        for r in rows:
            ts = ""
            try:
                from bot.utils.timeutil import from_iso
                ts = f" <t:{int(from_iso(r['created_at']).timestamp())}:R>"
            # FIXME: [auto-fix]: handle exception
            lines.append(f"**#{r['id']}** — {r['reason']}{ts}")
        embed = embeds.titled(
            await self.bot.tr(ctx.guild.id, "mod_history_title", user=str(member)),
            "\n".join(lines))
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="purge", description="Delete messages (optional: by user).")
    @commands.guild_only()
    @module_enabled("moderation")
    @is_mod()
    @commands.bot_has_guild_permissions(manage_messages=True)
    async def purge(self, ctx: commands.Context, amount: int = 50,
                    member: discord.Member | None = None) -> None:
        max_purge = int(config.get("moderation.max_purge", 500))
        amount = max(1, min(amount, max_purge))
        await ctx.message.delete()

        def check(m: discord.Message) -> bool:
            return member is None or m.author.id == member.id

        deleted = await ctx.channel.purge(limit=amount, check=check)
        msg = await ctx.send(embed=embeds.success(
            await self.bot.tr(ctx.guild.id, "mod_purge_success", count=len(deleted))))
        await discord.utils.sleep_delay(3)
        try:
            await msg.delete()
        except discord.HTTPException:
            pass

    @commands.hybrid_command(name="lock", description="Lock a channel (deny Send Messages for @everyone).")
    @commands.guild_only()
    @module_enabled("moderation")
    @is_mod()
    @commands.bot_has_guild_permissions(manage_channels=True)
    async def lock(self, ctx: commands.Context,
                   channel: discord.TextChannel | None = None) -> None:
        channel = channel or ctx.channel
        await channel.set_permissions(ctx.guild.default_role, send_messages=False,
                                      reason=f"locked by {ctx.author}")
        await ctx.send(embed=embeds.success(
            await self.bot.tr(ctx.guild.id, "mod_lock_success", channel=channel.mention)))

    @commands.hybrid_command(name="unlock", description="Unlock a channel.")
    @commands.guild_only()
    @module_enabled("moderation")
    @is_mod()
    @commands.bot_has_guild_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context,
                     channel: discord.TextChannel | None = None) -> None:
        channel = channel or ctx.channel
        await channel.set_permissions(ctx.guild.default_role, send_messages=None,
                                      reason=f"unlocked by {ctx.author}")
        await ctx.send(embed=embeds.success(
            await self.bot.tr(ctx.guild.id, "mod_unlock_success", channel=channel.mention)))

    @commands.hybrid_command(name="lockdown", description="Lock (or unlock) every channel at once.")
    @commands.guild_only()
    @module_enabled("moderation")
    @commands.has_guild_permissions(administrator=True)
    @commands.bot_has_guild_permissions(manage_channels=True)
    async def lockdown(self, ctx: commands.Context, release: bool = False) -> None:
        for channel in ctx.guild.text_channels:
            try:
                await channel.set_permissions(
                    ctx.guild.default_role,
                    send_messages=None if release else False,
                    reason=f"lockdown by {ctx.author}")
            except discord.HTTPException:
                continue
        key = "mod_lockdown_off" if release else "mod_lockdown_on"
        await ctx.send(embed=embeds.success(await self.bot.tr(ctx.guild.id, key)))

    @commands.hybrid_command(name="slowmode", description="Set channel slowmode (seconds, 0 to disable).")
    @commands.guild_only()
    @module_enabled("moderation")
    @is_mod()
    @commands.bot_has_guild_permissions(manage_channels=True)
    async def slowmode(self, ctx: commands.Context, seconds: int = 0) -> None:
        seconds = max(0, min(seconds, 21600))
        await ctx.channel.edit(slowmode_delay=seconds)
        key = "mod_slowmode_off" if seconds == 0 else "mod_slowmode_set"
        await ctx.send(embed=embeds.success(
            await self.bot.tr(ctx.guild.id, key, seconds=seconds, channel=ctx.channel.mention)))

    @commands.hybrid_command(name="nick", description="Set or reset a member's nickname.")
    @commands.guild_only()
    @module_enabled("moderation")
    @is_mod()
    @commands.bot_has_guild_permissions(manage_nicknames=True)
    async def nick(self, ctx: commands.Context, member: discord.Member,
                   *, nickname: str | None = None) -> None:
        await member.edit(nick=nickname, reason=f"nick by {ctx.author}")
        if nickname:
            await ctx.send(embed=embeds.success(await self.bot.tr(
                ctx.guild.id, "mod_nick_set", user=str(member), nick=nickname)))
        else:
            await ctx.send(embed=embeds.success(await self.bot.tr(
                ctx.guild.id, "mod_nick_reset", user=str(member))))

    @commands.hybrid_command(name="modlogs", description="View moderation case history for a user.")
    @commands.guild_only()
    @module_enabled("moderation")
    @is_mod()
    async def modlogs(self, ctx: commands.Context, member: discord.Member) -> None:
        rows = await db.fetchall(
            "SELECT * FROM cases WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT 25",
            (ctx.guild.id, member.id),
        )
        if not rows:
            return await ctx.send(embed=embeds.info(
                await self.bot.tr(ctx.guild.id, "mod_warnings_empty", user=str(member))))
        lines = [f"**#{r['id']}** `{r['action']}` — {r['reason']} (by <@{r['moderator_id']}>)"
                 for r in rows]
        embed = embeds.titled(
            await self.bot.tr(ctx.guild.id, "mod_history_title", user=str(member)),
            "\n".join(lines))
        await ctx.send(embed=embed)


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(Moderation(bot))
