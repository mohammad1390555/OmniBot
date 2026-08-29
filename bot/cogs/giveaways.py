# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Giveaways: button entry, timed ending, reroll, list."""

from __future__ import annotations

import json
import random

import discord
from discord.ext import commands, tasks

from bot.core.bot import OmniBot
from bot.core.config import config
from bot.core.database import db
from bot.utils import embeds
from bot.utils.checks import is_mod, module_enabled
from bot.utils.timeutil import discord_ts, from_iso, iso, parse_duration, utcnow


class GiveawayButton(discord.ui.View):
    def __init__(self, bot: OmniBot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Enter", style=discord.ButtonStyle.success,
                       emoji="🎉", custom_id="omnibot:giveaway_enter")
    async def enter(self, interaction: discord.Interaction, _: discord.ui.Button):
        message_id = interaction.message.id
        row = await db.fetchone(
            "SELECT * FROM giveaways WHERE message_id = ? AND ended = 0", (message_id,))
        if not row:
            return await interaction.response.send_message(
                embed=embeds.error("This giveaway has ended."), ephemeral=True)
        entries = json.loads(row["entries"] or "[]")
        if interaction.user.id in entries:
            entries.remove(interaction.user.id)
            action = "You left the giveaway."
        else:
            entries.append(interaction.user.id)
            action = "🎉 You're in! Good luck!"
        await db.execute("UPDATE giveaways SET entries = ? WHERE id = ?",
                         (json.dumps(entries), row["id"]))
        await interaction.response.send_message(embed=embeds.success(action), ephemeral=True)


class Giveaways(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.check_giveaways.start()

    def cog_unload(self) -> None:
        self.check_giveaways.cancel()

    @tasks.loop(seconds=15)
    async def check_giveaways(self) -> None:
        if db._db is None:
            return
        rows = await db.fetchall("SELECT * FROM giveaways WHERE ended = 0")
        now = utcnow()
        for row in rows:
            try:
                ends_at = from_iso(row["ends_at"])
            except Exception:
                continue
            if ends_at > now:
                continue
            await self._end_giveaway(row)

    @check_giveaways.before_loop
    async def before_check(self) -> None:
        try:
            await self.bot.wait_until_ready()
        except RuntimeError:
            pass

    async def _end_giveaway(self, row) -> None:
        guild = self.bot.get_guild(row["guild_id"])
        if guild is None:
            await db.execute("UPDATE giveaways SET ended = 1 WHERE id = ?", (row["id"],))
            return
        channel = guild.get_channel(row["channel_id"])
        entries = json.loads(row["entries"] or "[]")
        n_winners = min(row["winners"], len(entries))

        if channel:
            if entries:
                winners = random.sample(entries, n_winners)
                mention = " ".join(f"<@{w}>" for w in winners)
                text = await self.bot.tr(guild.id, "giveaway_end", winners=mention)
                await channel.send(f"🎉 **{row['prize']}**\n{text}")
            else:
                await channel.send(f"🎉 **{row['prize']}**\n" + await self.bot.tr(
                    guild.id, "giveaway_no_entries"))
            try:
                msg = await channel.fetch_message(row["message_id"])
                embed = embeds.titled(f"🎉 GIVEAWAY ENDED — {row['prize']}",
                                      f"Winners: {n_winners} | Entries: {len(entries)}")
                await msg.edit(embed=embed, view=None)
            except discord.HTTPException:
                pass
        await db.execute("UPDATE giveaways SET ended = 1 WHERE id = ?", (row["id"],))

    # ------------------------------------------------------------------
    @commands.hybrid_command(name="gstart", description="Start a giveaway.")
    @commands.guild_only()
    @module_enabled("giveaways")
    @is_mod()
    async def gstart(self, ctx: commands.Context, duration: str, winners: int, *, prize: str) -> None:
        delta = parse_duration(duration)
        if delta is None:
            return await ctx.send(embed=embeds.error("Invalid duration. Examples: `10m`, `1h`, `1d`."))
        winners = max(1, min(winners, 20))
        ends_at = utcnow() + delta

        embed = embeds.titled(f"🎉 GIVEAWAY — {prize}",
                              f"React below to enter!\n"
                              f"**Winners:** {winners}\n"
                              f"**Ends:** {discord_ts(ends_at, 'R')}\n"
                              f"Hosted by {ctx.author.mention}")
        view = GiveawayButton(self.bot)
        msg = await ctx.channel.send(embed=embed, view=view)

        await db.execute(
            "INSERT INTO giveaways (guild_id, channel_id, message_id, prize, winners, ends_at, host_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ctx.guild.id, ctx.channel.id, msg.id, prize, winners, iso(ends_at), ctx.author.id),
        )
        await ctx.send(embed=embeds.success(await self.bot.tr(
            ctx.guild.id, "giveaway_started", channel=ctx.channel.mention)), delete_after=5)

    @commands.hybrid_command(name="gend", description="End a giveaway early (by message ID or link).")
    @commands.guild_only()
    @module_enabled("giveaways")
    @is_mod()
    async def gend(self, ctx: commands.Context, message: str) -> None:
        try:
            mid = int(message.split("/")[-1].strip())
        except ValueError:
            return await ctx.send(embed=embeds.error("Invalid message ID or link."))
        row = await db.fetchone(
            "SELECT * FROM giveaways WHERE message_id = ? AND ended = 0", (mid,))
        if not row:
            return await ctx.send(embed=embeds.error("No active giveaway with that message ID."))
        await self._end_giveaway(row)
        await ctx.send(embed=embeds.success("Giveaway ended."))

    @commands.hybrid_command(name="greroll", description="Reroll a finished giveaway's winners (by message ID or link).")
    @commands.guild_only()
    @module_enabled("giveaways")
    @is_mod()
    async def greroll(self, ctx: commands.Context, message: str) -> None:
        try:
            mid = int(message.split("/")[-1].strip())
        except ValueError:
            return await ctx.send(embed=embeds.error("Invalid message ID or link."))
        row = await db.fetchone(
            "SELECT * FROM giveaways WHERE message_id = ?", (mid,))
        if not row:
            return await ctx.send(embed=embeds.error("No giveaway with that message ID."))
        entries = json.loads(row["entries"] or "[]")
        if not entries:
            return await ctx.send(embed=embeds.error(await self.bot.tr(ctx.guild.id, "giveaway_no_entries")))
        n = min(row["winners"], len(entries))
        winners = random.sample(entries, n)
        mention = " ".join(f"<@{w}>" for w in winners)
        await ctx.send(f"🎲 **{row['prize']}**\n" + await self.bot.tr(
            ctx.guild.id, "giveaway_reroll", winners=mention))

    @commands.hybrid_command(name="glist", description="List active giveaways.")
    @commands.guild_only()
    @module_enabled("giveaways")
    @is_mod()
    async def glist(self, ctx: commands.Context) -> None:
        rows = await db.fetchall(
            "SELECT * FROM giveaways WHERE guild_id = ? AND ended = 0", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=embeds.info("No active giveaways."))
        lines = []
        for r in rows:
            try:
                ends = discord_ts(from_iso(r["ends_at"]), "R")
            except Exception:
                ends = "?"
            lines.append(f"🎉 **{r['prize']}** — {ends} — [jump](https://discord.com/channels/{r['guild_id']}/{r['channel_id']}/{r['message_id']})")
        await ctx.send(embed=embeds.titled("🎉 Active Giveaways", "\n".join(lines)))


async def setup(bot: OmniBot) -> None:
    bot.add_view(GiveawayButton(bot))
    await bot.add_cog(Giveaways(bot))
