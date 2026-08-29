# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Utility: ping, userinfo, serverinfo, avatar, banner, servericon, roleinfo, channelinfo, botinfo, math, translate, remind, poll, snipe, editsnipe, afk, suggestions."""

from __future__ import annotations

import ast
import asyncio
import math
import operator
import time
import urllib.parse

import aiohttp
import discord
from discord.ext import commands

from bot.core.bot import OmniBot
from bot.core.database import db
from bot.utils import embeds
from bot.utils.checks import is_mod, module_enabled
from bot.utils.timeutil import discord_ts, format_duration, parse_duration, utcnow

# Safe math evaluator operators
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    elif isinstance(node, ast.BinOp) and type(node.op) in SAFE_OPERATORS:
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        return SAFE_OPERATORS[type(node.op)](left, right)
    elif isinstance(node, ast.UnaryOp) and type(node.op) in SAFE_OPERATORS:
        operand = _safe_eval(node.operand)
        return SAFE_OPERATORS[type(node.op)](operand)
    raise ValueError("Unsupported operation or expression")


class Utility(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot
        self.start_time = time.time()

    # ------------------------------------------------------------------
    @commands.hybrid_command(name="ping", description="Check bot latency and gateway response time.")
    async def ping(self, ctx: commands.Context) -> None:
        start = time.perf_counter()
        msg = await ctx.send(embed=embeds.info("🏓 Pinging..."))
        api_ms = (time.perf_counter() - start) * 1000
        gateway_ms = self.bot.latency * 1000
        await msg.edit(embed=embeds.info(await self.bot.tr(
            ctx.guild.id if ctx.guild else None, "util_ping",
            gateway=f"{gateway_ms:.0f}", api=f"{api_ms:.0f}")))

    @commands.hybrid_command(name="userinfo", description="Show detailed info about a user.")
    @commands.guild_only()
    @module_enabled("utility")
    async def userinfo(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        member = member or ctx.author
        roles = ", ".join(r.mention for r in member.roles[1:][:25]) or "None"
        embed = embeds.titled(
            await self.bot.tr(ctx.guild.id, "util_userinfo_title", user=str(member)))
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="User ID", value=f"`{member.id}`", inline=True)
        embed.add_field(name="Bot Account", value="Yes" if member.bot else "No", inline=True)
        embed.add_field(name="Nickname", value=member.nick or "—", inline=True)
        embed.add_field(name="Registered", value=discord_ts(member.created_at, "R"), inline=True)
        embed.add_field(name="Joined Server", value=discord_ts(member.joined_at, "R") if member.joined_at else "—", inline=True)
        embed.add_field(name="Top Role", value=member.top_role.mention, inline=True)
        embed.add_field(name=f"Roles ({len(member.roles) - 1})", value=roles[:1000], inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="serverinfo", description="Show detailed info about this server.")
    @commands.guild_only()
    @module_enabled("utility")
    async def serverinfo(self, ctx: commands.Context) -> None:
        g = ctx.guild
        embed = embeds.titled(
            await self.bot.tr(g.id, "util_serverinfo_title", server=g.name))
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        embed.add_field(name="Owner", value=f"<@{g.owner_id}>", inline=True)
        embed.add_field(name="Server ID", value=f"`{g.id}`", inline=True)
        embed.add_field(name="Created", value=discord_ts(g.created_at, "R"), inline=True)
        embed.add_field(name="Members", value=f"{g.member_count:,}", inline=True)
        embed.add_field(name="Channels", value=f"{len(g.channels)} (Text: {len(g.text_channels)}, Voice: {len(g.voice_channels)})", inline=True)
        embed.add_field(name="Roles", value=f"{len(g.roles)}", inline=True)
        embed.add_field(name="Boost Level", value=f"Tier {g.premium_tier} ({g.premium_subscription_count} boosts)", inline=True)
        embed.add_field(name="Emojis", value=f"{len(g.emojis)}", inline=True)
        embed.add_field(name="Verification Level", value=str(g.verification_level).capitalize(), inline=True)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="avatar", description="Show a user's avatar in full size.")
    @module_enabled("utility")
    async def avatar(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        member = member or ctx.author
        embed = embeds.titled(
            await self.bot.tr(ctx.guild.id if ctx.guild else None, "util_avatar_title", user=str(member)))
        embed.set_image(url=member.display_avatar.with_size(1024).url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="banner", description="Show a user's profile banner.")
    @module_enabled("utility")
    async def banner(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        member = member or ctx.author
        fetched = await self.bot.fetch_user(member.id)
        if fetched.banner is None:
            return await ctx.send(embed=embeds.info(
                await self.bot.tr(ctx.guild.id if ctx.guild else None, "util_banner_none")))
        embed = embeds.titled(f"🖼️ Banner — {member.display_name}")
        embed.set_image(url=fetched.banner.with_size(1024).url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="servericon", description="Show server icon.")
    @commands.guild_only()
    @module_enabled("utility")
    async def servericon(self, ctx: commands.Context) -> None:
        if not ctx.guild.icon:
            return await ctx.send(embed=embeds.info("This server has no icon set."))
        embed = embeds.titled(f"🖼️ Server Icon — {ctx.guild.name}")
        embed.set_image(url=ctx.guild.icon.with_size(1024).url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="math", aliases=["calc"], description="Evaluate a math expression safely.")
    @module_enabled("utility")
    async def math_calc(self, ctx: commands.Context, *, expression: str) -> None:
        try:
            parsed = ast.parse(expression, mode="eval")
            result = _safe_eval(parsed.body)
            # Format cleanly
            res_str = f"{result:,.4f}".rstrip("0").rstrip(".")
            embed = embeds.titled("🧮 Calculator", f"**Expression:** `{expression}`\n**Result:** `{res_str}`")
            await ctx.send(embed=embed)
        except Exception:
            await ctx.send(embed=embeds.error("Invalid or unsupported mathematical expression."))

    @commands.hybrid_command(name="translate", description="Translate text into another language (e.g. en, fa, es, de, fr).")
    @module_enabled("utility")
    async def translate(self, ctx: commands.Context, target_lang: str, *, text: str) -> None:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={urllib.parse.quote(target_lang)}&dt=t&q={urllib.parse.quote(text)}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        translated = "".join([piece[0] for piece in data[0] if piece[0]])
                        src_lang = data[2] if len(data) > 2 else "auto"
                        embed = embeds.titled("🌐 Translation",
                                              f"**Original ({src_lang}):** {text}\n\n**Translated ({target_lang}):** {translated}")
                        return await ctx.send(embed=embed)
        except Exception:
            pass
        await ctx.send(embed=embeds.error("Failed to translate text. Please check language code."))

    @commands.hybrid_command(name="roleinfo", description="Show info about a role.")
    @commands.guild_only()
    @module_enabled("utility")
    async def roleinfo(self, ctx: commands.Context, role: discord.Role) -> None:
        members = sum(1 for m in ctx.guild.members if role in m.roles)
        embed = embeds.titled(
            await self.bot.tr(ctx.guild.id, "util_roleinfo_title", role=role.name))
        embed.add_field(name="Role ID", value=f"`{role.id}`", inline=True)
        embed.add_field(name="Color", value=str(role.color), inline=True)
        embed.add_field(name="Member Count", value=str(members), inline=True)
        embed.add_field(name="Hoisted", value="Yes" if role.hoist else "No", inline=True)
        embed.add_field(name="Mentionable", value="Yes" if role.mentionable else "No", inline=True)
        embed.add_field(name="Created", value=discord_ts(role.created_at, "R"), inline=True)
        perms = [p.replace("_", " ").capitalize() for p, v in role.permissions if v]
        embed.add_field(name="Key Permissions", value=", ".join(perms)[:1000] or "None", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="channelinfo", description="Show info about a channel.")
    @commands.guild_only()
    @module_enabled("utility")
    async def channelinfo(self, ctx: commands.Context,
                          channel: discord.TextChannel | None = None) -> None:
        channel = channel or ctx.channel
        embed = embeds.titled(
            await self.bot.tr(ctx.guild.id, "util_channelinfo_title", channel=channel.name))
        embed.add_field(name="Channel ID", value=f"`{channel.id}`", inline=True)
        embed.add_field(name="Type", value=str(channel.type).capitalize(), inline=True)
        embed.add_field(name="Created", value=discord_ts(channel.created_at, "R"), inline=True)
        embed.add_field(name="Topic", value=channel.topic or "—", inline=False)
        embed.add_field(name="Slowmode", value=f"{channel.slowmode_delay}s", inline=True)
        embed.add_field(name="NSFW", value="Yes" if channel.is_nsfw() else "No", inline=True)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="botinfo", description="Bot system statistics and uptime.")
    @module_enabled("utility")
    async def botinfo(self, ctx: commands.Context) -> None:
        from datetime import timedelta
        uptime = format_duration(timedelta(seconds=time.time() - self.start_time))
        embed = embeds.titled(await self.bot.tr(ctx.guild.id if ctx.guild else None, "util_botinfo_title"))
        embed.add_field(name="Servers", value=f"{len(self.bot.guilds):,}", inline=True)
        embed.add_field(name="Total Users", value=f"{sum(g.member_count or 0 for g in self.bot.guilds):,}", inline=True)
        embed.add_field(name="Uptime", value=uptime, inline=True)
        embed.add_field(name="Library", value=f"discord.py {discord.__version__}", inline=True)
        embed.add_field(name="Gateway Latency", value=f"{self.bot.latency * 1000:.0f}ms", inline=True)
        if self.bot.user:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="remind", description="Set a reminder (e.g. 10m, 1h30m, 2d).")
    @module_enabled("utility")
    async def remind(self, ctx: commands.Context, duration: str, *, message: str = "Reminder!") -> None:
        delta = parse_duration(duration)
        if delta is None:
            return await ctx.send(embed=embeds.error("Invalid duration. Examples: `10m`, `1h`, `2d`."))
        remind_at = utcnow() + delta
        from bot.utils.timeutil import iso
        await db.execute(
            "INSERT INTO reminders (guild_id, channel_id, user_id, message, remind_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (ctx.guild.id if ctx.guild else None, ctx.channel.id, ctx.author.id,
             message[:1900], iso(remind_at)),
        )
        await ctx.send(embed=embeds.success(await self.bot.tr(
            ctx.guild.id if ctx.guild else None, "util_reminder_set",
            duration=format_duration(delta))))

    @commands.hybrid_command(name="poll", description="Create an interactive poll.")
    @module_enabled("utility")
    async def poll(self, ctx: commands.Context, *, question: str) -> None:
        embed = embeds.titled(
            await self.bot.tr(ctx.guild.id if ctx.guild else None, "util_poll_title", question=question),
            f"Poll started by {ctx.author.mention}\n\nReact below with ✅ or ❌ to vote!")
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

    @commands.hybrid_command(name="snipe", description="Show the last deleted message in this channel.")
    @commands.guild_only()
    @module_enabled("utility")
    async def snipe(self, ctx: commands.Context) -> None:
        row = await db.fetchone(
            "SELECT * FROM snipes WHERE guild_id = ? AND channel_id = ? AND kind = 'delete'",
            (ctx.guild.id, ctx.channel.id),
        )
        if not row:
            return await ctx.send(embed=embeds.info(
                await self.bot.tr(ctx.guild.id, "util_snipe_empty")))
        embed = embeds.titled(f"🎯 Snipe — {row['author']}", row["content"])
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="editsnipe", description="Show the last edited message in this channel.")
    @commands.guild_only()
    @module_enabled("utility")
    async def editsnipe(self, ctx: commands.Context) -> None:
        row = await db.fetchone(
            "SELECT * FROM snipes WHERE guild_id = ? AND channel_id = ? AND kind = 'edit'",
            (ctx.guild.id, ctx.channel.id),
        )
        if not row:
            return await ctx.send(embed=embeds.info(
                await self.bot.tr(ctx.guild.id, "util_snipe_empty")))
        embed = embeds.titled(f"✏️ Edit Snipe — {row['author']}", f"**Original Message:**\n{row['content']}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="clearsnipe", description="Clear snipe history for this channel.")
    @commands.guild_only()
    @module_enabled("utility")
    @is_mod()
    async def clearsnipe(self, ctx: commands.Context) -> None:
        await db.execute(
            "DELETE FROM snipes WHERE guild_id = ? AND channel_id = ?",
            (ctx.guild.id, ctx.channel.id)
        )
        await ctx.send(embed=embeds.success("Snipe history cleared for this channel."))

    @commands.hybrid_command(name="afk", description="Set yourself AFK with an optional reason.")
    @commands.guild_only()
    @module_enabled("utility")
    async def afk(self, ctx: commands.Context, *, reason: str = "AFK") -> None:
        await db.execute(
            "INSERT INTO afk (guild_id, user_id, reason) VALUES (?, ?, ?)"
            " ON CONFLICT(guild_id, user_id) DO UPDATE SET reason = ?, since = datetime('now')",
            (ctx.guild.id, ctx.author.id, reason[:200], reason[:200]),
        )
        await ctx.send(embed=embeds.success(await self.bot.tr(
            ctx.guild.id, "util_afk_set", user=str(ctx.author), reason=reason)))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        if not await db.module_enabled(message.guild.id, "utility"):
            return

        # Clear own AFK
        row = await db.fetchone(
            "SELECT * FROM afk WHERE guild_id = ? AND user_id = ?",
            (message.guild.id, message.author.id),
        )
        if row:
            await db.execute(
                "DELETE FROM afk WHERE guild_id = ? AND user_id = ?",
                (message.guild.id, message.author.id),
            )
            try:
                from bot.utils.timeutil import from_iso
                dur = format_duration(utcnow() - from_iso(row["since"]))
            except Exception:
                dur = "a while"
            await message.channel.send(embed=embeds.info(await self.bot.tr(
                message.guild.id, "util_afk_back", user=message.author.mention, duration=dur)))

        # Notify about mentioned AFK users
        for mentioned in message.mentions:
            if mentioned.bot or mentioned.id == message.author.id:
                continue
            mrow = await db.fetchone(
                "SELECT * FROM afk WHERE guild_id = ? AND user_id = ?",
                (message.guild.id, mentioned.id),
            )
            if mrow:
                try:
                    from bot.utils.timeutil import from_iso
                    since = discord_ts(from_iso(mrow["since"]), "R")
                except Exception:
                    since = "recently"
                await message.channel.send(embed=embeds.info(await self.bot.tr(
                    message.guild.id, "util_afk_mention", user=str(mentioned),
                    reason=mrow["reason"], since=since)))

    @commands.hybrid_command(name="suggest", description="Submit a server suggestion.")
    @commands.guild_only()
    @module_enabled("utility")
    async def suggest(self, ctx: commands.Context, *, suggestion: str) -> None:
        cur = await db.execute(
            "INSERT INTO suggestions (guild_id, user_id, content) VALUES (?, ?, ?)",
            (ctx.guild.id, ctx.author.id, suggestion[:1900]),
        )
        sid = cur.lastrowid or 0
        channel_id = await db.get_guild_setting(ctx.guild.id, "suggestion_channel")
        if channel_id:
            channel = ctx.guild.get_channel(int(channel_id))
            if isinstance(channel, discord.TextChannel):
                embed = embeds.titled(f"💡 Suggestion #{sid}",
                                      f"{suggestion}\n\n**Submitted by:** {ctx.author.mention}")
                msg = await channel.send(embed=embed)
                await msg.add_reaction("⬆️")
                await msg.add_reaction("⬇️")
                await db.execute("UPDATE suggestions SET message_id = ? WHERE id = ?",
                                 (msg.id, sid))
        await ctx.send(embed=embeds.success(await self.bot.tr(
            ctx.guild.id, "util_suggest_sent", id=sid)))


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(Utility(bot))
