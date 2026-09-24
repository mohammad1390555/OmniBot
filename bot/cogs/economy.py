# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Economy: balance, daily, weekly, work, pay, coinflip, slots, blackjack."""

from __future__ import annotations

import random
from datetime import datetime, timezone

import discord
from discord.ext import commands

from bot.core.bot import OmniBot
from bot.core.config import config
from bot.core.database import db
from bot.utils import embeds
from bot.utils.checks import is_admin, module_enabled
from bot.utils.timeutil import format_duration, from_iso, utcnow
import logging
log = logging.getLogger(__name__)


class Economy(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    def _cfg(self, key: str, default=None):
        return config.get(f"economy.{key}", default)

    async def _balance(self, guild_id: int, user_id: int) -> int:
        row = await db.fetchone(
            "SELECT balance FROM economy WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        return row["balance"] if row else int(self._cfg("starting_balance", 100))

    async def _add(self, guild_id: int, user_id: int, amount: int) -> int:
        balance = await self._balance(guild_id, user_id)
        balance += amount
        await db.execute(
            "INSERT INTO economy (guild_id, user_id, balance) VALUES (?, ?, ?)"
            " ON CONFLICT(guild_id, user_id) DO UPDATE SET balance = ?",
            (guild_id, user_id, balance, balance),
        )
        return balance

    async def _check_cooldown(self, guild_id: int, user_id: int, field: str,
                              cooldown: int) -> str | None:
        row = await db.fetchone(
            f"SELECT {field} AS last FROM economy WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        if not row or not row["last"]:
            return None
        try:
            last = from_iso(row["last"])
        except Exception:
            log.exception("Failed to parse last activity timestamp")
            return None
        diff = (utcnow() - last).total_seconds()
        if diff < cooldown:
            from datetime import timedelta
            return format_duration(timedelta(seconds=cooldown - diff))
        return None

    async def _stamp(self, guild_id: int, user_id: int, field: str) -> None:
        from bot.utils.timeutil import iso
        await db.execute(
            "INSERT INTO economy (guild_id, user_id) VALUES (?, ?)"
            f" ON CONFLICT(guild_id, user_id) DO UPDATE SET {field} = ?",
            (guild_id, user_id, iso(utcnow())),
        )

    def _fmt(self, amount: int) -> str:
        return f"{self._cfg('currency_emoji', '🪙')} **{amount:,} {self._cfg('currency_name', 'coins')}**"

    # ------------------------------------------------------------------
    @commands.hybrid_command(name="balance", description="Check your (or someone's) balance.")
    @commands.guild_only()
    @module_enabled("economy")
    async def balance(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        member = member or ctx.author
        bal = await self._balance(ctx.guild.id, member.id)
        await ctx.send(embed=embeds.info(await self.bot.tr(
            ctx.guild.id, "eco_balance", emoji=self._cfg("currency_emoji", "🪙"),
            user=str(member), amount=f"{bal:,}", currency=self._cfg("currency_name", "coins"))))

    @commands.hybrid_command(name="daily", description="Claim your daily reward.")
    @commands.guild_only()
    @module_enabled("economy")
    async def daily(self, ctx: commands.Context) -> None:
        cd = await self._check_cooldown(ctx.guild.id, ctx.author.id, "last_daily",
                                        int(self._cfg("daily_cooldown", 86400)))
        if cd:
            return await ctx.send(embed=embeds.error(await self.bot.tr(
                ctx.guild.id, "eco_cooldown", duration=cd)))
        amount = int(self._cfg("daily_amount", 250))
        await self._add(ctx.guild.id, ctx.author.id, amount)
        await self._stamp(ctx.guild.id, ctx.author.id, "last_daily")
        await ctx.send(embed=embeds.success(await self.bot.tr(
            ctx.guild.id, "eco_daily", emoji=self._cfg("currency_emoji", "🪙"),
            amount=f"{amount:,}", currency=self._cfg("currency_name", "coins"))))

    @commands.hybrid_command(name="weekly", description="Claim your weekly reward.")
    @commands.guild_only()
    @module_enabled("economy")
    async def weekly(self, ctx: commands.Context) -> None:
        cd = await self._check_cooldown(ctx.guild.id, ctx.author.id, "last_weekly",
                                        int(self._cfg("weekly_cooldown", 604800)))
        if cd:
            return await ctx.send(embed=embeds.error(await self.bot.tr(
                ctx.guild.id, "eco_cooldown", duration=cd)))
        amount = int(self._cfg("weekly_amount", 1500))
        await self._add(ctx.guild.id, ctx.author.id, amount)
        await self._stamp(ctx.guild.id, ctx.author.id, "last_weekly")
        await ctx.send(embed=embeds.success(await self.bot.tr(
            ctx.guild.id, "eco_weekly", emoji=self._cfg("currency_emoji", "🪙"),
            amount=f"{amount:,}", currency=self._cfg("currency_name", "coins"))))

    @commands.hybrid_command(name="work", description="Work a random job for coins.")
    @commands.guild_only()
    @module_enabled("economy")
    async def work(self, ctx: commands.Context) -> None:
        cd = await self._check_cooldown(ctx.guild.id, ctx.author.id, "last_work",
                                        int(self._cfg("work_cooldown", 3600)))
        if cd:
            return await ctx.send(embed=embeds.error(await self.bot.tr(
                ctx.guild.id, "eco_cooldown", duration=cd)))
        amount = random.randint(int(self._cfg("work_min", 100)), int(self._cfg("work_max", 500)))
        flavors = [
            "You worked as a developer.", "You drove a taxi.", "You fixed a server.",
            "You delivered pizzas.", "You mined some crypto.", "You designed a logo.",
        ]
        await self._add(ctx.guild.id, ctx.author.id, amount)
        await self._stamp(ctx.guild.id, ctx.author.id, "last_work")
        await ctx.send(embed=embeds.success(await self.bot.tr(
            ctx.guild.id, "eco_work", flavor=random.choice(flavors),
            amount=f"{amount:,}", currency=self._cfg("currency_name", "coins"))))

    @commands.hybrid_command(name="pay", description="Pay coins to another member.")
    @commands.guild_only()
    @module_enabled("economy")
    async def pay(self, ctx: commands.Context, member: discord.Member, amount: int) -> None:
        if amount <= 0 or member.id == ctx.author.id or member.bot:
            return await ctx.send(embed=embeds.error("Invalid payment."))
        bal = await self._balance(ctx.guild.id, ctx.author.id)
        if bal < amount:
            return await ctx.send(embed=embeds.error(await self.bot.tr(
                ctx.guild.id, "eco_insufficient", currency=self._cfg("currency_name", "coins"))))
        await self._add(ctx.guild.id, ctx.author.id, -amount)
        await self._add(ctx.guild.id, member.id, amount)
        await ctx.send(embed=embeds.success(await self.bot.tr(
            ctx.guild.id, "eco_pay", emoji=self._cfg("currency_emoji", "🪙"),
            sender=ctx.author.mention, amount=f"{amount:,}",
            receiver=member.mention, currency=self._cfg("currency_name", "coins"))))

    @commands.hybrid_command(name="coinflip", description="Flip a coin, double or nothing.")
    @commands.guild_only()
    @module_enabled("economy")
    async def coinflip(self, ctx: commands.Context, amount: int, guess: str = "heads") -> None:
        if not (int(self._cfg("min_bet", 10)) <= amount <= int(self._cfg("max_bet", 10000))):
            return await ctx.send(embed=embeds.error(
                f"Bet must be between {self._cfg('min_bet', 10)} and {self._cfg('max_bet', 10000)}."))
        bal = await self._balance(ctx.guild.id, ctx.author.id)
        if bal < amount:
            return await ctx.send(embed=embeds.error(await self.bot.tr(
                ctx.guild.id, "eco_insufficient", currency=self._cfg("currency_name", "coins"))))
        result = random.choice(["heads", "tails"])
        won = result == guess.lower()
        await self._add(ctx.guild.id, ctx.author.id, amount if won else -amount)
        key = "eco_gamble_win" if won else "eco_gamble_lose"
        await ctx.send(embed=embeds.info(
            f"🪙 The coin landed on **{result}**!\n" + await self.bot.tr(
                ctx.guild.id, key, amount=f"{amount:,}", currency=self._cfg("currency_name", "coins"))))

    @commands.hybrid_command(name="slots", description="Play the slot machine.")
    @commands.guild_only()
    @module_enabled("economy")
    async def slots(self, ctx: commands.Context, amount: int) -> None:
        if not (int(self._cfg("min_bet", 10)) <= amount <= int(self._cfg("max_bet", 10000))):
            return await ctx.send(embed=embeds.error("Invalid bet amount."))
        bal = await self._balance(ctx.guild.id, ctx.author.id)
        if bal < amount:
            return await ctx.send(embed=embeds.error(await self.bot.tr(
                ctx.guild.id, "eco_insufficient", currency=self._cfg("currency_name", "coins"))))
        symbols = ["🍒", "🍋", "🍇", "💎", "7️⃣"]
        reels = [random.choice(symbols) for _ in range(3)]
        line = " | ".join(reels)
        if len(set(reels)) == 1:
            winnings = amount * 5
            await self._add(ctx.guild.id, ctx.author.id, winnings - amount)
            text = f"🎰 {line}\n" + await self.bot.tr(ctx.guild.id, "eco_gamble_win",
                                                       amount=f"{winnings:,}", currency=self._cfg("currency_name", "coins")) + " JACKPOT!"
        elif len(set(reels)) == 2:
            await self._add(ctx.guild.id, ctx.author.id, 0)
            text = f"🎰 {line}\n😐 So close! Your bet was returned."
        else:
            await self._add(ctx.guild.id, ctx.author.id, -amount)
            text = f"🎰 {line}\n" + await self.bot.tr(ctx.guild.id, "eco_gamble_lose",
                                                      amount=f"{amount:,}", currency=self._cfg("currency_name", "coins"))
        await ctx.send(embed=embeds.info(text))

    @commands.hybrid_command(name="leaderboard", aliases=["lb"], description="Top 10 richest members.")
    @commands.guild_only()
    @module_enabled("economy")
    async def leaderboard(self, ctx: commands.Context) -> None:
        rows = await db.fetchall(
            "SELECT user_id, balance FROM economy WHERE guild_id = ? ORDER BY balance DESC LIMIT 10",
            (ctx.guild.id,),
        )
        if not rows:
            return await ctx.send(embed=embeds.info("No economy data yet."))
        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, r in enumerate(rows):
            medal = medals[i] if i < 3 else f"**{i + 1}.**"
            lines.append(f"{medal} <@{r['user_id']}> — {r['balance']:,} {self._cfg('currency_name', 'coins')}")
        await ctx.send(embed=embeds.titled(
            f"🏆 Economy Leaderboard — {ctx.guild.name}", "\n".join(lines)))

    # -- admin ---------------------------------------------------------
    @commands.hybrid_command(name="addmoney", description="Add coins to a member (admin).")
    @commands.guild_only()
    @module_enabled("economy")
    @is_admin()
    async def addmoney(self, ctx: commands.Context, member: discord.Member, amount: int) -> None:
        new = await self._add(ctx.guild.id, member.id, amount)
        await ctx.send(embed=embeds.success(f"Added {amount:,} to {member}. New balance: {new:,}"))

    @commands.hybrid_command(name="removemoney", description="Remove coins from a member (admin).")
    @commands.guild_only()
    @module_enabled("economy")
    @is_admin()
    async def removemoney(self, ctx: commands.Context, member: discord.Member, amount: int) -> None:
        new = await self._add(ctx.guild.id, member.id, -amount)
        await ctx.send(embed=embeds.success(f"Removed {amount:,} from {member}. New balance: {new:,}"))


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(Economy(bot))
