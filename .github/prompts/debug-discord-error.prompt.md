---
mode: agent
description: Debug a Discord bot error or unexpected behavior with structured analysis
---

Help me debug the following Discord bot issue. Provide a structured diagnosis and fix.

**Describe the problem:**
[Paste the error message, traceback, or describe the unexpected behavior]

**Relevant code:**
[Paste the code that is causing the issue]

**What you expected to happen:**
[Describe expected behavior]

---

## Debug Protocol

Work through these layers in order:

### Layer 1 — Error Classification
Identify which category the error belongs to:
- **Gateway error**: WebSocket disconnects, heartbeat failures, invalid session
- **REST API error**: HTTP 4xx/5xx responses (rate limits, bad requests, forbidden)
- **Permissions error**: Missing bot permissions in guild or channel
- **Intents error**: Required intent not enabled in Developer Portal or bot configuration
- **Interaction error**: `defer()`/`followup` misuse, interaction already acknowledged, 3-second timeout
- **Logic/runtime error**: Python exceptions in handler code (AttributeError, KeyError, TypeError)

### Layer 2 — Root Cause Analysis
- Quote the exact line(s) responsible for the error
- Explain **why** it fails, not just **what** fails
- Identify any false assumptions in the original code

### Layer 3 — Fix
- Provide the corrected code with a clear `# FIX:` comment marking the change
- Preserve original code structure; change only what is necessary
- Ensure the fix handles the error path and the happy path

### Layer 4 — Prevention
- Add a `pytest-asyncio` regression test that would have caught this bug
- Suggest any defensive patterns (type narrowing, early return, `isinstance` guards) to prevent recurrence

### Layer 5 — Related Issues to Watch
- List 1–3 related pitfalls that are commonly triggered alongside this error

---

## Common Discord.py Pitfalls Reference

| Symptom | Likely Cause |
|---|---|
| `InteractionResponded` | `response.send_message()` called twice — use `followup.send()` after `defer()` |
| `NotFound` on interaction | Interaction token expired (> 15 min) or response already sent |
| `Forbidden` | Bot lacks permissions in channel; check `bot.guilds` and channel overwrites |
| `Missing Access` | `GUILD_MEMBERS` or `MESSAGE_CONTENT` intent not enabled |
| Commands not showing | `tree.sync()` not called after adding commands; wait up to 1 hour for global sync |
| Cog commands missing | `await bot.add_cog()` not called or extension not listed in `EXTENSIONS` |
| `RuntimeError: Event loop closed` | Sync code calling async without proper event loop management |
