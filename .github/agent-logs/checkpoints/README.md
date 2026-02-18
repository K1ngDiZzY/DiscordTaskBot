# Agent Checkpoints

This directory holds mid-session checkpoint files created when an agent's context window reaches ~80% capacity.

## Purpose

When an agent cannot complete a task in a single session without risking quality degradation, it creates a checkpoint here. The checkpoint captures:

- What was being done
- What has been completed
- What remains (ordered, actionable list)
- Key decisions already made
- Context a new agent needs to resume cleanly

## File Naming

```
YYYY-MM-DD_HHMM_<agent-name>_<task-slug>.checkpoint.md
```

**Examples:**
- `2026-02-17_1430_python-dev_task-repository.checkpoint.md`
- `2026-02-17_1615_code-reviewer_reminders-cog.checkpoint.md`
- `2026-02-17_1745_tech-writer_commands-docs.checkpoint.md`

## Lifecycle

1. **Created** — by the agent when context load reaches ~80%.
2. **Resumed** — tell the agent in a new session: *"Resume from checkpoint: `.github/agent-logs/checkpoints/<filename>.checkpoint.md`"*
3. **Deleted** — by the Agent Logger once the covered task is fully complete and logged.

## Active Checkpoints

Any `.checkpoint.md` file in this directory represents an incomplete task that needs to be resumed.
If this directory is empty (other than this README), all tasks have been completed.
