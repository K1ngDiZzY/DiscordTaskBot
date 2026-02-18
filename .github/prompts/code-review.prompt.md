---
mode: agent
description: Review Python or Discord bot code for quality, security, and best practices
---

Review the code provided (or the currently open file) against the project's standards. Produce a structured report covering:

## Code Review Checklist

### 1. Python Style & Formatting
- [ ] PEP 8 compliance (4-space indent, 88-char line length with `black`)
- [ ] Imports sorted: stdlib → third-party → local (via `isort`)
- [ ] No `print()` used for diagnostics — replaced with `logging`
- [ ] f-strings used instead of `.format()` or `%`

### 2. Type Hints & Docstrings
- [ ] All function parameters and return types annotated
- [ ] Class attributes annotated (or `__slots__` defined)
- [ ] `from __future__ import annotations` present where forward refs are used
- [ ] Google-style docstrings on all public functions, classes, and modules

### 3. Async Correctness
- [ ] All I/O-bound operations are `async`
- [ ] No blocking calls (`time.sleep`, `open()`, sync `requests`) in async context
- [ ] `asyncio.to_thread()` used for unavoidable sync I/O
- [ ] `asyncio.gather()` used for concurrent independent awaitable tasks

### 4. Error Handling
- [ ] No bare `except:` clauses
- [ ] All exceptions are specific (not just `Exception`)
- [ ] Errors are logged with `logger.error(..., exc_info=True)` before re-raising
- [ ] Custom exception types defined in `bot/exceptions.py`

### 5. Security
- [ ] No hardcoded tokens, passwords, or API keys
- [ ] All secrets loaded from environment variables or `pydantic-settings`
- [ ] User input validated and sanitized before use
- [ ] Sensitive commands protected with permission checks

### 6. Discord-Specific (if applicable)
- [ ] Intents are minimal — only what's actually needed
- [ ] `interaction.response.defer()` called before any operation > 3 seconds
- [ ] `followup.send()` used after `defer()`; `response.send_message()` used otherwise
- [ ] `cog_app_command_error` implemented on every Cog
- [ ] Embed colors defined as constants, not inline hex values
- [ ] Views have a `timeout` and implement `on_timeout`

### 7. Testing
- [ ] Tests exist for all non-trivial functions
- [ ] Tests use `pytest` + `pytest-asyncio`
- [ ] Discord objects mocked with `AsyncMock` / `MagicMock`
- [ ] At least one negative/error path tested per command

---

**Output Format:**

Provide:
1. A summary verdict: **Pass / Needs Minor Changes / Needs Major Changes**
2. A bullet list of **issues found**, each with file + line reference and severity (🔴 Critical / 🟡 Warning / 🔵 Info)
3. Corrected code snippets for each issue found
4. Any positive observations worth keeping
