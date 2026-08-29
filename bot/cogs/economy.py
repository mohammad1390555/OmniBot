# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Economy: balance, bank, deposit, withdraw, daily, weekly, work, pay, rob, coinflip, slots, blackjack, shop, inventory."""

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
from bot.utils.timeutil import format_duration, from_iso, iso, utcnow


class BlackjackView(discord.ui.View):
    def __init__(self, cog: Economy, ctx: commands.Context, bet: int, player_cards: list[int], dealer_cards: list[int]) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.bet = bet
        self.player_cards = player_cards
        self.dealer_cards = dealer_cards

    def _calc_score(self, cards: list[int]) -> int:
        score = sum(min(c, 10) for c in cards)
        # handle aces (11 if possible)
        aces = cards.count(1)
        while aces > 0 and score + 10 <= 21:
            score += 10
            aces -= 1
        return score

    def _card_str(self, cards: list[int], hide_second: bool = False) -> str:
        names = {1: "A", 11: "J", 12: "Q", 13: "K"}
        if hide_second and len(cards) >= 2:
            first = names.get(cards[0], str(cards[0]))
            return f"`{first}` + `?`"
        return " + ".join(f"`{names.get(c, str(c))}`" for c in cards)

    async def on_timeout(self) -> None:
        try:
            await self.cog._add(self.ctx.guild.id, self.ctx.author.id, -self.bet)
        except Exception:
            pass
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary, emoji="🃏")
    async def hit(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.defer()
        self.player_cards.append(random.randint(1, 13))
        p_score = self._calc_score(self.player_cards)
        if p_score > 21:
            self.stop()
            await self.cog._add(self.ctx.guild.id, self.ctx.author.id, -self.bet)
            embed = embeds.error(
                f"💥 **Bust!** You went over 21.\n"
                f"**Your cards:** {self._card_str(self.player_cards)} ({p_score})\n"
                f"**Dealer cards:** {self._card_str(self.dealer_cards)} ({self._calc_score(self.dealer_cards)})\n"
                f"Lost {self.cog._fmt(self.bet)}."
            )
            return await interaction.response.edit_message(embed=embed, view=None)

        embed = embeds.titled(
            "🃏 Blackjack",
            f"**Your Hand:** {self._card_str(self.player_cards)} (Score: `{p_score}`)\n"
            f"**Dealer Hand:** {self._card_str(self.dealer_cards, hide_second=True)}\n"
            f"Bet: {self.cog._fmt(self.bet)}"
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary, emoji="🛑")
    async def stand(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.defer()
        self.stop()

        # Dealer draws to at least 17
        while self._calc_score(self.dealer_cards) < 17:
            self.dealer_cards.append(random.randint(1, 13))

        p_score = self._calc_score(self.player_cards)
        d_score = self._calc_score(self.dealer_cards)

        p_cards = self._card_str(self.player_cards)
        d_cards = self._card_str(self.dealer_cards)

        if d_score > 21 or p_score > d_score:
            winnings = self.bet
            await self.cog._add(self.ctx.guild.id, self.ctx.author.id, winnings)
            embed = embeds.success(
                f"🎉 **You Win!**\n"
                f"**Your Hand:** {p_cards} (`{p_score}`)\n"
                f"**Dealer Hand:** {d_cards} (`{d_score}`)\n"
                f"Won {self.cog._fmt(winnings)}!"
            )
        elif p_score == d_score:
            embed = embeds.info(
                f"🤝 **Push (Tie)!** Your bet was returned.\n"
                f"**Your Hand:** {p_cards} (`{p_score}`)\n"
                f"**Dealer Hand:** {d_cards} (`{d_score}`)"
            )
        else:
            await self.cog._add(self.ctx.guild.id, self.ctx.author.id, -self.bet)
            embed = embeds.error(
                f"🤖 **Dealer Wins!**\n"
                f"**Your Hand:** {p_cards} (`{p_score}`)\n"
                f"**Dealer Hand:** {d_cards} (`{d_score}`)\n"
                f"Lost {self.cog._fmt(self.bet)}."
            )
        await interaction.response.edit_message(embed=embed, view=None)


class Economy(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    def _cfg(self, key: str, default=None):
        return config.get(f"economy.{key}", default)

    async def _balance(self, guild_id: int, user_id: int) -> tuple[int, int]:
        """Returns (wallet, bank)"""
        row = await db.fetchone(
            "SELECT balance, bank FROM economy WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        if not row:
            return int(self._cfg("starting_balance", 100)), 0
        return row["balance"], (row["bank"] or 0)

    async def _add(self, guild_id: int, user_id: int, amount: int, in_bank: bool = False) -> int:
        wallet, bank = await self._balance(guild_id, user_id)
        if in_bank:
            bank += amount
        else:
            wallet += amount
        await db.execute(
            "INSERT INTO economy (guild_id, user_id, balance, bank) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(guild_id, user_id) DO UPDATE SET balance = ?, bank = ?",
            (guild_id, user_id, wallet, bank, wallet, bank),
        )
        return bank if in_bank else wallet

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
            return None
        diff = (utcnow() - last).total_seconds()
        if diff < cooldown:
            from datetime import timedelta
            return format_duration(timedelta(seconds=cooldown - diff))
        return None

    async def _stamp(self, guild_id: int, user_id: int, field: str) -> None:
        now_str = iso(utcnow())
        await db.execute(
            f"INSERT INTO economy (guild_id, user_id, {field}) VALUES (?, ?, ?)"
            f" ON CONFLICT(guild_id, user_id) DO UPDATE SET {field} = ?",
            (guild_id, user_id, now_str, now_str),
        )

    def _fmt(self, amount: int) -> str:
        return f"{self._cfg('currency_emoji', '🪙')} **{amount:,} {self._cfg('currency_name', 'coins')}**"

    # ------------------------------------------------------------------
    @commands.hybrid_command(name="balance", aliases=["bal"], description="Check your (or someone's) wallet and bank balance.")
    @commands.guild_only()
    @module_enabled("economy")
    async def balance(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        member = member or ctx.author
        wallet, bank = await self._balance(ctx.guild.id, member.id)
        total = wallet + bank
        embed = embeds.titled(f"🪙 Balance — {member.display_name}")
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="👛 Wallet", value=self._fmt(wallet), inline=True)
        embed.add_field(name="🏦 Bank", value=self._fmt(bank), inline=True)
        embed.add_field(name="💰 Net Worth", value=self._fmt(total), inline=True)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="deposit", aliases=["dep"], description="Deposit coins into your bank.")
    @commands.guild_only()
    @module_enabled("economy")
    async def deposit(self, ctx: commands.Context, amount: str) -> None:
        wallet, _ = await self._balance(ctx.guild.id, ctx.author.id)
        if amount.lower() == "all":
            deposit_amount = wallet
        else:
            try:
                deposit_amount = int(amount)
            except ValueError:
                return await ctx.send(embed=embeds.error("Please provide a valid number or `all`."))

        if deposit_amount <= 0:
            return await ctx.send(embed=embeds.error("Deposit amount must be greater than 0."))
        if wallet < deposit_amount:
            return await ctx.send(embed=embeds.error("You do not have enough coins in your wallet."))

        await self._add(ctx.guild.id, ctx.author.id, -deposit_amount, in_bank=False)
        await self._add(ctx.guild.id, ctx.author.id, deposit_amount, in_bank=True)
        await ctx.send(embed=embeds.success(f"Deposited {self._fmt(deposit_amount)} into your bank!"))

    @commands.hybrid_command(name="withdraw", aliases=["with"], description="Withdraw coins from your bank.")
    @commands.guild_only()
    @module_enabled("economy")
    async def withdraw(self, ctx: commands.Context, amount: str) -> None:
        _, bank = await self._balance(ctx.guild.id, ctx.author.id)
        if amount.lower() == "all":
            with_amount = bank
        else:
            try:
                with_amount = int(amount)
            except ValueError:
                return await ctx.send(embed=embeds.error("Please provide a valid number or `all`."))

        if with_amount <= 0:
            return await ctx.send(embed=embeds.error("Withdraw amount must be greater than 0."))
        if bank < with_amount:
            return await ctx.send(embed=embeds.error("You do not have enough coins in your bank."))

        await self._add(ctx.guild.id, ctx.author.id, -with_amount, in_bank=True)
        await self._add(ctx.guild.id, ctx.author.id, with_amount, in_bank=False)
        await ctx.send(embed=embeds.success(f"Withdrew {self._fmt(with_amount)} from your bank into your wallet!"))

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
            "You worked as a software engineer.", "You drove an Uber taxi.", "You fixed server issues.",
            "You delivered pizzas across town.", "You mined crypto blocks.", "You designed a UI kit.",
            "You streamed on Twitch.", "You tutored students in math."
        ]
        await self._add(ctx.guild.id, ctx.author.id, amount)
        await self._stamp(ctx.guild.id, ctx.author.id, "last_work")
        await ctx.send(embed=embeds.success(await self.bot.tr(
            ctx.guild.id, "eco_work", flavor=random.choice(flavors),
            amount=f"{amount:,}", currency=self._cfg("currency_name", "coins"))))

    @commands.hybrid_command(name="rob", description="Attempt to steal coins from another user's wallet.")
    @commands.guild_only()
    @module_enabled("economy")
    async def rob(self, ctx: commands.Context, member: discord.Member) -> None:
        if member.id == ctx.author.id or member.bot:
            return await ctx.send(embed=embeds.error("You cannot rob yourself or bots."))

        cd = await self._check_cooldown(ctx.guild.id, ctx.author.id, "last_rob", 7200)
        if cd:
            return await ctx.send(embed=embeds.error(f"You must lay low! Try robbing again in {cd}."))

        author_bal, _ = await self._balance(ctx.guild.id, ctx.author.id)
        if author_bal < 100:
            return await ctx.send(embed=embeds.error("You need at least 100 coins in your wallet to risk a robbery."))

        target_bal, _ = await self._balance(ctx.guild.id, member.id)
        if target_bal < 100:
            return await ctx.send(embed=embeds.error(f"{member.display_name} doesn't have enough coins in their wallet worth stealing!"))

        await self._stamp(ctx.guild.id, ctx.author.id, "last_rob")

        # 45% chance of success
        if random.random() < 0.45:
            stolen = random.randint(50, min(target_bal, int(target_bal * 0.4)))
            await self._add(ctx.guild.id, member.id, -stolen)
            await self._add(ctx.guild.id, ctx.author.id, stolen)
            await ctx.send(embed=embeds.success(
                f"🥷 **Success!** You sneaked up on {member.mention} and stole {self._fmt(stolen)}!"))
        else:
            fine = min(author_bal, random.randint(50, 150))
            await self._add(ctx.guild.id, ctx.author.id, -fine)
            await ctx.send(embed=embeds.error(
                f"🚨 **Busted!** You got caught trying to rob {member.mention} and had to pay a fine of {self._fmt(fine)}!"))

    @commands.hybrid_command(name="pay", description="Pay coins to another member.")
    @commands.guild_only()
    @module_enabled("economy")
    async def pay(self, ctx: commands.Context, member: discord.Member, amount: int) -> None:
        if amount <= 0 or member.id == ctx.author.id or member.bot:
            return await ctx.send(embed=embeds.error("Invalid payment."))
        wallet, _ = await self._balance(ctx.guild.id, ctx.author.id)
        if wallet < amount:
            return await ctx.send(embed=embeds.error(await self.bot.tr(
                ctx.guild.id, "eco_insufficient", currency=self._cfg("currency_name", "coins"))))
        await self._add(ctx.guild.id, ctx.author.id, -amount)
        await self._add(ctx.guild.id, member.id, amount)
        await ctx.send(embed=embeds.success(await self.bot.tr(
            ctx.guild.id, "eco_pay", emoji=self._cfg("currency_emoji", "🪙"),
            sender=ctx.author.mention, amount=f"{amount:,}",
            receiver=member.mention, currency=self._cfg("currency_name", "coins"))))

    @commands.hybrid_command(name="coinflip", aliases=["cf"], description="Flip a coin, double or nothing.")
    @commands.guild_only()
    @module_enabled("economy")
    async def coinflip(self, ctx: commands.Context, amount: int, guess: str = "heads") -> None:
        if not (int(self._cfg("min_bet", 10)) <= amount <= int(self._cfg("max_bet", 10000))):
            return await ctx.send(embed=embeds.error(
                f"Bet must be between {self._cfg('min_bet', 10)} and {self._cfg('max_bet', 10000)}."))
        wallet, _ = await self._balance(ctx.guild.id, ctx.author.id)
        if wallet < amount:
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
        wallet, _ = await self._balance(ctx.guild.id, ctx.author.id)
        if wallet < amount:
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

    @commands.hybrid_command(name="blackjack", aliases=["bj"], description="Play Blackjack 21 against the bot.")
    @commands.guild_only()
    @module_enabled("economy")
    async def blackjack(self, ctx: commands.Context, bet: int) -> None:
        if not (int(self._cfg("min_bet", 10)) <= bet <= int(self._cfg("max_bet", 10000))):
            return await ctx.send(embed=embeds.error(
                f"Bet must be between {self._cfg('min_bet', 10)} and {self._cfg('max_bet', 10000)}."))
        wallet, _ = await self._balance(ctx.guild.id, ctx.author.id)
        if wallet < bet:
            return await ctx.send(embed=embeds.error(await self.bot.tr(
                ctx.guild.id, "eco_insufficient", currency=self._cfg("currency_name", "coins"))))

        p_cards = [random.randint(1, 13), random.randint(1, 13)]
        d_cards = [random.randint(1, 13), random.randint(1, 13)]

        view = BlackjackView(self, ctx, bet, p_cards, d_cards)
        p_score = view._calc_score(p_cards)

        # Check natural 21 blackjack
        if p_score == 21:
            winnings = int(bet * 1.5)
            await self._add(ctx.guild.id, ctx.author.id, winnings)
            return await ctx.send(embed=embeds.success(
                f"🎉 **BLACKJACK!** You hit 21 immediately!\n"
                f"**Your Hand:** {view._card_str(p_cards)} (21)\n"
                f"Won {self._fmt(winnings)}!"
            ))

        embed = embeds.titled(
            "🃏 Blackjack",
            f"**Your Hand:** {view._card_str(p_cards)} (Score: `{p_score}`)\n"
            f"**Dealer Hand:** {view._card_str(d_cards, hide_second=True)}\n"
            f"Bet: {self._fmt(bet)}"
        )
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="leaderboard", aliases=["lb"], description="Top 10 richest members.")
    @commands.guild_only()
    @module_enabled("economy")
    async def leaderboard(self, ctx: commands.Context) -> None:
        rows = await db.fetchall(
            "SELECT user_id, (balance + IFNULL(bank, 0)) AS total FROM economy WHERE guild_id = ? ORDER BY total DESC LIMIT 10",
            (ctx.guild.id,),
        )
        if not rows:
            return await ctx.send(embed=embeds.info("No economy data yet."))
        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, r in enumerate(rows):
            medal = medals[i] if i < 3 else f"**{i + 1}.**"
            lines.append(f"{medal} <@{r['user_id']}> — {r['total']:,} {self._cfg('currency_name', 'coins')}")
        await ctx.send(embed=embeds.titled(
            f"🏆 Economy Leaderboard — {ctx.guild.name}", "\n".join(lines)))

    # -- Shop & Inventory -----------------------------------------------
    @commands.hybrid_group(name="shop", description="Server shop.", invoke_without_command=True)
    @commands.guild_only()
    @module_enabled("economy")
    async def shop(self, ctx: commands.Context) -> None:
        rows = await db.fetchall("SELECT * FROM shop_items WHERE guild_id = ? ORDER BY id", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=embeds.info("The server shop is currently empty."))
        lines = []
        for r in rows:
            role_tag = f" | Role: <@&{r['role_id']}>" if r["role_id"] else ""
            desc = f" — *{r['description']}*" if r["description"] else ""
            lines.append(f"**#{r['id']} {r['name']}** — {self._fmt(r['price'])}{role_tag}{desc}")
        embed = embeds.titled(f"🛒 Server Shop — {ctx.guild.name}", "\n".join(lines))
        embed.set_footer(text="Use /buy <item_id> to purchase an item.")
        await ctx.send(embed=embed)

    @shop.command(name="add", description="Add an item or role to the shop (Admin).")
    @is_admin()
    async def shop_add(self, ctx: commands.Context, name: str, price: int,
                       role: discord.Role | None = None, *, description: str | None = None) -> None:
        if price <= 0:
            return await ctx.send(embed=embeds.error("Price must be greater than 0."))
        role_id = role.id if role else None
        cur = await db.execute(
            "INSERT INTO shop_items (guild_id, name, description, price, role_id) VALUES (?, ?, ?, ?, ?)",
            (ctx.guild.id, name, description, price, role_id)
        )
        await ctx.send(embed=embeds.success(f"Item **{name}** added to the shop (ID: #{cur.lastrowid})."))

    @shop.command(name="remove", description="Remove an item from the shop (Admin).")
    @is_admin()
    async def shop_remove(self, ctx: commands.Context, item_id: int) -> None:
        row = await db.fetchone("SELECT * FROM shop_items WHERE id = ? AND guild_id = ?", (item_id, ctx.guild.id))
        if not row:
            return await ctx.send(embed=embeds.error(f"Shop item #{item_id} not found."))
        await db.execute("DELETE FROM shop_items WHERE id = ?", (item_id,))
        await ctx.send(embed=embeds.success(f"Shop item **{row['name']}** (#{item_id}) removed."))

    @commands.hybrid_command(name="buy", description="Buy an item from the server shop.")
    @commands.guild_only()
    @module_enabled("economy")
    async def buy(self, ctx: commands.Context, item_id: int) -> None:
        item = await db.fetchone("SELECT * FROM shop_items WHERE id = ? AND guild_id = ?", (item_id, ctx.guild.id))
        if not item:
            return await ctx.send(embed=embeds.error(f"Shop item #{item_id} does not exist."))

        price = item["price"]
        wallet, _ = await self._balance(ctx.guild.id, ctx.author.id)
        if wallet < price:
            return await ctx.send(embed=embeds.error(
                f"You need {self._fmt(price)} in your wallet to purchase this."))

        # Deduct price
        await self._add(ctx.guild.id, ctx.author.id, -price)

        # Grant role if applicable
        role_given = ""
        if item["role_id"]:
            role = ctx.guild.get_role(item["role_id"])
            if role:
                try:
                    await ctx.author.add_roles(role, reason="Shop purchase")
                    role_given = f" You received the {role.mention} role!"
                except discord.HTTPException:
                    role_given = " (Failed to assign role due to role hierarchy)."

        # Record in inventory
        await db.execute(
            "INSERT INTO user_inventory (guild_id, user_id, item_id, quantity) VALUES (?, ?, ?, 1)"
            " ON CONFLICT(guild_id, user_id, item_id) DO UPDATE SET quantity = quantity + 1",
            (ctx.guild.id, ctx.author.id, item["id"]),
        )
        await ctx.send(embed=embeds.success(f"🛍️ You bought **{item['name']}** for {self._fmt(price)}!{role_given}"))

    @commands.hybrid_command(name="inventory", aliases=["inv"], description="View your purchased items.")
    @commands.guild_only()
    @module_enabled("economy")
    async def inventory(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        member = member or ctx.author
        rows = await db.fetchall(
            "SELECT i.name, ui.quantity FROM user_inventory ui"
            " JOIN shop_items i ON ui.item_id = i.id"
            " WHERE ui.guild_id = ? AND ui.user_id = ?",
            (ctx.guild.id, member.id),
        )
        if not rows:
            return await ctx.send(embed=embeds.info(f"{member.display_name} has no items in their inventory."))
        lines = [f"📦 **{r['name']}** × {r['quantity']}" for r in rows]
        embed = embeds.titled(f"🎒 Inventory — {member.display_name}", "\n".join(lines))
        await ctx.send(embed=embed)

    # -- Admin tools ---------------------------------------------------
    @commands.hybrid_command(name="addmoney", description="Add coins to a member's wallet (Admin).")
    @commands.guild_only()
    @module_enabled("economy")
    @is_admin()
    async def addmoney(self, ctx: commands.Context, member: discord.Member, amount: int) -> None:
        new = await self._add(ctx.guild.id, member.id, amount)
        await ctx.send(embed=embeds.success(f"Added {self._fmt(amount)} to {member.mention}. New wallet: {self._fmt(new)}"))

    @commands.hybrid_command(name="removemoney", description="Remove coins from a member's wallet (Admin).")
    @commands.guild_only()
    @module_enabled("economy")
    @is_admin()
    async def removemoney(self, ctx: commands.Context, member: discord.Member, amount: int) -> None:
        new = await self._add(ctx.guild.id, member.id, -amount)
        await ctx.send(embed=embeds.success(f"Removed {self._fmt(amount)} from {member.mention}. New wallet: {self._fmt(new)}"))


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(Economy(bot))
