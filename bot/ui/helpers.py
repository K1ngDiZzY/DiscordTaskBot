"""Date/time parsing helpers shared across UI modules.

Provides :func:`_parse_dt` for free-text date entry and
:func:`_local_to_utc` for timezone conversion, plus the preset
constants used by the date picker.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bot.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DT_FORMATS = [
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M",
    "%d/%m/%Y %H:%M",
    "%d-%m-%Y %H:%M",
    "%Y-%m-%d",
]

# Presets shown in the quick-date select menu.
# Value format:  "<offset_hours>h" | "today_<HH>" | "tomorrow_<HH>" | "<days>d"
_DATE_PRESETS: list[tuple[str, str, str]] = [
    ("⏰", "In 1 hour",           "1h"),
    ("⏰", "In 2 hours",          "2h"),
    ("⏰", "In 4 hours",          "4h"),
    ("📅", "Today at 5:00 PM",    "today_17"),
    ("📅", "Tomorrow at 9:00 AM", "tomorrow_09"),
    ("📅", "Tomorrow at 5:00 PM", "tomorrow_17"),
    ("📅", "In 1 week",           "7d"),
    ("✏️", "Custom date/time…",   "custom"),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_preset(value: str) -> datetime:
    """Convert a preset select value to a UTC-naive :class:`datetime`.

    Args:
        value: One of the preset strings from :data:`_DATE_PRESETS`.

    Returns:
        A naive datetime representing the resolved UTC time.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    if value.endswith("h"):
        return now + timedelta(hours=int(value[:-1]))
    if value.endswith("d"):
        return now + timedelta(days=int(value[:-1]))
    if value.startswith("today_"):
        hour = int(value.split("_")[1])
        return now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if value.startswith("tomorrow_"):
        hour = int(value.split("_")[1])
        return (now + timedelta(days=1)).replace(
            hour=hour, minute=0, second=0, microsecond=0
        )
    raise ValueError(f"Unknown preset: {value}")


def _local_to_utc(dt: datetime) -> datetime:
    """Convert a naive datetime in ``bot_timezone`` to a naive UTC datetime.

    If the configured timezone is invalid, falls back to treating the
    input as UTC and logs a warning.

    Args:
        dt: A naive datetime in the bot's configured local timezone.

    Returns:
        A naive datetime in UTC.
    """
    try:
        tz = ZoneInfo(settings.bot_timezone)
    except (ZoneInfoNotFoundError, KeyError):
        logger.warning(
            "Unknown BOT_TIMEZONE %r — treating input as UTC.",
            settings.bot_timezone,
        )
        return dt
    aware_local = dt.replace(tzinfo=tz)
    return aware_local.astimezone(UTC).replace(tzinfo=None)


def _parse_dt(value: str) -> datetime | None:
    """Try to parse a user-supplied datetime string.

    Supports ``YYYY-MM-DD HH:MM`` and common shorthand:
    ``today HH:MM``, ``tomorrow HH:MM``, ``in Xh``, ``in Xd``.

    Args:
        value: Raw string from the user.

    Returns:
        A naive :class:`datetime` (treated as UTC), or ``None`` if empty.

    Raises:
        ValueError: If the string cannot be parsed.
    """
    value = value.strip()
    if not value:
        return None

    lower = value.lower()

    # Relative shorthands — relative to now in UTC
    if lower.startswith("in "):
        rest = lower[3:].strip()
        try:
            if rest.endswith("h"):
                return datetime.now(UTC).replace(tzinfo=None) + timedelta(
                    hours=float(rest[:-1])
                )
            if rest.endswith("d"):
                return datetime.now(UTC).replace(tzinfo=None) + timedelta(
                    days=float(rest[:-1])
                )
        except ValueError:
            pass

    # today / tomorrow — interpret entered time as local, convert to UTC
    for prefix, delta_days in (("today ", 0), ("tomorrow ", 1)):
        if lower.startswith(prefix):
            time_part = value[len(prefix):].strip()
            for fmt in ("%H:%M", "%I:%M %p", "%I%p"):
                try:
                    t = datetime.strptime(time_part, fmt)
                    local_now = datetime.now(
                        ZoneInfo(settings.bot_timezone)
                    ).replace(tzinfo=None)
                    base = (local_now + timedelta(days=delta_days)).replace(
                        hour=t.hour, minute=t.minute, second=0, microsecond=0
                    )
                    return _local_to_utc(base)
                except (ValueError, ZoneInfoNotFoundError):
                    continue
            raise ValueError(
                f"Could not parse time '{time_part}'. Use HH:MM (e.g. 09:00)."
            )

    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue

    raise ValueError(
        f"Could not parse '{value}'. "
        "Try: YYYY-MM-DD HH:MM · today 09:00 · tomorrow 17:00 · in 2h"
    )
