# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Fun: 8ball, rps, ship, rate, dice, coin, trivia, choose, meme, counting game, tags."""

from __future__ import annotations

import random

import aiohttp
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

TRIVIA_QUESTIONS = [
    {"q": "Which planet is known as the Red Planet?", "options": ["Venus", "Mars", "Jupiter", "Saturn"], "ans": "Mars"},
    {"q": "What is the capital city of France?", "options": ["Rome", "Madrid", "Paris", "Berlin"], "ans": "Paris"},
    {"q": "How many bits are in one byte?", "options": ["4", "8", "16", "32"], "ans": "8"},
    {"q": "What is the chemical symbol for Gold?", "options": ["Ag", "Au", "Fe", "Pb"], "ans": "Au"},
    {"q": "Which programming language was created by Guido van Rossum?", "options": ["Java", "C++", "Python", "Ruby"], "ans": "Python"},
    {"q": "How many continents are there on Earth?", "options": ["5", "6", "7", "8"], "ans": "7"},
    {"q": "What year did the Titanic sink?", "options": ["1905", "1912", "1920", "1898"], "ans": "1912"},
    {"q": "Which ocean is the largest on Earth?", "options": ["Atlantic", "Indian", "Arctic", "Pacific"], "ans": "Pacific"},
]


class TriviaView(discord.ui.View):
    def __init__(self, author_id: int, correct_answer: str, options: list[str]) -> None:
        super().__init__(timeout=30)
        self.author_id = author_id
        self.correct_answer = correct_answer

        for opt in options:
            btn = discord.ui.Button(label=opt, style=discord.ButtonStyle.secondary, custom_id=f"trivia_{opt}")
            btn.callback = self._make_callback(opt)
            self.add_item(btn)

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    def _make_callback(self, chosen: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                return await interaction.response.send_message("This trivia session isn't yours!", ephemeral=True)
            self.stop()
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
                    if item.label == self.correct_answer:
                        item.style = discord.ButtonStyle.success
                    elif item.label == chosen:
                        item.style = discord.ButtonStyle.danger

            if chosen == self.correct_answer:
                embed = embeds.success(f"🎉 **Correct!** The answer is **{self.correct_answer}**!")
            else:
                embed = embeds.error(f"❌ **Wrong!** You chose `{chosen}`. The correct answer was **{self.correct_answer}**.")
            await interaction.response.edit_message(embed=embed, view=self)
        return callback


class Fun(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="8ball", description="Ask the magic 8-ball a question.")
    @module_enabled("fun")
    async def eightball(self, ctx: commands.Context, *, question: str) -> None:
        embed = embeds.titled(await self.bot.tr(ctx.guild.id if ctx.guild else None, "fun_8ball_title"),
                              f"**Question:** {question}\n**Answer:** {random.choice(EIGHT_BALL)}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="rps", description="Play Rock-Paper-Scissors against the bot.")
    @module_enabled("fun")
    async def rps(self, ctx: commands.Context, choice: str) -> None:
        choice = choice.lower()
        if choice not in ("rock", "paper", "scissors"):
            return await ctx.send(embed=embeds.error("Choose: `rock`, `paper`, or `scissors`."))
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
            f"You: {emojis[choice]} **{choice.capitalize()}**\nBot: {emojis[bot_choice]} **{bot_choice.capitalize()}**\n\n{result}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="ship", description="Calculate the love match percentage between two users.")
    @commands.guild_only()
    @module_enabled("fun")
    async def ship(self, ctx: commands.Context, user1: discord.Member,
                   user2: discord.Member | None = None) -> None:
        user2 = user2 or ctx.author
        seed = sorted([user1.id, user2.id])
        rng = random.Random(f"{seed[0]}-{seed[1]}")
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

    @commands.hybrid_command(name="dice", description="Roll dice (e.g. 2d6, 1d20).")
    @module_enabled("fun")
    async def dice(self, ctx: commands.Context, dice_str: str = "1d6") -> None:
        try:
            count, sides = dice_str.lower().split("d")
            count, sides = int(count or 1), int(sides)
        except ValueError:
            return await ctx.send(embed=embeds.error("Format example: `2d6` or `1d20`"))
        count, sides = max(1, min(count, 20)), max(2, min(sides, 1000))
        rolls = [random.randint(1, sides) for _ in range(count)]
        await ctx.send(embed=embeds.info(
            f"🎲 Rolled **{dice_str}**: {', '.join(map(str, rolls))} (Sum: **{sum(rolls)}**)"))

    @commands.hybrid_command(name="coin", description="Flip a coin.")
    @module_enabled("fun")
    async def coin(self, ctx: commands.Context) -> None:
        await ctx.send(embed=embeds.info(f"🪙 **{random.choice(['Heads', 'Tails'])}**!"))

    @commands.hybrid_command(name="choose", description="Randomly choose between comma-separated options.")
    @module_enabled("fun")
    async def choose(self, ctx: commands.Context, *, choices: str) -> None:
        items = [c.strip() for c in choices.split(",") if c.strip()]
        if len(items) < 2:
            return await ctx.send(embed=embeds.error("Please provide at least 2 options separated by commas (e.g. pizza, burger, pasta)."))
        chosen = random.choice(items)
        embed = embeds.titled("🤔 Decision Maker", f"I choose: **{chosen}**!")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="trivia", description="Play a multiple-choice trivia quiz.")
    @module_enabled("fun")
    async def trivia(self, ctx: commands.Context) -> None:
        item = random.choice(TRIVIA_QUESTIONS)
        options = list(item["options"])
        random.shuffle(options)
        view = TriviaView(ctx.author.id, item["ans"], options)
        embed = embeds.titled("🧠 Trivia Quiz", f"**{item['q']}**\n\nChoose an answer below:")
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="meme", description="Get a random safe meme.")
    @module_enabled("fun")
    async def meme(self, ctx: commands.Context) -> None:
        url = "https://meme-api.com/gimme"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        embed = embeds.titled(f"🤣 {data.get('title', 'Meme')}")
                        embed.set_image(url=data.get("url"))
                        embed.set_footer(text=f"r/{data.get('subreddit', 'memes')} • 👍 {data.get('ups', 0)}")
                        return await ctx.send(embed=embed)
        except Exception:
            pass
        await ctx.send(embed=embeds.info("🤣 Why did the programmer quit his job? Because he didn't get arrays!"))

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

    @commands.hybrid_command(name="setcount", description="Set the channel for the counting game.")
    @commands.guild_only()
    @module_enabled("fun")
    @is_mod()
    async def setcount(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        await db.set_guild_setting(ctx.guild.id, "count_channel", channel.id)
        await ctx.send(embed=embeds.success(f"Counting game channel set to {channel.mention}. Next number is **1**!"))

    # -- tags --------------------------------------------------------------
    @commands.hybrid_group(name="tag", description="Custom server tags.", invoke_without_command=True)
    @commands.guild_only()
    @module_enabled("fun")
    async def tag(self, ctx: commands.Context, *, name: str | None = None) -> None:
        if name is None:
            rows = await db.fetchall("SELECT name FROM tags WHERE guild_id = ? ORDER BY name",
                                     (ctx.guild.id,))
            names = ", ".join(f"`{r['name']}`" for r in rows) or "No tags created yet."
            return await ctx.send(embed=embeds.titled(f"🏷️ Server Tags ({len(rows)})", names))
        row = await db.fetchone("SELECT * FROM tags WHERE guild_id = ? AND name = ?",
                                (ctx.guild.id, name.lower()))
        if not row:
            return await ctx.send(embed=embeds.error(f"Tag `{name}` not found."))
        await db.execute("UPDATE tags SET uses = uses + 1 WHERE guild_id = ? AND name = ?",
                         (ctx.guild.id, name.lower()))
        await ctx.send(row["content"])

    @tag.command(name="create", description="Create a new tag.")
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

    @tag.command(name="delete", description="Delete an existing tag.")
    async def tag_delete(self, ctx: commands.Context, *, name: str) -> None:
        name = name.lower()
        row = await db.fetchone("SELECT * FROM tags WHERE guild_id = ? AND name = ?",
                                (ctx.guild.id, name))
        if not row:
            return await ctx.send(embed=embeds.error(f"Tag `{name}` not found."))
        if row["author_id"] != ctx.author.id and not ctx.author.guild_permissions.manage_messages:
            return await ctx.send(embed=embeds.error("You can only delete tags you created."))
        await db.execute("DELETE FROM tags WHERE guild_id = ? AND name = ?", (ctx.guild.id, name))
        await ctx.send(embed=embeds.success(f"Tag `{name}` deleted."))


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(Fun(bot))
