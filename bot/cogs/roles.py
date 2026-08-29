# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Self-assignable roles via select menu + role management helpers."""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.core.bot import OmniBot
from bot.core.database import db
from bot.utils import embeds
from bot.utils.checks import is_mod, module_enabled


class RoleSelect(discord.ui.Select):
    def __init__(self, bot: OmniBot, roles: list[discord.Role]) -> None:
        self.bot = bot
        options = [
            discord.SelectOption(
                label=r.name,
                value=str(r.id),
                description=f"Click to add/remove the @{r.name} role"
            ) for r in roles[:25]
        ]
        super().__init__(placeholder="Select a role to toggle...", min_values=1, max_values=1,
                         options=options, custom_id="omnibot:role_select")

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.defer()

        role = interaction.guild.get_role(int(self.values[0]))
        if role is None:
            return await interaction.response.send_message(embed=embeds.error("Role no longer exists."), ephemeral=True)

        member = interaction.user
        if role in member.roles:
            try:
                await member.remove_roles(role, reason="Self-role menu")
                msg = await self.bot.tr(interaction.guild.id, "roles_removed", role=role.mention)
                await interaction.response.send_message(embed=embeds.success(msg), ephemeral=True)
            except discord.HTTPException:
                await interaction.response.send_message(embed=embeds.error("Cannot remove role (role hierarchy)."), ephemeral=True)
        else:
            try:
                await member.add_roles(role, reason="Self-role menu")
                msg = await self.bot.tr(interaction.guild.id, "roles_added", role=role.mention)
                await interaction.response.send_message(embed=embeds.success(msg), ephemeral=True)
            except discord.HTTPException:
                await interaction.response.send_message(embed=embeds.error("Cannot assign role (role hierarchy)."), ephemeral=True)


class RoleMenuView(discord.ui.View):
    def __init__(self, bot: OmniBot, roles: list[discord.Role]) -> None:
        super().__init__(timeout=None)
        self.add_item(RoleSelect(bot, roles))


class Roles(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot

    @commands.hybrid_group(name="roles", description="Self-assignable role tools.",
                           invoke_without_command=True)
    @commands.guild_only()
    @module_enabled("roles")
    @is_mod()
    async def roles(self, ctx: commands.Context) -> None:
        await ctx.send(embed=embeds.info(
            "**🎭 Role Management Commands:**\n"
            "`roles add @role` — Add a self-assignable role\n"
            "`roles remove @role` — Remove a role from self-assignable list\n"
            "`roles list` — View all configured self-assignable roles\n"
            "`roles menu` — Post the interactive dropdown menu in this channel"))

    @roles.command(name="add", description="Add a self-assignable role.")
    async def roles_add(self, ctx: commands.Context, role: discord.Role) -> None:
        stored = await db.get_guild_setting(ctx.guild.id, "self_roles", []) or []
        if role.id not in stored:
            stored.append(role.id)
        await db.set_guild_setting(ctx.guild.id, "self_roles", stored)
        await ctx.send(embed=embeds.success(f"Added {role.mention} to self-assignable roles."))

    @roles.command(name="remove", description="Remove a self-assignable role.")
    async def roles_remove(self, ctx: commands.Context, role: discord.Role) -> None:
        stored = await db.get_guild_setting(ctx.guild.id, "self_roles", []) or []
        stored = [r for r in stored if r != role.id]
        await db.set_guild_setting(ctx.guild.id, "self_roles", stored)
        await ctx.send(embed=embeds.success(f"Removed **{role.name}** from self-assignable roles."))

    @roles.command(name="list", description="List all self-assignable roles.")
    async def roles_list(self, ctx: commands.Context) -> None:
        stored = await db.get_guild_setting(ctx.guild.id, "self_roles", []) or []
        roles = [f"• <@&{rid}>" for rid in stored if ctx.guild.get_role(rid)]
        embed = embeds.titled("🎭 Self-Assignable Roles", "\n".join(roles) or "No self-assignable roles configured.")
        await ctx.send(embed=embed)

    @roles.command(name="menu", description="Post the role selection dropdown menu here.")
    async def roles_menu(self, ctx: commands.Context) -> None:
        stored = await db.get_guild_setting(ctx.guild.id, "self_roles", []) or []
        role_objs = [r for r in (ctx.guild.get_role(rid) for rid in stored) if r]
        if not role_objs:
            return await ctx.send(embed=embeds.error("No self-assignable roles configured. Use `roles add` first."))

        if ctx.message:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass

        view = RoleMenuView(self.bot, role_objs)
        embed = embeds.titled(await self.bot.tr(ctx.guild.id, "roles_menu_title"),
                              "Select a role from the dropdown menu below to add or remove it from yourself.")
        await ctx.channel.send(embed=embed, view=view)


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(Roles(bot))
