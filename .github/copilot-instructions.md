# GitHub Copilot Repository Instructions

This is a Python-based Discord bot project. Follow these global instructions for all Copilot interactions in this repository.

## Project Overview

This project is a **Discord bot** built with Python using `discord.py` (or `py-cord`). The bot follows a modular cog-based architecture, async-first design, and full adherence to Python best practices.

## Language & Runtime

- **Language**: Python 3.11+
- **Primary library**: `discord.py >= 2.x` or `py-cord >= 2.x`
- **Environment management**: Use `venv` or `poetry`
- **Dependency file**: `requirements.txt` or `pyproject.toml`

## General Coding Standards

- Follow **PEP 8** for all Python code
- Use **type hints** on all function signatures and class attributes
- Write **docstrings** for all public modules, classes, and functions (Google or NumPy style)
- Prefer **f-strings** over `.format()` or `%`-formatting
- Use **dataclasses** or **Pydantic models** for structured data
- Keep functions **small and single-purpose**
- Avoid mutable default arguments
- Never use bare `except:` — always catch specific exceptions
- All I/O operations must be **async**

## Project Structure Convention

```
project/
├── .github/
│   ├── copilot-instructions.md
│   ├── instructions/
│   ├── agents/
│   ├── chatmodes/
│   └── prompts/
├── bot/
│   ├── __init__.py
│   ├── core.py          # Bot class definition
│   ├── config.py        # Settings via pydantic-settings or dotenv
│   └── cogs/            # Feature modules (Discord Cogs)
│       ├── __init__.py
│       └── example.py
├── tests/
│   ├── __init__.py
│   └── test_example.py
├── .env.example
├── pyproject.toml
├── README.md
└── main.py
```

## Error Handling

- Use structured logging via the `logging` module (never `print` for diagnostics)
- All Discord event handlers and commands must handle exceptions gracefully
- Use `try/except/finally` patterns consistently; log errors before re-raising
- Return meaningful error messages to Discord users without exposing internals

## Security

- **Never** hardcode tokens, secrets, or API keys — load from environment variables
- Use `.env` files locally; use secrets managers or environment variables in production
- Validate and sanitize all user input from Discord interactions
- Restrict sensitive commands with permission checks

## Testing

- Write tests with `pytest` and `pytest-asyncio`
- Mock Discord objects using `unittest.mock` or `discord.py` test utilities
- Aim for high coverage on business logic; avoid testing Discord internals

## Agent Team

This project uses a team of specialized Copilot agents. All development is handled by the team — never by a single agent in isolation.

| Agent | Role |
|---|---|
| `architect` | Lead Architect — breaks down features, delegates work packages, integrates results |
| `python-discord-dev` | Python Discord Developer — implements cogs, slash commands, interactions, embeds |
| `python-dev` | Python Developer — implements data models, utilities, config, repository classes |
| `code-reviewer` | Code Reviewer — reviews all code for quality, security, and correctness before merge |
| `tech-writer` | Technical Writer — produces and maintains README, command reference, architecture docs, changelogs |
| `agent-logger` | Agent Activity Logger — records what every agent does and writes structured logs to `.github/agent-logs/` for human review |

### Team Workflow

```
User request
    └─► Architect designs plan & delegates
            ├─► Python Developer       (data models, config, utilities)    ─┐
            ├─► Python Discord Dev     (cogs, commands, interactions)       ├─► Code Reviewer ─► Technical Writer ─► Agent Logger ─► Done
            └─► Python Developer       (tests)                             ─┘
```

- Start every feature request by opening the **Architect** agent (`.github/agents/architect.agent.md`).
- The Architect will assign work to the right agents and coordinate parallel execution.
- **Nothing is considered done until the Code Reviewer has approved it.**
- The **Technical Writer** documents every approved feature before the session closes.
- The **Agent Activity Logger** writes a session log to `.github/agent-logs/` at the end of every session for human review, audit, and retrospective.
- Reusable prompts under `.github/prompts/` can be used by individual agents for scoped tasks.

### Agent Logs

All team activity is recorded under `.github/agent-logs/`:
- `INDEX.md` — cumulative ledger of all sessions with links to detailed logs
- `YYYY-MM-DD/NNN_HHMM_<description>.md` — per-session structured logs grouped into per-day folders, numbered sequentially within each day (e.g. `2026-02-17/001_1430_task-feature.md`)

### Context Window Management

All agents follow `.github/instructions/context-window-management.instructions.md`.

- **Every agent self-monitors context load** throughout their session.
- **At ~80% context capacity**, the agent stops work, writes a checkpoint file to `.github/agent-logs/checkpoints/`, and tells the user how to resume in a new session.
- **At every session start**, the Architect checks `.github/agent-logs/checkpoints/` for active checkpoints before producing any new plan.
- **Resuming**: Tell any agent "Resume from checkpoint: `<path>`" and it will read the checkpoint and continue from where the prior session left off.
- The reusable prompt `.github/prompts/checkpoint.prompt.md` guides any agent through creating a checkpoint correctly.

Checkpoint files are named: `YYYY-MM-DD_HHMM_<agent-name>_<task>.checkpoint.md`  
They are deleted by the Agent Logger when the covered task is fully complete.
