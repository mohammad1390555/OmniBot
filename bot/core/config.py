"""Configuration loader.

Reads config/config.yml and config/messages.yml once at startup and
exposes them through a small helper API. Everything the user can tune
lives in the config/ folder.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
CONFIG_PATH = CONFIG_DIR / "config.yml"
MESSAGES_PATH = CONFIG_DIR / "messages.yml"


class Config:
    """Dot-path accessor over the parsed YAML config."""

    def __init__(self) -> None:
        self.raw: dict[str, Any] = {}
        self.messages: dict[str, Any] = {}
        self.load()

    # -- loading -----------------------------------------------------
    def load(self) -> None:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            self.raw = yaml.safe_load(fh) or {}
        with open(MESSAGES_PATH, "r", encoding="utf-8") as fh:
            self.messages = yaml.safe_load(fh) or {}

    def reload(self) -> None:
        self.load()

    # -- access ------------------------------------------------------
    def get(self, path: str, default: Any = None) -> Any:
        """Fetch a nested value with dot notation: get('bot.branding.color')."""
        node: Any = self.raw
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    # -- convenience -------------------------------------------------
    @property
    def token(self) -> str:
        # Environment variable always wins over the YAML file.
        return os.getenv("DISCORD_TOKEN") or self.get("bot.token", "") or ""

    @property
    def default_prefix(self) -> str:
        return self.get("bot.default_prefix", "!")

    @property
    def default_language(self) -> str:
        return self.get("bot.default_language", "en")

    @property
    def branding(self) -> dict[str, Any]:
        return self.get("bot.branding", {}) or {}

    @property
    def color(self) -> int:
        hex_color = str(self.branding.get("color", "#5865F2")).lstrip("#")
        try:
            return int(hex_color, 16)
        except ValueError:
            return 0x5865F2

    @property
    def owner_ids(self) -> set[int]:
        return {int(x) for x in self.get("bot.owner_ids", []) or []}

    @property
    def sqlite_path(self) -> str:
        return self.get("database.sqlite_path", "data/omnibot.db")

    # -- i18n --------------------------------------------------------
    def tr(self, lang: str, key: str, **kwargs: Any) -> str:
        """Translate a message key for a language, falling back to English."""
        lang_block = self.messages.get(lang) or {}
        text = lang_block.get(key)
        if text is None:
            text = (self.messages.get("en") or {}).get(key, key)
        try:
            return text.format(**kwargs) if kwargs else text
        except (KeyError, IndexError, ValueError):
            return text


# Singleton used across the codebase.
config = Config()
