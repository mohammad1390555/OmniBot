# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Owner-only tools: reload cogs, sync, shutdown, guild list."""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.core.bot import OmniBot
from bot.utils import embeds


class Owner(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    @commands.command(name="reload", description="Reload cogs (owner only).")
    async def reload(self, ctx: commands.Context, cog: str = "all") -> None:
        reloaded = []
        for ext in list(self.bot.extensions):
            if cog != "all" and not ext.endswith(cog):
                continue
            try:
                await self.bot.reload_extension(ext)
                reloaded.append(ext.split(".")[-1])
            except Exception as e:
                await ctx.send(embed=embeds.error(f"Failed to reload {ext}: {e}"))
        await ctx.send(embed=embeds.success(
            await self.bot.tr(ctx.guild.id if ctx.guild else None,
                              "owner_reloaded", cogs=", ".join(reloaded) or "none")))

    @commands.command(name="sync", description="Sync slash commands (owner only).")
    async def sync(self, ctx: commands.Context) -> None:
        await self.bot.tree.sync()
        await ctx.send(embed=embeds.success("Slash commands synced."))

    @commands.command(name="guilds", description="List servers the bot is in (owner only).")
    async def guilds(self, ctx: commands.Context) -> None:
        lines = [f"**{g.name}** — {g.member_count} members (id: {g.id})"
                 for g in self.bot.guilds[:25]]
        await ctx.send(embed=embeds.titled(f"🌍 {len(self.bot.guilds)} Servers",
                                           "\n".join(lines) or "None"))

    @commands.command(name="shutdown", description="Shut down the bot (owner only).")
    async def shutdown(self, ctx: commands.Context) -> None:
        await ctx.send(embed=embeds.info(
            await self.bot.tr(ctx.guild.id if ctx.guild else None, "owner_shutdown")))
        await self.bot.close()


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(Owner(bot))
