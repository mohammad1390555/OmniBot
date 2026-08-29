# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Birthdays: record member birthdays and post automated daily birthday celebrations."""

from __future__ import annotations

import calendar
from datetime import datetime

import discord
from discord.ext import commands, tasks

from bot.core.bot import OmniBot
from bot.core.database import db
from bot.utils import embeds
from bot.utils.checks import is_admin, module_enabled
from bot.utils.timeutil import utcnow


class Birthdays(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.celebrate_task.start()

    def cog_unload(self) -> None:
        self.celebrate_task.cancel()

    @tasks.loop(hours=1)
    async def celebrate_task(self) -> None:
        if db._db is None:
            return
        now = utcnow()
        cur_month = now.month
        cur_day = now.day
        date_key = f"{now.year}-{cur_month:02d}-{cur_day:02d}"

        rows = await db.fetchall(
            "SELECT b.guild_id, b.user_id, b.last_celebrated FROM birthdays b"
            " WHERE b.month = ? AND b.day = ?",
            (cur_month, cur_day),
        )

        for r in rows:
            if r["last_celebrated"] == date_key:
                continue

            guild = self.bot.get_guild(r["guild_id"])
            if not guild:
                continue
            if not await db.module_enabled(guild.id, "birthdays"):
                continue

            channel_id = await db.get_guild_setting(guild.id, "birthday_channel")
            if not channel_id:
                continue
            channel = guild.get_channel(int(channel_id))
            if not isinstance(channel, discord.TextChannel):
                continue

            member = guild.get_member(r["user_id"])
            if not member:
                continue

            embed = embeds.titled(
                f"🎂 Happy Birthday, {member.display_name}! 🎉",
                f"Wishing a very special day to {member.mention}! 🎈✨\n"
                f"May all your wishes and goals come true!"
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            try:
                await channel.send(content=f"{member.mention}", embed=embed)
                await db.execute(
                    "UPDATE birthdays SET last_celebrated = ? WHERE guild_id = ? AND user_id = ?",
                    (date_key, guild.id, member.id)
                )
            except discord.HTTPException:
                pass

    @celebrate_task.before_loop
    async def before_celebrate(self) -> None:
        try:
            await self.bot.wait_until_ready()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    @commands.hybrid_command(name="setbirthday", description="Set your birthday (day and month).")
    @commands.guild_only()
    @module_enabled("birthdays")
    async def setbirthday(self, ctx: commands.Context, day: int, month: int) -> None:
        if not (1 <= month <= 12):
            return await ctx.send(embed=embeds.error("Month must be between 1 and 12."))
        max_days = calendar.monthrange(2024, month)[1]
        if not (1 <= day <= max_days):
            return await ctx.send(embed=embeds.error(f"Invalid day for month {month}. Must be between 1 and {max_days}."))

        await db.execute(
            "INSERT INTO birthdays (guild_id, user_id, month, day) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(guild_id, user_id) DO UPDATE SET month = ?, day = ?",
            (ctx.guild.id, ctx.author.id, month, day, month, day)
        )
        month_name = calendar.month_name[month]
        await ctx.send(embed=embeds.success(f"🎂 Your birthday has been set to **{month_name} {day}**!"))

    @commands.hybrid_command(name="birthday", description="View your (or a member's) saved birthday.")
    @commands.guild_only()
    @module_enabled("birthdays")
    async def birthday(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        member = member or ctx.author
        row = await db.fetchone(
            "SELECT month, day FROM birthdays WHERE guild_id = ? AND user_id = ?",
            (ctx.guild.id, member.id)
        )
        if not row:
            return await ctx.send(embed=embeds.info(f"{member.display_name} has not set their birthday yet."))

        month_name = calendar.month_name[row["month"]]
        await ctx.send(embed=embeds.info(f"🎂 **{member.display_name}**'s birthday is on **{month_name} {row['day']}**."))

    @commands.hybrid_command(name="birthdays", description="List upcoming birthdays in the server.")
    @commands.guild_only()
    @module_enabled("birthdays")
    async def birthdays(self, ctx: commands.Context) -> None:
        rows = await db.fetchall(
            "SELECT user_id, month, day FROM birthdays WHERE guild_id = ? ORDER BY month ASC, day ASC",
            (ctx.guild.id,)
        )
        if not rows:
            return await ctx.send(embed=embeds.info("No birthdays registered in this server yet."))

        lines = []
        for r in rows:
            m = ctx.guild.get_member(r["user_id"])
            name = m.display_name if m else f"User {r['user_id']}"
            m_name = calendar.month_abbr[r["month"]]
            lines.append(f"• **{name}** — `{m_name} {r['day']}`")

        embed = embeds.titled(f"🎂 Birthdays — {ctx.guild.name}", "\n".join(lines[:30]))
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="birthdaychannel", description="Set the channel for birthday announcements (Admin).")
    @commands.guild_only()
    @module_enabled("birthdays")
    @is_admin()
    async def birthdaychannel(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        await db.set_guild_setting(ctx.guild.id, "birthday_channel", channel.id)
        await ctx.send(embed=embeds.success(f"Birthday announcements will be sent to {channel.mention}."))


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(Birthdays(bot))
