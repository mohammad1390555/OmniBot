# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Welcome & leave messages + autorole assignment."""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.core.bot import OmniBot
from bot.core.config import config
from bot.core.database import db
from bot.utils import embeds
from bot.utils.checks import is_mod, module_enabled


def _render(template: str, member: discord.Member) -> str:
    return (template
            .replace("{user.mention}", member.mention)
            .replace("{user}", str(member))
            .replace("{server}", member.guild.name)
            .replace("{membercount}", str(member.guild.member_count or 0)))


class Welcome(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not await db.module_enabled(member.guild.id, "welcome"):
            return

        # autoroles
        rows = await db.fetchall(
            "SELECT role_id FROM autoroles WHERE guild_id = ?", (member.guild.id,))
        for r in rows:
            role = member.guild.get_role(r["role_id"])
            if role:
                try:
                    await member.add_roles(role, reason="autorole")
                except discord.HTTPException:
                    pass

        channel_id = await db.get_guild_setting(member.guild.id, "welcome_channel")
        if not channel_id:
            return
        channel = member.guild.get_channel(int(channel_id))
        if not channel:
            return
        template = await db.get_guild_setting(
            member.guild.id, "welcome_message",
            config.get("welcome.default_welcome_message"))
        embed = embeds.titled(await self.bot.tr(member.guild.id, "welcome_title"),
                              _render(template, member))
        embed.set_thumbnail(url=member.display_avatar.url)
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if not await db.module_enabled(member.guild.id, "welcome"):
            return
        channel_id = await db.get_guild_setting(member.guild.id, "leave_channel")
        if not channel_id:
            return
        channel = member.guild.get_channel(int(channel_id))
        if not channel:
            return
        template = await db.get_guild_setting(
            member.guild.id, "leave_message",
            config.get("welcome.default_leave_message"))
        try:
            await channel.send(embed=embeds.info(_render(template, member)))
        except discord.HTTPException:
            pass

    # ------------------------------------------------------------------
    @commands.hybrid_command(name="setwelcome", description="Set welcome channel and message.")
    @commands.guild_only()
    @module_enabled("welcome")
    @is_mod()
    async def setwelcome(self, ctx: commands.Context, channel: discord.TextChannel,
                         *, message: str | None = None) -> None:
        await db.set_guild_setting(ctx.guild.id, "welcome_channel", channel.id)
        if message:
            await db.set_guild_setting(ctx.guild.id, "welcome_message", message)
        await ctx.send(embed=embeds.success(f"Welcome messages → {channel.mention}"))

    @commands.hybrid_command(name="setleave", description="Set leave channel and message.")
    @commands.guild_only()
    @module_enabled("welcome")
    @is_mod()
    async def setleave(self, ctx: commands.Context, channel: discord.TextChannel,
                       *, message: str | None = None) -> None:
        await db.set_guild_setting(ctx.guild.id, "leave_channel", channel.id)
        if message:
            await db.set_guild_setting(ctx.guild.id, "leave_message", message)
        await ctx.send(embed=embeds.success(f"Leave messages → {channel.mention}"))

    @commands.hybrid_command(name="autorole", description="Add/remove an auto-assigned role.")
    @commands.guild_only()
    @module_enabled("welcome")
    @is_mod()
    async def autorole(self, ctx: commands.Context, role: discord.Role, remove: bool = False) -> None:
        if remove:
            await db.execute("DELETE FROM autoroles WHERE guild_id = ? AND role_id = ?",
                             (ctx.guild.id, role.id))
            await ctx.send(embed=embeds.success(f"Removed autorole {role.mention}."))
        else:
            await db.execute(
                "INSERT OR IGNORE INTO autoroles (guild_id, role_id) VALUES (?, ?)",
                (ctx.guild.id, role.id))
            await ctx.send(embed=embeds.success(f"Autorole added: {role.mention}."))


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(Welcome(bot))
