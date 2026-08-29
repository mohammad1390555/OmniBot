# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Logging: audit-log enriched tracking for messages, members, bans, voice, channels, and roles."""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.core.bot import OmniBot
from bot.core.database import db
from bot.utils import embeds
from bot.utils.checks import is_mod, module_enabled


class Logging(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot

    async def _send(self, guild: discord.Guild, key: str, embed: discord.Embed) -> None:
        if not await db.module_enabled(guild.id, "logging"):
            return
        channel_id = await db.get_guild_setting(guild.id, key)
        if not channel_id:
            return
        channel = guild.get_channel(int(channel_id))
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

    # -- message events ------------------------------------------------
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return

        content = message.content or "(no text content)"
        att_links = [f"[{a.filename}]({a.url})" for a in message.attachments]
        att_str = f"\n**Attachments:** {', '.join(att_links)}" if att_links else ""

        # store for snipe
        await db.execute(
            "INSERT OR REPLACE INTO snipes (guild_id, channel_id, author, content, kind)"
            " VALUES (?, ?, ?, ?, 'delete')",
            (message.guild.id, message.channel.id, str(message.author), (content + att_str)[:1900]),
        )

        embed = embeds.titled(
            await self.bot.tr(message.guild.id, "log_msg_deleted", channel=message.channel.mention),
            f"**Author:** {message.author.mention} (`{message.author.id}`)\n"
            f"**Content:**\n{content[:1000]}{att_str}"
        )
        embed.color = discord.Color.red()
        await self._send(message.guild, "message_log_channel", embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.guild is None or before.author.bot:
            return
        if before.content == after.content:
            return

        await db.execute(
            "INSERT OR REPLACE INTO snipes (guild_id, channel_id, author, content, kind)"
            " VALUES (?, ?, ?, ?, 'edit')",
            (before.guild.id, before.channel.id, str(before.author), (before.content or "")[:1900]),
        )

        embed = embeds.titled(
            await self.bot.tr(before.guild.id, "log_msg_edited", channel=before.channel.mention),
            f"**Author:** {before.author.mention} [Jump to Message]({after.jump_url})\n"
            f"**Before:**\n{before.content[:500] or '(empty)'}\n\n"
            f"**After:**\n{after.content[:500] or '(empty)'}"
        )
        embed.color = discord.Color.gold()
        await self._send(before.guild, "message_log_channel", embed)

    # -- member events ---------------------------------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        embed = embeds.titled(
            await self.bot.tr(member.guild.id, "log_member_join"),
            f"{member.mention} **{member}** (`{member.id}`)\n"
            f"Account created: <t:{int(member.created_at.timestamp())}:R>"
        )
        embed.color = discord.Color.green()
        embed.set_thumbnail(url=member.display_avatar.url)
        await self._send(member.guild, "member_log_channel", embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        roles = ", ".join(r.mention for r in member.roles[1:][:20]) or "None"
        moderator = ""
        try:
            async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
                if entry.target.id == member.id:
                    moderator = f"\n**Kicked by:** {entry.user.mention} (Reason: `{entry.reason or 'None'}`)"
                    break
        except (discord.HTTPException, discord.Forbidden):
            pass

        embed = embeds.titled(
            await self.bot.tr(member.guild.id, "log_member_leave"),
            f"**{member}** (`{member.id}`)\n**Roles:** {roles}{moderator}"
        )
        embed.color = discord.Color.orange()
        await self._send(member.guild, "member_log_channel", embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        mod_info = ""
        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
                if entry.target.id == user.id:
                    mod_info = f"\n**Banned by:** {entry.user.mention} — `{entry.reason or 'No reason provided'}`"
                    break
        except (discord.HTTPException, discord.Forbidden):
            pass

        embed = embeds.titled(
            await self.bot.tr(guild.id, "log_member_ban"),
            f"**{user}** (`{user.id}`){mod_info}"
        )
        embed.color = discord.Color.red()
        await self._send(guild, "member_log_channel", embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        mod_info = ""
        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.unban):
                if entry.target.id == user.id:
                    mod_info = f"\n**Unbanned by:** {entry.user.mention}"
                    break
        except (discord.HTTPException, discord.Forbidden):
            pass

        embed = embeds.titled(
            await self.bot.tr(guild.id, "log_member_unban"),
            f"**{user}** (`{user.id}`){mod_info}"
        )
        embed.color = discord.Color.green()
        await self._send(guild, "member_log_channel", embed)

    # -- voice events ----------------------------------------------------
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                    before: discord.VoiceState,
                                    after: discord.VoiceState) -> None:
        if before.channel == after.channel:
            return
        if before.channel is None and after.channel is not None:
            key, desc = "log_voice_join", f"{member.mention} joined {after.channel.mention}"
        elif before.channel is not None and after.channel is None:
            key, desc = "log_voice_leave", f"{member.mention} left {before.channel.mention}"
        else:
            key, desc = "log_voice_move", f"{member.mention} moved from {before.channel.mention} to {after.channel.mention}"
        embed = embeds.titled(await self.bot.tr(member.guild.id, key), desc)
        await self._send(member.guild, "voice_log_channel", embed)

    # -- channel / role events --------------------------------------------
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        embed = embeds.titled(await self.bot.tr(channel.guild.id, "log_channel_created"),
                              f"{channel.mention} (`{channel.name}` — {channel.type})")
        embed.color = discord.Color.green()
        await self._send(channel.guild, "server_log_channel", embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        embed = embeds.titled(await self.bot.tr(channel.guild.id, "log_channel_deleted"),
                              f"**#{channel.name}** (`{channel.id}` — {channel.type})")
        embed.color = discord.Color.red()
        await self._send(channel.guild, "server_log_channel", embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        embed = embeds.titled(await self.bot.tr(role.guild.id, "log_role_created"),
                              f"{role.mention} (`{role.name}` — `{role.id}`)")
        embed.color = discord.Color.green()
        await self._send(role.guild, "server_log_channel", embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        embed = embeds.titled(await self.bot.tr(role.guild.id, "log_role_deleted"),
                              f"**@{role.name}** (`{role.id}`)")
        embed.color = discord.Color.red()
        await self._send(role.guild, "server_log_channel", embed)

    # -- nickname changes ---------------------------------------------------
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.nick != after.nick:
            embed = embeds.titled(
                await self.bot.tr(after.guild.id, "log_nick_changed"),
                f"**{after}** (`{after.id}`)\n**Before:** `{before.nick or before.name}`\n**After:** `{after.nick or after.name}`"
            )
            await self._send(after.guild, "member_log_channel", embed)

    # ------------------------------------------------------------------
    @commands.hybrid_group(name="setlog", description="Set log channels.", invoke_without_command=True)
    @commands.guild_only()
    @module_enabled("logging")
    @is_mod()
    async def setlog(self, ctx: commands.Context) -> None:
        keys = {
            "message": "message_log_channel",
            "member": "member_log_channel",
            "voice": "voice_log_channel",
            "server": "server_log_channel",
            "mod": "mod_log_channel",
        }
        lines = []
        for name, key in keys.items():
            cid = await db.get_guild_setting(ctx.guild.id, key)
            lines.append(f"**{name.capitalize()}:** <#{cid}>" if cid else f"**{name.capitalize()}:** —")
        await ctx.send(embed=embeds.titled("📜 Log Channels Configuration", "\n".join(lines)))

    @setlog.command(name="message", description="Channel for message edit/delete logs.")
    async def setlog_message(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        await db.set_guild_setting(ctx.guild.id, "message_log_channel", channel.id)
        await ctx.send(embed=embeds.success(f"Message logs → {channel.mention}"))

    @setlog.command(name="member", description="Channel for join/leave/ban logs.")
    async def setlog_member(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        await db.set_guild_setting(ctx.guild.id, "member_log_channel", channel.id)
        await ctx.send(embed=embeds.success(f"Member logs → {channel.mention}"))

    @setlog.command(name="voice", description="Channel for voice logs.")
    async def setlog_voice(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        await db.set_guild_setting(ctx.guild.id, "voice_log_channel", channel.id)
        await ctx.send(embed=embeds.success(f"Voice logs → {channel.mention}"))

    @setlog.command(name="server", description="Channel for channel/role logs.")
    async def setlog_server(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        await db.set_guild_setting(ctx.guild.id, "server_log_channel", channel.id)
        await ctx.send(embed=embeds.success(f"Server logs → {channel.mention}"))

    @setlog.command(name="mod", description="Channel for moderation action logs.")
    async def setlog_mod(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        await db.set_guild_setting(ctx.guild.id, "mod_log_channel", channel.id)
        await ctx.send(embed=embeds.success(f"Mod logs → {channel.mention}"))


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(Logging(bot))
