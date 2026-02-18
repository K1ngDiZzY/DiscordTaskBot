"""Entry point for the Discord Task Bot.

Run with::

    python main.py

or, on a Raspberry Pi managed by systemd::

    python -m bot  # (add a __main__.py if desired)
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from bot.config import settings
from bot.core import DiscordBot


def _configure_logging() -> None:
    """Set up the root logger with a human-friendly format."""
    level = getattr(logging, str(settings.log_level).upper(), logging.INFO)
    log_format = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))

    # File handler (writes alongside the DB)
    log_dir = Path(settings.database_path).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "bot.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))

    logging.basicConfig(level=level, handlers=[handler, file_handler])

    # Silence noisy third-party loggers
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)


async def _main() -> None:
    """Async entry point — creates and runs the bot."""
    _configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting Discord Task Bot…")

    bot = DiscordBot()
    async with bot:
        await bot.start(settings.discord_token)


def main() -> None:
    """Synchronous wrapper so the script can be invoked directly."""
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass  # Clean shutdown on Ctrl-C


if __name__ == "__main__":
    main()
