# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Interactive help command with categorized selection menu."""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.core.bot import OmniBot
from bot.core.config import config
from bot.utils import embeds

CATEGORIES: dict[str, tuple[str, list[str]]] = {
    "Moderation": ("🔨", ["ban", "tempban", "unban", "kick", "softban", "mute", "unmute", "warn",
                          "unwarn", "clearwarns", "warnings", "modlogs", "purge", "lock", "unlock",
                          "lockdown", "slowmode", "nick"]),
    "AutoMod": ("🛡️", ["automod", "automod toggle", "automod antispam", "automod ghostping",
                        "automod addword", "automod removeword", "automod invites", "automod punishment"]),
    "Utility": ("🧰", ["ping", "userinfo", "serverinfo", "avatar", "banner", "servericon", "roleinfo",
                        "channelinfo", "botinfo", "math", "translate", "remind", "poll", "snipe",
                        "editsnipe", "clearsnipe", "afk", "suggest"]),
    "Economy": ("🪙", ["balance", "deposit", "withdraw", "daily", "weekly", "work", "pay", "rob",
                        "coinflip", "slots", "blackjack", "shop", "buy", "inventory", "leaderboard",
                        "addmoney", "removemoney"]),
    "Leveling": ("📈", ["rank", "xpleaderboard", "levelroles"]),
    "Tickets": ("🎫", ["ticket panel", "ticket supportrole", "ticket logchannel", "ticket adduser", "ticket removeuser", "ticket close"]),
    "Starboard": ("⭐", ["starboard", "starboard channel", "starboard threshold"]),
    "Birthdays": ("🎂", ["setbirthday", "birthday", "birthdays", "birthdaychannel"]),
    "Giveaways": ("🎉", ["gstart", "gend", "greroll", "glist"]),
    "Welcome": ("👋", ["setwelcome", "setleave", "autorole"]),
    "Roles": ("🎭", ["roles add", "roles remove", "roles list", "roles menu"]),
    "Fun": ("🎲", ["8ball", "rps", "ship", "rate", "dice", "coin", "choose", "trivia", "meme",
                    "setcount", "tag"]),
    "Music": ("🎵", ["play", "pause", "resume", "skip", "stop", "queue", "volume",
                      "nowplaying", "loop", "shuffle", "leave"]),
    "Config": ("⚙️", ["config", "config prefix", "config language", "config modules",
                        "config set", "setlog message/member/voice/server/mod"]),
}


class HelpSelect(discord.ui.Select):
    def __init__(self, bot: OmniBot, lang: str) -> None:
        self.bot = bot
        self.lang = lang
        options = [discord.SelectOption(label=name, emoji=emoji)
                   for name, (emoji, _) in CATEGORIES.items()]
        super().__init__(placeholder="Select a category to view commands...", options=options,
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
        embed = embeds.titled(f"{emoji} {name} Commands ({len(cmds)})", "  ".join(lines))
        embed.set_footer(text=f"Total {name} commands: {len(cmds)} • Slash commands supported")
        await interaction.response.edit_message(embed=embed)


class HelpView(discord.ui.View):
    def __init__(self, bot: OmniBot, lang: str) -> None:
        super().__init__(timeout=180)
        self.add_item(HelpSelect(bot, lang))


class Help(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="help", description="Show the interactive help menu with all bot features.")
    async def help_cmd(self, ctx: commands.Context) -> None:
        lang = config.default_language
        if ctx.guild:
            from bot.core.database import db
            g = await db.get_guild(ctx.guild.id)
            lang = g["language"]
        embed = embeds.titled(config.tr(lang, "help_title"),
                              config.tr(lang, "help_description"))
        embed.add_field(name="✨ Features", value=f"`{len(CATEGORIES)}` categories • `{sum(len(c[1]) for c in CATEGORIES.values())}` commands available", inline=False)
        view = HelpView(self.bot, lang)
        await ctx.send(embed=embed, view=view)


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(Help(bot))
