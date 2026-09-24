# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Interactive help command with a category select menu."""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.core.bot import OmniBot
from bot.core.config import config
from bot.utils import embeds

CATEGORIES: dict[str, tuple[str, list[str]]] = {
    "Moderation": ("🔨", ["ban", "unban", "kick", "softban", "mute", "unmute", "warn",
                          "warnings", "modlogs", "purge", "lock", "unlock", "lockdown",
                          "slowmode", "nick"]),
    "AutoMod": ("🛡️", ["automod", "automod toggle", "automod addword", "automod removeword",
                        "automod invites", "automod punishment"]),
    "Utility": ("🧰", ["ping", "userinfo", "serverinfo", "avatar", "banner", "roleinfo",
                        "channelinfo", "botinfo", "remind", "poll", "snipe", "editsnipe",
                        "afk", "suggest"]),
    "Economy": ("🪙", ["balance", "daily", "weekly", "work", "pay", "coinflip", "slots",
                        "leaderboard", "addmoney", "removemoney"]),
    "Leveling": ("📈", ["rank", "xpleaderboard"]),
    "Tickets": ("🎫", ["ticket panel", "ticket supportrole", "ticket logchannel"]),
    "Giveaways": ("🎉", ["gstart", "gend", "greroll", "glist"]),
    "Welcome": ("👋", ["setwelcome", "setleave", "autorole"]),
    "Roles": ("🎭", ["roles add", "roles remove", "roles menu"]),
    "Fun": ("🎲", ["8ball", "rps", "ship", "rate", "dice", "coin", "setcount",
                    "tag", "tag create", "tag delete"]),
    "Music": ("🎵", ["play", "pause", "resume", "skip", "stop", "queue", "volume",
                      "nowplaying", "loop", "shuffle"]),
    "Config": ("⚙️", ["config", "config prefix", "config language", "config modules",
                        "config set", "setlog message/member/voice/server/mod", "help"]),
}


class HelpSelect(discord.ui.Select):
    def __init__(self, bot: OmniBot, lang: str) -> None:
        self.bot = bot
        self.lang = lang
        options = [discord.SelectOption(label=name, emoji=emoji)
                   for name, (emoji, _) in CATEGORIES.items()]
        super().__init__(placeholder="Choose a category...", options=options,
                         custom_id="omnibot:help_select")

    async def callback(self, interaction: discord.Interaction) -> None:
        name = self.values[0]
        emoji, cmds = CATEGORIES[name]
        prefix = config.default_prefix
        if interaction.guild:
            from bot.core.database import db
            g = await db.get_guild(interaction.guild.id)
            prefix = g["prefix"] or prefix
        lines = [f"`{prefix}{c}`" for c in cmds]
        embed = embeds.titled(f"{emoji} {name}", " ".join(lines))
        await interaction.response.edit_message(embed=embed)


class HelpView(discord.ui.View):
    def __init__(self, bot: OmniBot, lang: str) -> None:
        super().__init__(# timeout config)
        self.add_item(HelpSelect(bot, lang))


class Help(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="help", description="Show the interactive help menu.")
    async def help_cmd(self, ctx: commands.Context) -> None:
        lang = config.default_language
        if ctx.guild:
            from bot.core.database import db
            g = await db.get_guild(ctx.guild.id)
            lang = g["language"]
        embed = embeds.titled(config.tr(lang, "help_title"),
                              config.tr(lang, "help_description"))
        view = HelpView(self.bot, lang)
        await ctx.send(embed=embed, view=view)


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(Help(bot))
