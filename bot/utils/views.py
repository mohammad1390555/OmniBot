# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Reusable interactive views: pagination and confirm buttons."""

from __future__ import annotations

import discord

from bot.core.config import config


class Paginator(discord.ui.View):
    """Prev/Next buttons over a list of embeds."""

    def __init__(self, pages: list[discord.Embed], author_id: int, timeout: float = 120):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.author_id = author_id
        self.index = 0
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_btn.disabled = self.index == 0
        self.next_btn.disabled = self.index >= len(self.pages) - 1

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary, custom_id="paginator_prev")
    async def prev_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.defer()
        self.index = max(0, self.index - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary, custom_id="paginator_next")
    async def next_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.defer()
        self.index = min(len(self.pages) - 1, self.index + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore[union-attr]


class ConfirmView(discord.ui.View):
    """Yes/No confirmation. Result stored in self.value."""

    def __init__(self, author_id: int, lang: str = "en", timeout: float = 30):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value: bool | None = None
        self.yes_btn.label = config.tr(lang, "confirm_yes")
        self.no_btn.label = config.tr(lang, "confirm_no")

    @discord.ui.button(style=discord.ButtonStyle.success, custom_id="confirm_yes")
    async def yes_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.defer()
        self.value = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(style=discord.ButtonStyle.danger, custom_id="confirm_no")
    async def no_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.defer()
        self.value = False
        await interaction.response.defer()
        self.stop()
