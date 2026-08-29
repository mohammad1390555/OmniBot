# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Ticket system: button-opened private channels, claim, close, transcript."""

from __future__ import annotations

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

        # ticket limit
        max_per_user = int(config.get("tickets.max_per_user", 1))
        row = await db.fetchone(
            "SELECT COUNT(*) AS c FROM tickets WHERE guild_id = ? AND user_id = ? AND status = 'open'",
            (guild.id, user.id),
        )
        if row and row["c"] >= max_per_user:
            return await interaction.response.send_message(
                embed=embeds.error(await self.bot.tr(guild.id, "ticket_limit")), ephemeral=True)

        # find or create category
        cat_id = await db.get_guild_setting(guild.id, "ticket_category")
        category = guild.get_channel(int(cat_id)) if cat_id else None
        if category is None:
            overwrites_cat = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True),
            }
            category = await guild.create_category("🎫 Tickets", overwrites=overwrites_cat)
            await db.set_guild_setting(guild.id, "ticket_category", category.id)

        support_role_id = await db.get_guild_setting(guild.id, "ticket_support_role")
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True),
        }
        if support_role_id:
            role = guild.get_role(int(support_role_id))
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        channel = await guild.create_text_channel(
            f"ticket-{user.name}", category=category, overwrites=overwrites,
            topic=f"Ticket for {user} (id {user.id})")

        cur = await db.execute(
            "INSERT INTO tickets (guild_id, channel_id, user_id) VALUES (?, ?, ?)",
            (guild.id, channel.id, user.id),
        )
        ticket_id = cur.lastrowid or 0

        await interaction.response.send_message(
            embed=embeds.success(await self.bot.tr(guild.id, "ticket_created", channel=channel.mention)),
            ephemeral=True)

        view = TicketControls(self.bot, ticket_id)
        await channel.send(
            content=f"{user.mention}",
            embed=embeds.titled(f"🎫 Ticket #{ticket_id}",
                                "Staff will be with you shortly. Use the buttons below to manage this ticket."),
            view=view)


class TicketControls(discord.ui.View):
    def __init__(self, bot: OmniBot, ticket_id: int) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.ticket_id = ticket_id

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.success,
                       emoji="🙋", custom_id="omnibot:ticket_claim")
    async def claim(self, interaction: discord.Interaction, _: discord.ui.Button):
        await db.execute("UPDATE tickets SET claimed_by = ? WHERE id = ?",
                         (interaction.user.id, self.ticket_id))
        await interaction.response.send_message(
            embed=embeds.success(f"🙋 Ticket claimed by {interaction.user.mention}."))

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger,
                       emoji="🔒", custom_id="omnibot:ticket_close")
    async def close(self, interaction: discord.Interaction, _: discord.ui.Button):
        guild = interaction.guild
        channel = interaction.channel

        # transcript
        if bool(config.get("tickets.save_transcript", True)):
            lines = []
            async for msg in channel.history(limit=500, oldest_first=True):
                lines.append(f"[{msg.created_at:%Y-%m-%d %H:%M}] {msg.author}: {msg.content}")
            transcript = "\n".join(lines) or "(empty)"
            log_id = await db.get_guild_setting(guild.id, "ticket_log_channel")
            if log_id:
                log_channel = guild.get_channel(int(log_id))
                if log_channel:
                    file = discord.File(io.BytesIO(transcript.encode()),
                                        filename=f"ticket-{self.ticket_id}.txt")
                    await log_channel.send(
                        embed=embeds.titled(f"📄 Transcript — ticket #{self.ticket_id}",
                                            f"Closed by {interaction.user}"),
                        file=file)

        await db.execute("UPDATE tickets SET status = 'closed' WHERE id = ?", (self.ticket_id,))
        await interaction.response.send_message(
            embed=embeds.success(await self.bot.tr(guild.id, "ticket_closed", user=str(interaction.user))))
        await discord.utils.sleep_delay(2)
        try:
            await channel.delete(reason=f"ticket closed by {interaction.user}")
        except discord.HTTPException:
            pass


class Tickets(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot

    @commands.hybrid_group(name="ticket", description="Ticket system setup.", invoke_without_command=True)
    @commands.guild_only()
    @module_enabled("tickets")
    @is_mod()
    async def ticket(self, ctx: commands.Context) -> None:
        await ctx.send(embed=embeds.info(
            "**Ticket setup commands:**\n"
            "`ticket panel` — post the open-ticket button message\n"
            "`ticket supportrole @role` — set the support role\n"
            "`ticket logchannel #channel` — set the transcript channel"))

    @ticket.command(name="panel", description="Post the ticket panel message here.")
    async def ticket_panel(self, ctx: commands.Context) -> None:
        view = TicketOpenButton(self.bot)
        embed = embeds.titled("🎫 Support Tickets",
                              "Click the button below to open a private ticket with our staff team.")
        await ctx.channel.send(embed=embed, view=view)
        await ctx.message.delete()

    @ticket.command(name="supportrole", description="Set the role that can see tickets.")
    async def ticket_supportrole(self, ctx: commands.Context, role: discord.Role) -> None:
        await db.set_guild_setting(ctx.guild.id, "ticket_support_role", role.id)
        await ctx.send(embed=embeds.success(f"Support role set to {role.mention}."))

    @ticket.command(name="logchannel", description="Set the channel for ticket transcripts.")
    async def ticket_logchannel(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        await db.set_guild_setting(ctx.guild.id, "ticket_log_channel", channel.id)
        await ctx.send(embed=embeds.success(f"Ticket transcripts → {channel.mention}."))


async def setup(bot: OmniBot) -> None:
    # register persistent views so buttons survive restarts
    bot.add_view(TicketOpenButton(bot))
    bot.add_view(TicketControls(bot, 0))
    await bot.add_cog(Tickets(bot))
