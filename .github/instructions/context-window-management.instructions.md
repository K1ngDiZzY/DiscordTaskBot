# Context Window Management — All Agents

**Applies to**: All agents (Architect, Python Developer, Python Discord Developer, Code Reviewer, Technical Writer, Agent Activity Logger)

---

## Why This Rule Exists

Language model agents operate within a fixed context window. As a session grows — through file reads, code generation, back-and-forth exchanges, and tool output — the available context shrinks. When context approaches its limit, response quality degrades silently: agents begin to forget earlier decisions, miss details, or produce inconsistent output. This rule prevents that degradation by requiring every agent to self-monitor and checkpoint before quality is affected.

---

## Context Load Self-Assessment

Agents cannot read their token count directly, but they **must estimate** context load continuously using these heuristics:

| Signal | Weight |
|---|---|
| Large files read in full (>100 lines each) | High |
| Multiple full file reads in one session | High |
| Long multi-turn conversation (>15 exchanges) | High |
| Multiple large code blocks generated | Medium |
| Many tool results returned (grep, search, dir listings) | Medium |
| Accumulated agent plans and structured outputs | Medium |

### Estimation Levels

- **🟢 Low (< 50%)** — Full capacity. Proceed normally.
- **🟡 Medium (50–79%)** — Begin completing or pausing work at natural boundaries. Avoid starting large new sub-tasks.
- **🔴 High (≥ 80%)** — **STOP. Create a checkpoint immediately before continuing or ending the session.** Do not start additional work.

Err on the side of caution. If you are unsure whether you are at 80%, treat it as if you are.

---

## The 80% Rule — Mandatory Checkpoint Protocol

When you estimate you have reached **80% context load**, you **must**:

1. **Immediately stop the current work unit** at the nearest safe boundary (do not abandon mid-function or mid-plan).
2. **Create a checkpoint file** at `.github/agent-logs/checkpoints/YYYY-MM-DD_HHMM_<agent-name>_<short-task>.checkpoint.md` using the format below.
3. **Announce the checkpoint** to the user in your response:
   > ⚠️ **Context Window Checkpoint Created**
   > I have reached approximately 80% of my context window. To preserve quality, I have saved a checkpoint to `.github/agent-logs/checkpoints/<filename>.checkpoint.md`. Start a new session and open that file to resume exactly where we left off.
4. **Do not continue** with additional implementation, review, or documentation in the same session.

---

## Checkpoint File Format

**Path**: `.github/agent-logs/checkpoints/YYYY-MM-DD_HHMM_<agent-name>_<task>.checkpoint.md`

**Example**: `.github/agent-logs/checkpoints/2026-02-17_1430_python-dev_task-repository.checkpoint.md`

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
- [ already done item 3 ]

### Files Already Created or Modified

| File | Action | Notes |
|---|---|---|
| `path/to/file.py` | Created | Brief description of what it contains |
| `path/to/other.py` | Modified | What was changed and why |

---

## Work Remaining ⏳

Ordered list of everything that still needs to be done to complete the task. Include enough detail that a fresh agent can proceed without asking for clarification.

1. **Next immediate step** — exact description of what to do first, including which file, function, or section to work on.
2. **Following step** — what comes after, any dependencies between steps.
3. **Remaining steps** — continue the ordered list.

---

## Key Decisions Made

Record non-obvious choices so a resuming agent doesn't revisit settled decisions.

| Decision | Rationale |
|---|---|
| Used `aiosqlite` instead of `asyncpg` | SQLite is sufficient for single-server scope; avoids Postgres dependency |
| Named the method `get_by_user` not `fetch_user_tasks` | Aligns with existing repository naming convention |

---

## Important Context

Anything a resuming agent needs to know that is NOT in the code itself:

- Active architecture plan or feature brief (paste or summarize the key constraints)
- Reviewer feedback that has already been given
- Known issues or blockers encountered
- User preferences or constraints stated during the session

---

## How to Resume

Steps for the agent picking up this checkpoint in a new session:

1. Read this entire checkpoint file.
2. Read the files listed in "Files Already Created or Modified" to verify their current state.
3. Begin with item 1 from "Work Remaining."
4. When resuming is complete, delete or archive this checkpoint file and update the session log in `.github/agent-logs/`.

---

## Links to Related Logs

- Session log: `.github/agent-logs/YYYY-MM-DD/NNN_HHMM_<session>.md` (if one exists)
- Related checkpoint(s): (list any prior checkpoints from the same feature)
```

---

## Session Start — Checkpoint Check

**At the start of every session**, agents must:

1. Check whether `.github/agent-logs/checkpoints/` contains any `.checkpoint.md` files.
2. If a checkpoint exists for the relevant agent or task, **read it first** before doing anything else.
3. Report to the user: "I found an active checkpoint from a prior session. Resuming from there."
4. Begin from "Work Remaining" item 1 in that checkpoint.

The **Architect** must always check for active checkpoints at session start and surface them to the user before producing a new plan.

---

## Checkpoint Lifecycle

| State | File exists? | Status field |
|---|---|---|
| Active — needs resumption | Yes | `🔄 In Progress` |
| Resumed and complete | Should be deleted | — |
| Superseded by a newer checkpoint | Should be deleted | — |

When a task covered by a checkpoint is fully completed:
- The Agent Activity Logger **deletes the checkpoint file**.
- The Logger records the completion in the session log under `.github/agent-logs/`.

---

## Rules Summary

- **Every agent** follows this protocol — it is not optional.
- **80% = checkpoint now**, not "finish this one thing first" (you may complete the single current sentence/function, then checkpoint).
- **Checkpoint files are the source of truth** for mid-session state. They take priority over memory of what was discussed.
- **Never degrade silently.** A checkpoint is always better than producing poor-quality output with a full context.
- **The Architect surfaces checkpoints.** If the Architect finds active checkpoints at session start, the new plan must account for them.
