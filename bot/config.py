"""Configuration settings loaded from environment variables.

Uses pydantic-settings so every value is validated on startup.
"""

from __future__ import annotations

from pydantic import Field
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

    # --- Required ---
    discord_token: str = Field(..., description="Discord bot token")

    # --- Optional ---
    discord_guild_id: int | None = Field(
        default=None,
        description=(
            "Guild ID for instant slash-command sync during development. "
            "Leave unset to sync globally."
        ),
    )
    database_path: str = Field(
        default="data/tasks.db",
        description="Path to the SQLite database file",
    )
    reminder_poll_seconds: int = Field(
        default=60,
        ge=10,
        description="How often (seconds) the reminder loop polls for due reminders",
    )
    log_level: str = Field(
        default="INFO",
        description="Python logging level (DEBUG, INFO, WARNING, ERROR)",
    )


# Singleton — import this anywhere you need config values.
# pydantic-settings resolves required fields from the environment at runtime;
# the call-arg false positive is a known mypy/pydantic-settings limitation.
settings: Settings = Settings()  # type: ignore[call-arg]
