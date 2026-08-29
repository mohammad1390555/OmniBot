# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Leveling: XP on messages, Voice XP, rank cards, XP leaderboards, and automated Level Role rewards."""

from __future__ import annotations

import math
import random
import time
from datetime import timedelta

import discord
from discord.ext import commands

from bot.core.bot import OmniBot
from bot.core.config import config
from bot.core.database import db
from bot.utils import embeds
from bot.utils.checks import is_admin, module_enabled
from bot.utils.timeutil import from_iso, iso, utcnow


class Leveling(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot
        # (guild_id, user_id) -> join timestamp
        self._voice_tracking: dict[tuple[int, int], float] = {}

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

    async def _check_level_rewards(self, member: discord.Member, new_level: int) -> list[discord.Role]:
        """Check and award roles up to new_level."""
        rows = await db.fetchall(
            "SELECT role_id, level FROM level_roles WHERE guild_id = ? AND level <= ? ORDER BY level ASC",
            (member.guild.id, new_level),
        )
        awarded = []
        for r in rows:
            role = member.guild.get_role(r["role_id"])
            if role and role not in member.roles:
                try:
                    await member.add_roles(role, reason=f"Level {r['level']} Reward")
                    awarded.append(role)
                except discord.HTTPException:
                    pass
        return awarded

    # -- Message XP Listener -------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        if not await db.module_enabled(message.guild.id, "leveling"):
            return

        data = await self._get(message.guild.id, message.author.id)

        # Anti-spam cooldown check
        cooldown = int(config.get("leveling.xp_cooldown", 60))
        if data["last_xp"]:
            try:
                if (utcnow() - from_iso(data["last_xp"])).total_seconds() < cooldown:
                    return
            except Exception:
                pass

        gain = random.randint(int(config.get("leveling.xp_min", 15)),
                              int(config.get("leveling.xp_max", 25)))
        new_xp = data["xp"] + gain
        new_level = data["level"]
        while new_xp >= self._xp_for_level(new_level + 1):
            new_level += 1

        await db.execute(
            "INSERT INTO leveling (guild_id, user_id, xp, level, messages, last_xp)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(guild_id, user_id) DO UPDATE SET"
            " xp = ?, level = ?, messages = messages + 1, last_xp = ?",
            (message.guild.id, message.author.id, new_xp, new_level,
             data["messages"] + 1, iso(utcnow()), new_xp, new_level, iso(utcnow())),
        )

        if new_level > data["level"]:
            if isinstance(message.author, discord.Member):
                awarded_roles = await self._check_level_rewards(message.author, new_level)
                role_msg = f" 🎖️ You unlocked: {', '.join(r.mention for r in awarded_roles)}" if awarded_roles else ""
            else:
                role_msg = ""

            if bool(config.get("leveling.announce_level_up", True)):
                embed = embeds.success(
                    f"🎉 GG {message.author.mention}! You reached **Level {new_level}**!{role_msg}"
                )
                try:
                    await message.channel.send(embed=embed)
                except discord.HTTPException:
                    pass

    # -- Voice XP Listener ---------------------------------------------
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if member.bot or member.guild is None:
            return
        if not await db.module_enabled(member.guild.id, "leveling"):
            return

        key = (member.guild.id, member.id)
        now = time.time()

        # Check if user joined an active voice channel
        is_active = (
            after.channel is not None
            and not after.self_deaf
            and not after.deaf
            and len([m for m in after.channel.members if not m.bot]) > 1
        )

        if is_active and key not in self._voice_tracking:
            self._voice_tracking[key] = now
        elif (not is_active or after.channel is None) and key in self._voice_tracking:
            joined_at = self._voice_tracking.pop(key, None)
            if joined_at:
                minutes = int((now - joined_at) / 60)
                if minutes >= 1:
                    xp_gain = minutes * random.randint(5, 10)
                    data = await self._get(member.guild.id, member.id)
                    new_xp = data["xp"] + xp_gain
                    new_level = data["level"]
                    while new_xp >= self._xp_for_level(new_level + 1):
                        new_level += 1

                    await db.execute(
                        "INSERT INTO leveling (guild_id, user_id, xp, level, messages, last_xp)"
                        " VALUES (?, ?, ?, ?, ?, ?)"
                        " ON CONFLICT(guild_id, user_id) DO UPDATE SET xp = ?, level = ?",
                        (member.guild.id, member.id, new_xp, new_level, data["messages"], iso(utcnow()),
                         new_xp, new_level),
                    )
                    if new_level > data["level"]:
                        await self._check_level_rewards(member, new_level)

    # ------------------------------------------------------------------
    @commands.hybrid_command(name="rank", description="Show your (or someone's) rank card and level progress.")
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

        # Guild leaderboard position
        rows = await db.fetchall(
            "SELECT user_id FROM leveling WHERE guild_id = ? ORDER BY xp DESC",
            (ctx.guild.id,),
        )
        rank_pos = next((i + 1 for i, r in enumerate(rows) if r["user_id"] == member.id), len(rows) + 1)

        bar_len = 16
        filled = round(bar_len * progress / 100)
        bar = "▰" * filled + "▱" * (bar_len - filled)

        embed = embeds.titled(f"📈 Level & Rank — {member.display_name}")
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="🏆 Rank", value=f"`#{rank_pos}`", inline=True)
        embed.add_field(name="⭐ Level", value=f"`{level}`", inline=True)
        embed.add_field(name="💬 Messages", value=f"`{data['messages']:,}`", inline=True)
        embed.add_field(name="✨ Total XP", value=f"`{cur_xp:,}` / `{need:,}`", inline=True)
        embed.add_field(name="📊 Progress", value=f"`{bar}` **{progress}%**", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="xpleaderboard", aliases=["xplb"], description="Top 10 members with highest XP.")
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
            lines.append(f"{medal} <@{r['user_id']}> — Level **{r['level']}** (`{r['xp']:,}` XP)")
        await ctx.send(embed=embeds.titled(
            f"🏆 Level Leaderboard — {ctx.guild.name}", "\n".join(lines)))

    # -- Level Role Rewards --------------------------------------------
    @commands.hybrid_group(name="levelroles", description="Manage level role rewards.", invoke_without_command=True)
    @commands.guild_only()
    @module_enabled("leveling")
    @is_admin()
    async def levelroles(self, ctx: commands.Context) -> None:
        rows = await db.fetchall(
            "SELECT level, role_id FROM level_roles WHERE guild_id = ? ORDER BY level ASC",
            (ctx.guild.id,),
        )
        if not rows:
            return await ctx.send(embed=embeds.info("No level role rewards configured."))
        lines = [f"• Level **{r['level']}** ➔ <@&{r['role_id']}>" for r in rows]
        embed = embeds.titled("🎖️ Level Role Rewards", "\n".join(lines))
        await ctx.send(embed=embed)

    @levelroles.command(name="add", description="Add a role reward for reaching a level.")
    @is_admin()
    async def levelroles_add(self, ctx: commands.Context, level: int, role: discord.Role) -> None:
        if level <= 0:
            return await ctx.send(embed=embeds.error("Level must be greater than 0."))
        await db.execute(
            "INSERT INTO level_roles (guild_id, level, role_id) VALUES (?, ?, ?)"
            " ON CONFLICT(guild_id, level) DO UPDATE SET role_id = ?",
            (ctx.guild.id, level, role.id, role.id),
        )
        await ctx.send(embed=embeds.success(f"Role {role.mention} will be awarded when reaching Level **{level}**!"))

    @levelroles.command(name="remove", description="Remove a level role reward.")
    @is_admin()
    async def levelroles_remove(self, ctx: commands.Context, level: int) -> None:
        await db.execute("DELETE FROM level_roles WHERE guild_id = ? AND level = ?", (ctx.guild.id, level))
        await ctx.send(embed=embeds.success(f"Removed role reward for Level **{level}**."))


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(Leveling(bot))
