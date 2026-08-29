# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Ticket system: button-opened private channels, claim, close, transcript, user management."""

from __future__ import annotations

import asyncio
import io

import discord
from discord.ext import commands

from bot.core.bot import OmniBot
from bot.core.config import config
from bot.core.database import db
from bot.utils import embeds
from bot.utils.checks import is_mod, module_enabled


class TicketOpenButton(discord.ui.View):
    def __init__(self, bot: OmniBot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.primary,
                       emoji="🎫", custom_id="omnibot:ticket_open")
    async def open_ticket(self, interaction: discord.Interaction, _: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user
        if guild is None:
            return

        # Check open ticket limit
        max_per_user = int(config.get("tickets.max_per_user", 1))
        row = await db.fetchone(
            "SELECT COUNT(*) AS c FROM tickets WHERE guild_id = ? AND user_id = ? AND status = 'open'",
            (guild.id, user.id),
        )
        if row and row["c"] >= max_per_user:
            return await interaction.response.send_message(
                embed=embeds.error(await self.bot.tr(guild.id, "ticket_limit")), ephemeral=True)

        # Find or create category
        cat_id = await db.get_guild_setting(guild.id, "ticket_category")
        category = guild.get_channel(int(cat_id)) if cat_id else None
        if category is None or not isinstance(category, discord.CategoryChannel):
            overwrites_cat = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True),
            }
            category = await guild.create_category("🎫 Tickets", overwrites=overwrites_cat)
            await db.set_guild_setting(guild.id, "ticket_category", category.id)

        support_role_id = await db.get_guild_setting(guild.id, "ticket_support_role")
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True, send_messages=True),
        }
        if support_role_id:
            role = guild.get_role(int(support_role_id))
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        channel = await guild.create_text_channel(
            f"ticket-{user.name[:20]}", category=category, overwrites=overwrites,
            topic=f"Ticket for {user} (id {user.id})")

        cur = await db.execute(
            "INSERT INTO tickets (guild_id, channel_id, user_id) VALUES (?, ?, ?)",
            (guild.id, channel.id, user.id),
        )
        ticket_id = cur.lastrowid or 0

        await interaction.response.send_message(
            embed=embeds.success(await self.bot.tr(guild.id, "ticket_created", channel=channel.mention)),
            ephemeral=True)

        view = TicketControls(self.bot)
        await channel.send(
            content=f"{user.mention}",
            embed=embeds.titled(
                f"🎫 Ticket #{ticket_id}",
                "Thank you for reaching out! Staff will assist you shortly.\n"
                "Click **Claim** to assign yourself, or **Close** to finish."),
            view=view)


class TicketControls(discord.ui.View):
    def __init__(self, bot: OmniBot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.success,
                       emoji="🙋", custom_id="omnibot:ticket_claim")
    async def claim(self, interaction: discord.Interaction, _: discord.ui.Button):
        channel = interaction.channel
        if channel is None:
            return
        row = await db.fetchone(
            "SELECT * FROM tickets WHERE channel_id = ? AND status = 'open'",
            (channel.id,),
        )
        if not row:
            return await interaction.response.send_message(embed=embeds.error("This is not an active ticket."), ephemeral=True)

        await db.execute("UPDATE tickets SET claimed_by = ? WHERE id = ?",
                         (interaction.user.id, row["id"]))
        await interaction.response.send_message(
            embed=embeds.success(f"🙋 Ticket #{row['id']} claimed by {interaction.user.mention}."))

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger,
                       emoji="🔒", custom_id="omnibot:ticket_close")
    async def close(self, interaction: discord.Interaction, _: discord.ui.Button):
        guild = interaction.guild
        channel = interaction.channel
        if guild is None or not isinstance(channel, discord.TextChannel):
            return

        row = await db.fetchone(
            "SELECT * FROM tickets WHERE channel_id = ?",
            (channel.id,),
        )
        ticket_id = row["id"] if row else 0

        # Transcript generation
        if bool(config.get("tickets.save_transcript", True)):
            lines = [f"=== TRANSCRIPT FOR TICKET #{ticket_id} ({channel.name}) ===",
                     f"Guild: {guild.name} ({guild.id})",
                     f"Closed by: {interaction.user} ({interaction.user.id})",
                     "========================================\n"]
            async for msg in channel.history(limit=1000, oldest_first=True):
                att_info = f" [Attachment: {msg.attachments[0].url}]" if msg.attachments else ""
                lines.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}] {msg.author} ({msg.author.id}): {msg.content}{att_info}")

            transcript = "\n".join(lines) or "(empty transcript)"
            log_id = await db.get_guild_setting(guild.id, "ticket_log_channel")
            if log_id:
                log_channel = guild.get_channel(int(log_id))
                if isinstance(log_channel, discord.TextChannel):
                    file = discord.File(io.BytesIO(transcript.encode("utf-8")),
                                        filename=f"ticket-{ticket_id}.txt")
                    try:
                        await log_channel.send(
                            embed=embeds.titled(
                                f"📄 Transcript — Ticket #{ticket_id}",
                                f"**Channel:** `{channel.name}`\n**Closed by:** {interaction.user.mention}"),
                            file=file)
                    except discord.HTTPException:
                        pass

        if row:
            await db.execute("UPDATE tickets SET status = 'closed' WHERE id = ?", (row["id"],))

        await interaction.response.send_message(
            embed=embeds.success(await self.bot.tr(guild.id, "ticket_closed", user=str(interaction.user))))

        await asyncio.sleep(2)
        try:
            await channel.delete(reason=f"Ticket closed by {interaction.user}")
        except discord.HTTPException:
            pass


