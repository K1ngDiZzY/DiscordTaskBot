---
mode: agent
description: Scaffold a new Discord bot Cog following project conventions
---

Create a new Discord bot Cog for the feature described below. Follow this checklist:

**What feature should this Cog implement?**
[Describe the feature here]

---

## Generation Requirements

Generate the following files:

### 1. `bot/cogs/<feature_name>.py`
- Subclass `commands.Cog` with a meaningful `name` parameter
- Constructor accepts `bot: DiscordBot` and stores it on `self.bot`
- Implement `cog_load` and `cog_unload` with `logger.info` messages
- Implement `cog_app_command_error` with user-friendly ephemeral error responses and full logging
- Define all slash commands using `@app_commands.command` with `name`, `description`, and `@app_commands.describe` for each parameter
- Defer interactions before any async work: `await interaction.response.defer(ephemeral=True)`
- Respond via `interaction.followup.send()` using `discord.Embed`
- Apply permission checks with `@app_commands.default_permissions` and `@app_commands.guild_only` where appropriate
- Add `async def setup(bot: DiscordBot) -> None` at module level
- Module-level docstring, Google-style docstrings on all public methods, full type hints

### 2. `tests/test_<feature_name>.py`
- Import the `Cog` class and the `setup` function
- Use `pytest-asyncio` (`asyncio_mode = "auto"` or `@pytest.mark.asyncio`)
- Mock `discord.Interaction` with `MagicMock`; mock `interaction.response.send_message` and `interaction.followup.send` as `AsyncMock`
- Write tests for:
  - Happy path of each command
  - At least one error path (e.g., missing permissions, invalid input)
  - `cog_app_command_error` handler behavior

### 3. Register in `bot/core.py`
- Add the new extension string to the `EXTENSIONS` list

---

## Code Style Reminders
- `from __future__ import annotations` at top
- `import logging; logger = logging.getLogger(__name__)`
- Imports ordered: stdlib → third-party (`discord`) → local (`bot.*`)
- `black`-compatible formatting (line length 88)
- No bare `except:` — catch specific exceptions only
