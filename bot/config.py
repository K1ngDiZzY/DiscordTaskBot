"""Configuration settings loaded from environment variables.

Uses pydantic-settings so every value is validated on startup.
"""

from __future__ import annotations

from pydantic import Field
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide configuration.

    Values are read from the environment (or a .env file in the working
    directory).  Sensible defaults are provided for optional settings.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Optional (validated at startup) ---
    # Make the token optional here so importing this module doesn't raise
    # a ValidationError during tests or other non-bot runs. The application
    # runtime should check that a token is present before attempting to
    # connect to Discord.
    discord_token: str | None = Field(
        default=None, description="Discord bot token (required to run the bot)"
    )

    # --- Optional ---
    discord_guild_id: int | None = Field(
        default=None,
        description=(
            "Guild ID for instant slash-command sync during development. "
            "Leave unset to sync globally."
        ),
    )

    @field_validator("discord_guild_id", mode="before")
    def _empty_str_to_none_discord_guild_id(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v
    database_path: str = Field(
        default="data/tasks.db",
        description="Path to the SQLite database file",
    )
    reminder_poll_seconds: int = Field(
        default=60,
        ge=10,
        description="How often (seconds) the reminder loop polls for due reminders",
    )
    bot_timezone: str = Field(
        default="UTC",
        description=(
            "IANA timezone name for the bot's users (e.g. America/Chicago). "
            "Times entered by users are interpreted in this timezone and "
            "converted to UTC before storage."
        ),
    )
    log_level: str = Field(
        default="INFO",
        description="Python logging level (DEBUG, INFO, WARNING, ERROR)",
    )


# Singleton — import this anywhere you need config values.
# pydantic-settings resolves required fields from the environment at runtime;
# the call-arg false positive is a known mypy/pydantic-settings limitation.
settings: Settings = Settings()  # type: ignore[call-arg]
