# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Embed builders with consistent branding."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import discord

from bot.core.config import config


def _base_embed(**kwargs: Any) -> discord.Embed:
    embed = discord.Embed(
        color=config.color,
        timestamp=datetime.now(timezone.utc),
        **kwargs,
    )
    footer_text = config.branding.get("footer_text", "OmniBot")
    thumb = config.branding.get("thumbnail_url") or None
    embed.set_footer(text=footer_text)
    if thumb:
        embed.set_thumbnail(url=thumb)
    return embed


def success(text: str, **kwargs: Any) -> discord.Embed:
    return _base_embed(description=f"✅ {text}", **kwargs)


def error(text: str, **kwargs: Any) -> discord.Embed:
    embed = _base_embed(description=f"❌ {text}", **kwargs)
    embed.color = discord.Color.red()
    return embed


def info(text: str, **kwargs: Any) -> discord.Embed:
    return _base_embed(description=text, **kwargs)


def titled(title: str, description: str = "", **kwargs: Any) -> discord.Embed:
    return _base_embed(title=title, description=description, **kwargs)
