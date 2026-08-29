# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Human duration parsing and formatting helpers."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_UNITS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
    "w": 604800, "week": 604800, "weeks": 604800,
}

_PATTERN = re.compile(r"(\d+)\s*([a-zA-Z]+)")


def parse_duration(text: str) -> timedelta | None:
    """Parse '1h30m', '2 days', '90s' into a timedelta. None if invalid."""
    if not text:
        return None
    matches = _PATTERN.findall(text.strip().lower())
    if not matches:
        return None
    total = 0
    for amount, unit in matches:
        if unit not in _UNITS:
            return None
        total += int(amount) * _UNITS[unit]
    if total <= 0:
        return None
    return timedelta(seconds=total)


def format_duration(delta: timedelta) -> str:
    """Format a timedelta as '1d 2h 3m 4s' (compact)."""
    total = int(delta.total_seconds())
    parts = []
    for name, secs in (("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if total >= secs:
            parts.append(f"{total // secs}{name}")
            total %= secs
    return " ".join(parts) or "0s"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def from_iso(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def discord_ts(dt: datetime, style: str = "R") -> str:
    """Discord dynamic timestamp markup."""
    return f"<t:{int(dt.timestamp())}:{style}>"
