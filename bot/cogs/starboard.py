# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Starboard: pins memorable messages that reach star reaction thresholds."""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.core.bot import OmniBot
from bot.core.database import db
from bot.utils import embeds
from bot.utils.checks import is_mod, module_enabled


class Starboard(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot

    async def _get_starboard_channel(self, guild_id: int) -> discord.TextChannel | None:
        cid = await db.get_guild_setting(guild_id, "starboard_channel")
        if not cid:
            return None
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return None
        ch = guild.get_channel(int(cid))
        return ch if isinstance(ch, discord.TextChannel) else None

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if str(payload.emoji) != "⭐" or payload.guild_id is None:
            return
        if not await db.module_enabled(payload.guild_id, "starboard"):
            return

        star_channel = await self._get_starboard_channel(payload.guild_id)
        if star_channel is None or payload.channel_id == star_channel.id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        orig_channel = guild.get_channel(payload.channel_id)
        if not isinstance(orig_channel, discord.TextChannel):
            return

        try:
            message = await orig_channel.fetch_message(payload.message_id)
        except discord.HTTPException:
            return

        # Find reaction count
        reaction = discord.utils.get(message.reactions, emoji="⭐")
        count = reaction.count if reaction else 0
        threshold = int(await db.get_guild_setting(payload.guild_id, "starboard_threshold", 3))

        if count < threshold:
            return

        row = await db.fetchone(
            "SELECT * FROM starboard WHERE guild_id = ? AND message_id = ?",
            (payload.guild_id, message.id),
        )

        embed = embeds.titled(
            f"⭐ {count} | #{orig_channel.name}",
            f"{message.content}\n\n[**Jump to Message**]({message.jump_url})"
        )
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        embed.color = 0xFFAC33

        # Attach image if present
        if message.attachments:
            first = message.attachments[0]
            if first.content_type and first.content_type.startswith("image/"):
                embed.set_image(url=first.url)

        if row and row["posted_id"]:
            # Update existing starboard message
            try:
                posted_msg = await star_channel.fetch_message(row["posted_id"])
                await posted_msg.edit(content=f"⭐ **{count}** {orig_channel.mention}", embed=embed)
                await db.execute(
                    "UPDATE starboard SET stars = ? WHERE guild_id = ? AND message_id = ?",
                    (count, payload.guild_id, message.id)
                )
            except discord.HTTPException:
                pass
        else:
            # Post new starboard message
            try:
                posted_msg = await star_channel.send(content=f"⭐ **{count}** {orig_channel.mention}", embed=embed)
                await db.execute(
                    "INSERT INTO starboard (guild_id, message_id, channel_id, stars, posted_id) VALUES (?, ?, ?, ?, ?)"
                    " ON CONFLICT(guild_id, message_id) DO UPDATE SET stars = ?, posted_id = ?",
                    (payload.guild_id, message.id, orig_channel.id, count, posted_msg.id, count, posted_msg.id)
                )
            except discord.HTTPException:
                pass

    # ------------------------------------------------------------------
    @commands.hybrid_group(name="starboard", description="Configure Starboard.", invoke_without_command=True)
    @commands.guild_only()
    @module_enabled("starboard")
    @is_mod()
    async def starboard(self, ctx: commands.Context) -> None:
        cid = await db.get_guild_setting(ctx.guild.id, "starboard_channel")
        thresh = await db.get_guild_setting(ctx.guild.id, "starboard_threshold", 3)
        channel_str = f"<#{cid}>" if cid else "Not set"
        embed = embeds.titled(
            "⭐ Starboard Settings",
            f"**Channel:** {channel_str}\n"
            f"**Threshold:** `{thresh}` stars\n\n"
            f"Use `/starboard channel #channel` to configure."
        )
        await ctx.send(embed=embed)

    @starboard.command(name="channel", description="Set the starboard channel.")
    @is_mod()
    async def starboard_channel(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        await db.set_guild_setting(ctx.guild.id, "starboard_channel", channel.id)
        await ctx.send(embed=embeds.success(f"Starboard messages will be posted in {channel.mention}."))

    @starboard.command(name="threshold", description="Set required number of stars to pin a message.")
    @is_mod()
    async def starboard_threshold(self, ctx: commands.Context, stars: int) -> None:
        if stars < 1:
            return await ctx.send(embed=embeds.error("Threshold must be at least 1."))
        await db.set_guild_setting(ctx.guild.id, "starboard_threshold", stars)
        await ctx.send(embed=embeds.success(f"Starboard threshold set to **{stars}** stars."))


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(Starboard(bot))