class Tickets(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot

    @commands.hybrid_group(name="ticket", description="Ticket system setup and management.", invoke_without_command=True)
    @commands.guild_only()
    @module_enabled("tickets")
    async def ticket(self, ctx: commands.Context) -> None:
        await ctx.send(embed=embeds.info(
            "**🎫 Ticket Commands:**\n"
            "`ticket panel` — Post the open-ticket button message (Admin/Mod)\n"
            "`ticket supportrole @role` — Set staff role for tickets\n"
            "`ticket logchannel #channel` — Set transcript log channel\n"
            "`ticket adduser @user` — Add member to current ticket\n"
            "`ticket removeuser @user` — Remove member from current ticket\n"
            "`ticket close` — Close the current ticket channel"))

    @ticket.command(name="panel", description="Post the ticket panel message here.")
    @is_mod()
    async def ticket_panel(self, ctx: commands.Context) -> None:
        if ctx.message:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass
        view = TicketOpenButton(self.bot)
        embed = embeds.titled("🎫 Support Tickets",
                              "Need assistance or have questions? Click the button below to open a private ticket with our staff team.")
        await ctx.channel.send(embed=embed, view=view)

    @ticket.command(name="supportrole", description="Set the role that can manage tickets.")
    @is_mod()
    async def ticket_supportrole(self, ctx: commands.Context, role: discord.Role) -> None:
        await db.set_guild_setting(ctx.guild.id, "ticket_support_role", role.id)
        await ctx.send(embed=embeds.success(f"Support role set to {role.mention}."))

    @ticket.command(name="logchannel", description="Set the channel for ticket transcripts.")
    @is_mod()
    async def ticket_logchannel(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        await db.set_guild_setting(ctx.guild.id, "ticket_log_channel", channel.id)
        await ctx.send(embed=embeds.success(f"Ticket transcripts → {channel.mention}."))

    @ticket.command(name="adduser", description="Add a user to the current ticket channel.")
    @is_mod()
    async def ticket_adduser(self, ctx: commands.Context, member: discord.Member) -> None:
        if not isinstance(ctx.channel, discord.TextChannel):
            return
        await ctx.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
        await ctx.send(embed=embeds.success(f"Added {member.mention} to this ticket."))

    @ticket.command(name="removeuser", description="Remove a user from the current ticket channel.")
    @is_mod()
    async def ticket_removeuser(self, ctx: commands.Context, member: discord.Member) -> None:
        if not isinstance(ctx.channel, discord.TextChannel):
            return
        await ctx.channel.set_permissions(member, overwrite=None)
        await ctx.send(embed=embeds.success(f"Removed {member.mention} from this ticket."))

    @ticket.command(name="close", description="Close the current ticket channel.")
    async def ticket_close(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.channel, discord.TextChannel):
            return
        row = await db.fetchone("SELECT * FROM tickets WHERE channel_id = ? AND status = 'open'", (ctx.channel.id,))
        if not row:
            return await ctx.send(embed=embeds.error("This command can only be used inside an active ticket channel."))
        view = TicketControls(self.bot)
        for child in view.children:
            if getattr(child, "custom_id", "") == "omnibot:ticket_close":
                # Create fake interaction or close directly
                pass
        # Perform close directly
        await db.execute("UPDATE tickets SET status = 'closed' WHERE id = ?", (row["id"],))
        await ctx.send(embed=embeds.success(await self.bot.tr(ctx.guild.id, "ticket_closed", user=str(ctx.author))))
        await asyncio.sleep(2)
        try:
            await ctx.channel.delete(reason=f"Ticket closed by {ctx.author}")
        except discord.HTTPException:
            pass


async def setup(bot: OmniBot) -> None:
    bot.add_view(TicketOpenButton(bot))
    bot.add_view(TicketControls(bot))
    await bot.add_cog(Tickets(bot))
