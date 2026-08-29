# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Scheduler: fires reminders and temp actions (unmute/unban) from the DB.

Everything is database-backed, so timers survive restarts — on startup
any overdue rows are processed immediately.
"""

from __future__ import annotations

import json

import discord
from discord.ext import commands, tasks

from bot.core.bot import OmniBot
from bot.core.database import db
from bot.utils import embeds
from bot.utils.timeutil import from_iso, utcnow


class Scheduler(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.tick.start()

    def cog_unload(self) -> None:
        self.tick.cancel()

    @tasks.loop(seconds=30)
    async def tick(self) -> None:
        if db._db is None:
            return
        now = utcnow()
        await self._process_reminders(now)
        await self._process_temp_actions(now)

    @tick.before_loop
    async def before_tick(self) -> None:
        try:
            await self.bot.wait_until_ready()
        except RuntimeError:
            pass

    async def _process_reminders(self, now) -> None:
        rows = await db.fetchall("SELECT * FROM reminders WHERE done = 0")
        for row in rows:
            try:
                remind_at = from_iso(row["remind_at"])
            except Exception:
                await db.execute("UPDATE reminders SET done = 1 WHERE id = ?", (row["id"],))
                continue
            if remind_at > now:
                continue
            channel = self.bot.get_channel(row["channel_id"])
            if channel:
                try:
                    guild_id = channel.guild.id if channel.guild else None
                    text = await self.bot.tr(guild_id, "util_reminder_due",
                                             user=f"<@{row['user_id']}>")
                    await channel.send(f"{text}\n> {row['message']}")
                except discord.HTTPException:
                    pass
            await db.execute("UPDATE reminders SET done = 1 WHERE id = ?", (row["id"],))

    async def _process_temp_actions(self, now) -> None:
        rows = await db.fetchall("SELECT * FROM temp_actions WHERE done = 0")
        for row in rows:
            try:
                expires = from_iso(row["expires_at"])
            except Exception:
                await db.execute("UPDATE temp_actions SET done = 1 WHERE id = ?", (row["id"],))
                continue
            if expires > now:
                continue

            guild = self.bot.get_guild(row["guild_id"])
            if guild:
                try:
                    if row["action"] == "unmute":
                        member = guild.get_member(row["user_id"])
                        if member and member.is_timed_out():
                            await member.timeout(None, reason="temp mute expired")
                    elif row["action"] == "unban":
                        user = await self.bot.fetch_user(row["user_id"])
                        await guild.unban(user, reason="temp ban expired")
                except discord.HTTPException:
                    pass
            await db.execute("UPDATE temp_actions SET done = 1 WHERE id = ?", (row["id"],))


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(Scheduler(bot))
