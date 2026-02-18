---
applyTo: "bot/**/*.py"
---

# Discord Integration Best Practices

Apply these rules to all Discord bot code under `bot/`.

## Library Usage

- Use `discord.py >= 2.x` or `py-cord >= 2.x`. Do **not** mix both.
- Import from `discord` and `discord.ext.commands` consistently.
- Use `discord.app_commands` for slash commands and `commands.Cog` for feature modules.

## Bot & Client Setup

- Subclass `commands.Bot` (not `discord.Client`) to enable the commands extension.
- Always set `intents` explicitly — never use `Intents.all()` in production. Grant only the intents the bot actually needs.
- Set `command_prefix` to a string constant or retrieve it from config.

```python
import discord
from discord.ext import commands

class DiscordBot(commands.Bot):
    """Custom bot class with lifecycle hooks."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # Only if reading message content
        intents.members = True           # Only if tracking member events
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self) -> None:
        """Called after login, before connecting. Load cogs here."""
        await self.load_extension("bot.cogs.tasks")
        await self.tree.sync()

    async def on_ready(self) -> None:
        logger.info("Logged in as %s (ID: %s)", self.user, self.user.id)
```

## Cog Architecture

- Every feature must live in its own **Cog** class under `bot/cogs/`.
- Cogs must define `async def cog_load(self)` for setup and `async def cog_unload(self)` for teardown.
- Register the cog via the module-level `async def setup(bot)` function.

```python
from discord.ext import commands

class TasksCog(commands.Cog, name="Tasks"):
    """Cog for managing user tasks."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        logger.info("TasksCog loaded")

    async def cog_unload(self) -> None:
        logger.info("TasksCog unloaded")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TasksCog(bot))
```

## Slash Commands & App Commands

- Prefer **slash commands** (`@app_commands.command`) over prefix commands for new features.
- Group related slash commands using `app_commands.Group`.
- Always provide a clear `name` and `description` for every command and parameter.
- Use `app_commands.describe()` to document individual parameters.
- Defer the interaction with `await interaction.response.defer()` before any long-running operations.

```python
import discord
from discord import app_commands

class TaskGroup(app_commands.Group, name="task", description="Manage your tasks"):

    @app_commands.command(name="add", description="Add a new task")
    @app_commands.describe(title="The task title", description="Optional task description")
    async def add_task(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str = "",
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        # ... logic ...
        await interaction.followup.send(f"Task '{title}' added!", ephemeral=True)
```

## Error Handling in Discord

- Implement `cog_app_command_error` on each Cog to handle slash command errors locally.
- Implement a global `on_app_command_error` on the bot for unhandled errors.
- Never expose stack traces or internal error messages to Discord users.
- Respond to the user with a friendly ephemeral error message.

```python
async def cog_app_command_error(
    self,
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> None:
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"Slow down! Try again in {error.retry_after:.1f}s.", ephemeral=True
        )
    else:
        logger.error("Unhandled command error: %s", error, exc_info=True)
        await interaction.response.send_message(
            "An unexpected error occurred. Please try again later.", ephemeral=True
        )
```

## Permissions & Checks

- Apply `@app_commands.checks.has_permissions()` or `@commands.has_permissions()` to restrict access.
- Use `@app_commands.default_permissions()` to set the default member permission requirement.
- For owner-only functionality, use `@commands.is_owner()`.
- Implement `guild_only` checks for commands that should not run in DMs.

```python
@app_commands.command(name="clear", description="Clear tasks for a user (Admin only)")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
async def clear_tasks(self, interaction: discord.Interaction, user: discord.Member) -> None:
    ...
```

## Embeds & UI

- Use `discord.Embed` for rich responses instead of long plain-text messages.
- Keep embed descriptions under 4096 characters; field values under 1024 characters.
- Always set `color` on embeds for visual consistency. Define your palette in a constants file.
- Use `discord.ui.View` with `discord.ui.Button` and `discord.ui.Select` for interactive components.
- Set a `timeout` on Views and handle `on_timeout` to disable components gracefully.

```python
SUCCESS_COLOR = discord.Color.green()
ERROR_COLOR   = discord.Color.red()
INFO_COLOR    = discord.Color.blurple()

def build_task_embed(task: TaskEntry) -> discord.Embed:
    """Build a standardized embed for a task entry."""
    embed = discord.Embed(
        title=task.title,
        description=task.description or "No description provided.",
        color=SUCCESS_COLOR if task.completed else INFO_COLOR,
    )
    embed.set_footer(text=f"ID: {task.user_id}")
    return embed
```

## Rate Limiting & Performance

- Always `await interaction.response.defer()` before any operation taking > 3 seconds.
- Use `bot.wait_for()` with a timeout to avoid hanging coroutines.
- Cache frequently-accessed guild/member data using a `TTLCache` (`cachetools`) instead of repeated API calls.
- Implement cooldowns with `@app_commands.checks.cooldown()` to prevent abuse.

## Configuration

- Load the bot token, guild IDs, and other settings from environment variables via `pydantic-settings`.
- Never hardcode guild IDs, channel IDs, or role IDs — store them in config or `.env`.

```python
from pydantic_settings import BaseSettings

class BotConfig(BaseSettings):
    discord_token: str
    command_prefix: str = "!"
    dev_guild_id: int | None = None
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
```
