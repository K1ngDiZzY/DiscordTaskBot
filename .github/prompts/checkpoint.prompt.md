# Checkpoint: Save Session State

Use this prompt when you have reached ~80% context window capacity, or when you need to deliberately save progress mid-session so a fresh agent can resume cleanly.

---

## Instructions for the Agent Executing This Prompt

You are about to create a checkpoint file. Follow these steps exactly:

1. **Assess current work state** — mentally review everything accomplished in this session and everything still pending.
2. **Identify the correct checkpoint path**:
   - Directory: `.github/agent-logs/checkpoints/`
   - Filename: `YYYY-MM-DD_HHMM_<your-agent-name>_<task-slug>.checkpoint.md`
   - Example: `2026-02-17_1430_code-reviewer_reminders-cog.checkpoint.md`
3. **Write the checkpoint file** using the template below — fill in every section with accurate, specific detail.
4. **Announce to the user** that the checkpoint has been created and what to do next.

---

## Checkpoint Template

```markdown
# Checkpoint — <Agent Name>

**Date**: YYYY-MM-DD HH:MM  
**Agent**: <Agent Name>  
**Task**: <Short description of the task being performed>  
**Context Load at Checkpoint**: ~<estimated>%  
**Status**: 🔄 In Progress  

---

## What Was Being Done

Concise description of the goal of this session — what feature, bug fix, or task was being worked on and why.

---

## Work Completed ✅

List every concrete action already taken. Be specific enough that a new agent can verify completion without re-reading the full conversation.

- [ already done item 1 ]
- [ already done item 2 ]

### Files Already Created or Modified

| File | Action | Notes |
|---|---|---|
| `path/to/file.py` | Created | Brief description of what it contains |
| `path/to/other.py` | Modified | What was changed and why |

---

## Work Remaining ⏳

Ordered list of everything that still needs to be done to complete the task.

1. **Next immediate step** — exact description of what to do first.
2. **Following step** — what comes after, and any dependencies.
3. **Remaining steps** — continue the ordered list.

---

## Key Decisions Made

| Decision | Rationale |
|---|---|
| <decision> | <why it was made> |

---

## Important Context

Anything a resuming agent needs to know that is NOT in the code itself:

- Active architecture plan constraints
- Reviewer feedback already given
- Known issues or blockers
- User preferences or constraints

---

## How to Resume

1. Read this entire checkpoint file.
2. Read the files listed in "Files Already Created or Modified" to verify their current state.
3. Begin with item 1 from "Work Remaining."
4. When the task is complete, delete this checkpoint file and update the session log.

---

## Links to Related Logs

- Session log: `.github/agent-logs/YYYY-MM-DD/NNN_HHMM_<session>.md`
- Related checkpoint(s): (if any)
```

---

## After Writing the Checkpoint

Tell the user:

> ⚠️ **Context Window Checkpoint Created**
>
> I've saved my progress to `.github/agent-logs/checkpoints/<filename>.checkpoint.md`. My context window is near its limit and continuing would degrade quality.
>
> **To resume**: Start a new chat session, switch to the appropriate agent mode, and say:
> *"Resume from checkpoint: `.github/agent-logs/checkpoints/<filename>.checkpoint.md`"*
>
> The agent will read the checkpoint and pick up exactly where this session left off.

---

## Resuming from a Checkpoint

When a user says "resume from checkpoint" or a checkpoint file is found at session start:

1. Read the checkpoint file in full.
2. Confirm to the user: "I've read the checkpoint. Resuming task: `<task name>`. Starting from: `<Work Remaining item 1>`."
3. Execute the items in "Work Remaining" in order.
4. When all work is complete:
   - Delete the checkpoint file.
   - Ask the Agent Logger to finalize the session log.
