# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Fun: 8ball, rps, ship, rate, dice, coin, counting game, tags."""

from __future__ import annotations

import random

import discord
from discord.ext import commands

from bot.core.bot import OmniBot
from bot.core.database import db
from bot.utils import embeds
from bot.utils.checks import is_mod, module_enabled

EIGHT_BALL = [
    "It is certain.", "Without a doubt.", "Yes, definitely.", "You may rely on it.",
    "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
    "Reply hazy, try again.", "Ask again later.", "Cannot predict now.",
    "Don't count on it.", "My reply is no.", "My sources say no.",
    "Outlook not so good.", "Very doubtful.",
]


class Fun(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="8ball", description="Ask the magic 8-ball.")
    @module_enabled("fun")
    async def eightball(self, ctx: commands.Context, *, question: str) -> None:
        embed = embeds.titled(await self.bot.tr(ctx.guild.id if ctx.guild else None, "fun_8ball_title"),
                              f"**Q:** {question}\n**A:** {random.choice(EIGHT_BALL)}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="rps", description="Rock paper scissors vs the bot.")
    @module_enabled("fun")
    async def rps(self, ctx: commands.Context, choice: str) -> None:
        choice = choice.lower()
        if choice not in ("rock", "paper", "scissors"):
            return await ctx.send(embed=embeds.error("Choose: rock, paper, or scissors."))
        bot_choice = random.choice(["rock", "paper", "scissors"])
        wins = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
        if choice == bot_choice:
            result = "🤝 It's a tie!"
        elif wins[choice] == bot_choice:
            result = "🎉 You win!"
        else:
            result = "🤖 I win!"
        emojis = {"rock": "✊", "paper": "✋", "scissors": "✌️"}
        embed = embeds.titled(
            await self.bot.tr(ctx.guild.id if ctx.guild else None, "fun_rps_title"),
            f"You: {emojis[choice]} {choice}\nMe: {emojis[bot_choice]} {bot_choice}\n\n{result}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="ship", description="Ship two users.")
    @commands.guild_only()
    @module_enabled("fun")
    async def ship(self, ctx: commands.Context, user1: discord.Member,
                   user2: discord.Member | None = None) -> None:
        user2 = user2 or ctx.author
        seed = sorted([user1.id, user2.id])
        rng = random.Random(seed)
        percent = rng.randint(0, 100)
        bar_len = 10
        filled = round(bar_len * percent / 100)
        bar = "❤️" * filled + "🖤" * (bar_len - filled)
        embed = embeds.titled(
            await self.bot.tr(ctx.guild.id, "fun_ship_title"),
            f"{user1.mention} × {user2.mention}\n`{bar}` **{percent}%**")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="rate", description="Rate something out of 10.")
    @module_enabled("fun")
    async def rate(self, ctx: commands.Context, *, thing: str) -> None:
        score = random.randint(0, 10)
        embed = embeds.titled(
            await self.bot.tr(ctx.guild.id if ctx.guild else None, "fun_rate_title"),
            f"I rate **{thing}** a **{score}/10** ⭐")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="dice", description="Roll dice (e.g. 2d6).")
    @module_enabled("fun")
    async def dice(self, ctx: commands.Context, dice_str: str = "1d6") -> None:
        try:
            count, sides = dice_str.lower().split("d")
            count, sides = int(count or 1), int(sides)
        except ValueError:
            return await ctx.send(embed=embeds.error("Format: `2d6`"))
        count, sides = min(count, 20), min(sides, 1000)
        rolls = [random.randint(1, sides) for _ in range(count)]
        await ctx.send(embed=embeds.info(
            f"🎲 Rolled **{dice_str}**: {', '.join(map(str, rolls))} = **{sum(rolls)}**"))

    @commands.hybrid_command(name="coin", description="Flip a coin.")
    @module_enabled("fun")
    async def coin(self, ctx: commands.Context) -> None:
        await ctx.send(embed=embeds.info(f"🪙 **{random.choice(['Heads', 'Tails'])}**!"))

    # -- counting game ---------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        count_channel = await db.get_guild_setting(message.guild.id, "count_channel")
        if not count_channel or message.channel.id != int(count_channel):
            return
        if not await db.module_enabled(message.guild.id, "fun"):
            return

        row = await db.fetchone("SELECT * FROM counters WHERE guild_id = ?", (message.guild.id,))
        current = row["count"] if row else 0
        last_user = row["last_user"] if row else None

        try:
            num = int(message.content.strip())
        except ValueError:
            return

        if num == current + 1 and message.author.id != last_user:
            await db.execute(
                "INSERT INTO counters (guild_id, count, last_user) VALUES (?, ?, ?)"
                " ON CONFLICT(guild_id) DO UPDATE SET count = ?, last_user = ?",
                (message.guild.id, num, message.author.id, num, message.author.id),
            )
            await message.add_reaction("✅")
        else:
            await db.execute(
                "INSERT INTO counters (guild_id, count, last_user) VALUES (?, 0, NULL)"
                " ON CONFLICT(guild_id) DO UPDATE SET count = 0, last_user = NULL",
                (message.guild.id,),
            )
            await message.channel.send(embed=embeds.error(
                await self.bot.tr(message.guild.id, "fun_count_wrong")))

    @commands.hybrid_command(name="setcount", description="Set the counting game channel.")
    @commands.guild_only()
    @module_enabled("fun")
    @is_mod()
    async def setcount(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        await db.set_guild_setting(ctx.guild.id, "count_channel", channel.id)
        await ctx.send(embed=embeds.success(f"Counting game → {channel.mention}. Start at **1**!"))

    # -- tags --------------------------------------------------------------
    @commands.hybrid_group(name="tag", description="Custom text tags.", invoke_without_command=True)
    @commands.guild_only()
    @module_enabled("fun")
    async def tag(self, ctx: commands.Context, *, name: str | None = None) -> None:
        if name is None:
            rows = await db.fetchall("SELECT name FROM tags WHERE guild_id = ? ORDER BY name",
                                     (ctx.guild.id,))
            names = ", ".join(f"`{r['name']}`" for r in rows) or "No tags yet."
            return await ctx.send(embed=embeds.titled("🏷️ Tags", names))
        row = await db.fetchone("SELECT * FROM tags WHERE guild_id = ? AND name = ?",
                                (ctx.guild.id, name.lower()))
        if not row:
            return await ctx.send(embed=embeds.error(f"Tag `{name}` not found."))
        await db.execute("UPDATE tags SET uses = uses + 1 WHERE guild_id = ? AND name = ?",
                         (ctx.guild.id, name.lower()))
        await ctx.send(row["content"])

    @tag.command(name="create", description="Create a tag.")
    async def tag_create(self, ctx: commands.Context, name: str, *, content: str) -> None:
        name = name.lower()
        row = await db.fetchone("SELECT name FROM tags WHERE guild_id = ? AND name = ?",
                                (ctx.guild.id, name))
        if row:
            return await ctx.send(embed=embeds.error(f"Tag `{name}` already exists."))
        await db.execute(
            "INSERT INTO tags (guild_id, name, content, author_id) VALUES (?, ?, ?, ?)",
            (ctx.guild.id, name, content[:1900], ctx.author.id))
        await ctx.send(embed=embeds.success(f"Tag `{name}` created."))

    @tag.command(name="delete", description="Delete a tag.")
    async def tag_delete(self, ctx: commands.Context, *, name: str) -> None:
        name = name.lower()
        row = await db.fetchone("SELECT * FROM tags WHERE guild_id = ? AND name = ?",
                                (ctx.guild.id, name))
        if not row:
            return await ctx.send(embed=embeds.error(f"Tag `{name}` not found."))
        if row["author_id"] != ctx.author.id and not ctx.author.guild_permissions.manage_messages:
            return await ctx.send(embed=embeds.error("You can only delete your own tags."))
        await db.execute("DELETE FROM tags WHERE guild_id = ? AND name = ?", (ctx.guild.id, name))
        await ctx.send(embed=embeds.success(f"Tag `{name}` deleted."))


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(Fun(bot))
