"""Core bot class definition.

:class:`DiscordBot` subclasses :class:`commands.Bot` to add lifecycle
management for the database connection and cog loading.
"""

from __future__ import annotations

import logging

import aiohttp
import discord
from discord.ext import commands

from bot.config import settings
from bot.database import Database

logger = logging.getLogger(__name__)

_EXTENSIONS = (
    "bot.cogs.tasks",
    "bot.cogs.reminders",
)


class DiscordBot(commands.Bot):
    """The Task Bot — manages tasks and reminders for Discord users.

    Attributes:
        db: The open :class:`Database` instance, available after
            :meth:`setup_hook` completes.
    """

    def __init__(self) -> None:
        intents = discord.Intents.default()
        # We only need to read message content if using prefix commands,
        # which this bot does not. Slash commands don't require it.
        #
        # Use a connector with a higher keepalive timeout to prevent premature
        # SSL handshake timeouts on slower hardware (e.g. Raspberry Pi / ARM).
        connector = aiohttp.TCPConnector(
            limit=0,
            keepalive_timeout=60.0,
            force_close=False,
        )
        super().__init__(
            command_prefix="!",  # Fallback prefix — slash commands are primary.
            intents=intents,
            help_command=None,  # We use slash commands exclusively.
            connector=connector,
        )
        self.db: Database = Database(settings.database_path)
        self._ready_fired: bool = False

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    async def setup_hook(self) -> None:
        """Called by discord.py after login, before connecting to the gateway.

        Responsible for:
        1. Opening the database connection.
        2. Loading all cog extensions.
        3. Syncing the slash-command tree (guild-scoped for dev, global for prod).
        """
        # Open DB
        await self.db.connect()

        # Load cogs
        for extension in _EXTENSIONS:
            try:
                await self.load_extension(extension)
                logger.info("Loaded extension: %s", extension)
            except (ImportError, commands.ExtensionError) as exc:
                logger.exception("Failed to load extension %s: %s", extension, exc)

        # Sync slash commands
        if settings.discord_guild_id:
            guild = discord.Object(id=settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info(
                "Slash commands synced to guild %s (instant).",
                settings.discord_guild_id,
            )
        else:
            await self.tree.sync()
            logger.info("Slash commands synced globally (may take up to 1 hour).")

    async def close(self) -> None:
        """Gracefully close the database before disconnecting."""
        logger.info("Bot shutting down — closing database…")
        await self.db.close()
        await super().close()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    async def on_ready(self) -> None:
        """Fired when the bot is fully connected and ready.

        Sets a custom 'Watching' activity to indicate the bot is alive.
        Note: ``on_ready`` may fire multiple times after reconnections;
        startup logging is therefore guarded by a flag.
        """
        if not self._ready_fired:
            self._ready_fired = True
            logger.info("Logged in as %s (ID: %s)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="your tasks 📋",
            )
        )

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ) -> None:
        """Global fallback handler for unhandled slash command errors.

        Args:
            interaction: The failing interaction.
            error: The exception that was raised.
        """
        logger.exception("Unhandled app command error: %s", error)
        msg = "An unexpected error occurred. Please try again later."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
