---
applyTo: "**/*.py"
---

# Python Best Practices

Apply these rules to all Python files in this project.

## Code Style & Formatting

- Adhere strictly to **PEP 8**: 4-space indentation, 79-character line length for code, 72 for docstrings/comments.
- Use `black` (line length 88) for formatting and `isort` for import sorting.
- Group imports in this order: stdlib → third-party → local. Separate each group with a blank line.
- Prefer absolute imports over relative imports except within the same package.

## Type Annotations

- Add type hints to **all** function parameters, return types, and class attributes.
- Use `from __future__ import annotations` at the top of every module for forward references.
- Use `typing` module types for Python < 3.10 compatibility: `Optional[X]`, `Union[X, Y]`, `List[X]`, `Dict[K, V]`.
- For Python 3.10+, prefer `X | Y` union syntax and built-in generics (`list[X]`, `dict[K, V]`).
- Use `TypeAlias` for complex type definitions to improve readability.

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.core import DiscordBot
```

## Docstrings

- Use **Google-style** docstrings for all public modules, classes, methods, and functions.
- Every module must have a module-level docstring describing its purpose.

```python
def load_extension(name: str, *, package: str | None = None) -> None:
    """Load a Discord bot extension (cog) by name.

    Args:
        name: The dotted module path to the cog (e.g., 'bot.cogs.moderation').
        package: Optional package anchor for relative imports.

    Raises:
        ExtensionNotFound: If the extension module does not exist.
        ExtensionAlreadyLoaded: If the extension is already loaded.
    """
```

## Naming Conventions

| Item | Convention | Example |
|---|---|---|
| Module | `snake_case` | `task_manager.py` |
| Class | `PascalCase` | `TaskManager` |
| Function / Method | `snake_case` | `get_user_tasks()` |
| Constant | `UPPER_SNAKE_CASE` | `MAX_RETRIES = 3` |
| Private | leading `_` | `_internal_cache` |
| Dunder | double leading/trailing `__` | `__init__`, `__repr__` |

## Classes & Dataclasses

- Prefer **dataclasses** (`@dataclass`) or **Pydantic models** (`BaseModel`) over plain dicts for structured data.
- Define `__slots__` on hot-path classes for memory efficiency.
- Always implement `__repr__` for custom classes.

```python
from dataclasses import dataclass, field

@dataclass
class TaskEntry:
    """Represents a single user task entry."""

    user_id: int
    title: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    completed: bool = False
```

## Async / Await

- Mark all I/O-bound functions as `async def`.
- Never call blocking I/O (file reads, network, database) from sync context inside an async loop — use `asyncio.to_thread()` or an async library.
- Use `asyncio.gather()` for concurrent awaitable tasks.
- Avoid `asyncio.sleep(0)` except for intentional yielding.

```python
import asyncio

async def fetch_all(urls: list[str]) -> list[str]:
    """Fetch multiple URLs concurrently."""
    results = await asyncio.gather(*[fetch(url) for url in urls])
    return list(results)
```

## Error Handling

- Never use a bare `except:` or `except Exception:` without re-raising or logging.
- Define custom exception classes in `bot/exceptions.py` inheriting from a project base exception.
- Use `finally` for cleanup (closing connections, releasing locks).

```python
class BotError(Exception):
    """Base exception for all bot errors."""

class ConfigError(BotError):
    """Raised when configuration is invalid or missing."""
```

## Logging

- Use the standard `logging` module — never `print()` for diagnostics.
- Configure a logger per module using `logging.getLogger(__name__)`.
- Log at appropriate levels: `DEBUG` for trace data, `INFO` for lifecycle events, `WARNING` for recoverable issues, `ERROR` for failures.

```python
import logging

logger = logging.getLogger(__name__)

async def start_bot() -> None:
    logger.info("Bot is starting up...")
```

## Security

- Load all secrets from environment variables using `os.getenv()` or `pydantic-settings`.
- Never commit `.env` files — only commit `.env.example` with placeholder values.
- Validate all external input before use (user messages, API responses).

## Testing

- Use `pytest` with `pytest-asyncio` for all tests.
- Name test files `test_<module>.py` and test functions `test_<behavior>`.
- Use `pytest.mark.asyncio` (or configure `asyncio_mode = "auto"`) for async tests.
- Mock Discord objects and external services with `unittest.mock.AsyncMock`.

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_command_sends_response():
    ctx = MagicMock()
    ctx.send = AsyncMock()
    await my_command(ctx)
    ctx.send.assert_called_once()
```
