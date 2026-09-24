# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Leveling: XP on messages, rank, leaderboard, level-up announcements."""

from __future__ import annotations

import math
import random
from datetime import timedelta

import discord
from discord.ext import commands

from bot.core.bot import OmniBot
from bot.core.config import config
from bot.core.database import db
from bot.utils import embeds
from bot.utils.checks import module_enabled
from bot.utils.timeutil import from_iso, utcnow


class Leveling(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot

    def _xp_for_level(self, level: int) -> int:
        base = int(config.get("leveling.xp_base", 100))
        exp = float(config.get("leveling.xp_exponent", 1.5))
        return int(base * (level ** exp))

    async def _get(self, guild_id: int, user_id: int) -> dict:
        row = await db.fetchone(
            "SELECT * FROM leveling WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        if row is None:
            return {"xp": 0, "level": 0, "messages": 0, "last_xp": None}
        return {"xp": row["xp"], "level": row["level"],
                "messages": row["messages"], "last_xp": row["last_xp"]}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        if not await db.module_enabled(message.guild.id, "leveling"):
            return

        data = await self._get(message.guild.id, message.author.id)

        # cooldown check
        cooldown = int(config.get("leveling.xp_cooldown", 60))
        if data["last_xp"]:
            try:
                if (utcnow() - from_iso(data["last_xp"])).total_seconds() < cooldown:
                    return
            except Exception:
                logger.exception("Unhandled exception")

        gain = random.randint(int(config.get("leveling.xp_min", 15)),
                              int(config.get("leveling.xp_max", 25)))
        new_xp = data["xp"] + gain
        new_level = data["level"]
        while new_xp >= self._xp_for_level(new_level + 1):
            new_level += 1

        from bot.utils.timeutil import iso
        await db.execute(
            "INSERT INTO leveling (guild_id, user_id, xp, level, messages, last_xp)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(guild_id, user_id) DO UPDATE SET"
            " xp = ?, level = ?, messages = messages + 1, last_xp = ?",
            (message.guild.id, message.author.id, new_xp, new_level,
             data["messages"] + 1, iso(utcnow()), new_xp, new_level, iso(utcnow())),
        )

        if new_level > data["level"] and bool(config.get("leveling.announce_level_up", True)):
            await message.channel.send(embed=embeds.success(await self.bot.tr(
                message.guild.id, "level_up", user=message.author.mention, level=new_level)))

    # ------------------------------------------------------------------
    @commands.hybrid_command(name="rank", description="Show your (or someone's) rank card.")
    @commands.guild_only()
    @module_enabled("leveling")
    async def rank(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        member = member or ctx.author
        data = await self._get(ctx.guild.id, member.id)
        level = data["level"]
        cur_xp = data["xp"]
        need = self._xp_for_level(level + 1)
        prev = self._xp_for_level(level)
        progress = max(0, min(100, int((cur_xp - prev) / max(1, need - prev) * 100)))

        # server rank
        rows = await db.fetchall(
            "SELECT user_id FROM leveling WHERE guild_id = ? ORDER BY xp DESC",
            (ctx.guild.id,),
        )
        rank_pos = next((i + 1 for i, r in enumerate(rows) if r["user_id"] == member.id), 0)

        bar_len = 15
        filled = round(bar_len * progress / 100)
        bar = "█" * filled + "░" * (bar_len - filled)

        embed = embeds.titled(
            await self.bot.tr(ctx.guild.id, "rank_title", user=str(member)))
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Level", value=str(level), inline=True)
        embed.add_field(name="Rank", value=f"#{rank_pos}", inline=True)
        embed.add_field(name="Messages", value=str(data["messages"]), inline=True)
        embed.add_field(name="XP", value=f"{cur_xp:,} / {need:,}", inline=False)
        embed.add_field(name="Progress", value=f"`{bar}` {progress}%", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="xpleaderboard", description="Top 10 by XP.")
    @commands.guild_only()
    @module_enabled("leveling")
    async def xpleaderboard(self, ctx: commands.Context) -> None:
        rows = await db.fetchall(
            "SELECT user_id, xp, level FROM leveling WHERE guild_id = ? ORDER BY xp DESC LIMIT 10",
            (ctx.guild.id,),
        )
        if not rows:
            return await ctx.send(embed=embeds.info(
                await self.bot.tr(ctx.guild.id, "leaderboard_empty")))
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, r in enumerate(rows):
            medal = medals[i] if i < 3 else f"**{i + 1}.**"
            lines.append(f"{medal} <@{r['user_id']}> — level {r['level']} ({r['xp']:,} XP)")
        await ctx.send(embed=embeds.titled(
            await self.bot.tr(ctx.guild.id, "leaderboard_title", server=ctx.guild.name),
            "\n".join(lines)))


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(Leveling(bot))
