"""Discord embed builders for task display.

All public functions return fully-formed :class:`discord.Embed` objects
ready to be passed to Discord API calls.
"""

from __future__ import annotations

from datetime import UTC, datetime

import discord

from bot.models import Task, TaskPriority, TaskStatus

# Colour palette keyed by task status
_STATUS_COLOUR: dict[TaskStatus, discord.Colour] = {
    TaskStatus.PENDING: discord.Colour.blurple(),
    TaskStatus.IN_PROGRESS: discord.Colour.yellow(),
    TaskStatus.DONE: discord.Colour.green(),
    TaskStatus.CANCELLED: discord.Colour.red(),
}

_PRIORITY_LABEL: dict[TaskPriority, str] = {
    TaskPriority.LOW: "Low 🟢",
    TaskPriority.MEDIUM: "Medium 🟡",
    TaskPriority.HIGH: "High 🔴",
}


def _fmt_dt(dt: datetime | None) -> str:
    """Format a datetime for display, or 'Not set' if None.

    Datetimes are stored as naive UTC throughout the codebase.
    UTC is re-attached here so :func:`datetime.timestamp` produces
    the correct Unix epoch regardless of the host's local timezone.
    Discord renders ``<t:unix:F>`` in each viewer's own local timezone.
    """
    if dt is None:
        return "Not set"
    aware = dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    ts = int(aware.timestamp())
    return f"<t:{ts}:F> (<t:{ts}:R>)"


def task_detail_embed(task: Task) -> discord.Embed:
    """Build a rich embed showing all details for a single task.

    Args:
        task: The task to display.

    Returns:
        A fully-populated :class:`discord.Embed`.
    """
    colour = _STATUS_COLOUR.get(task.status, discord.Colour.greyple())
    overdue_marker = " ⚠️ OVERDUE" if task.is_overdue else ""

    embed = discord.Embed(
        title=f"{task.status_emoji} Task #{task.id} — {task.title}{overdue_marker}",
        description=task.description or "*No description provided.*",
        colour=colour,
        timestamp=task.updated_at,
    )

    embed.add_field(
        name="Status",
        value=f"{task.status_emoji} {task.status.value.replace('_', ' ').title()}",
        inline=True,
    )
    embed.add_field(
        name="Priority",
        value=_PRIORITY_LABEL.get(task.priority, task.priority.value),
        inline=True,
    )
    embed.add_field(
        name="Due Date",
        value=_fmt_dt(task.due_at),
        inline=False,
    )
    embed.add_field(
        name="Reminder",
        value=(
            f"{_fmt_dt(task.reminder_at)}"
            + (" ✅ sent" if task.reminder_sent else "")
        ),
        inline=False,
    )
    embed.add_field(
        name="Assigned To",
        value=(
            f"<@{task.assigned_to_id}>" if task.assigned_to_id else "*Unassigned*"
        ),
        inline=True,
    )
    embed.add_field(
        name="Created",
        value=_fmt_dt(task.created_at),
        inline=True,
    )
    embed.set_footer(text=f"Task ID: {task.id} • Last updated")
    return embed


def task_list_embed(
    tasks: list[Task],
    *,
    user: discord.User | discord.Member,
    page: int,
    total_pages: int,
    total_tasks: int,
    status_filter: TaskStatus | None = None,
) -> discord.Embed:
    """Build a paginated list embed for multiple tasks.

    Args:
        tasks: Tasks for the current page.
        user: The requesting Discord user (shown in the footer).
        page: Current 1-indexed page number.
        total_pages: Total number of pages.
        total_tasks: Grand total task count for this filter.
        status_filter: Optional status filter applied to the query.

    Returns:
        A formatted list embed.
    """
    filter_label = (
        f" — {status_filter.value.replace('_', ' ').title()}"
        if status_filter
        else ""
    )
    embed = discord.Embed(
        title=f"📋 Your Tasks{filter_label}",
        colour=discord.Colour.blurple(),
        timestamp=datetime.now(UTC),
    )

    if not tasks:
        embed.description = "*No tasks found. Use `/task add` to create one!*"
    else:
        lines: list[str] = []
        for task in tasks:
            overdue = " ⚠️" if task.is_overdue else ""
            due = (
                f" | Due <t:{int(task.due_at.replace(tzinfo=UTC).timestamp())}:d>"
                if task.due_at
                else ""
            )
            lines.append(
                f"{task.status_emoji} **#{task.id}** {task.priority_emoji} "
                f"**{task.title}**{due}{overdue}"
            )
        embed.description = "\n".join(lines)

    embed.set_footer(
        text=(
            f"Page {page}/{total_pages} • {total_tasks} task(s) total "
            f"• {user.display_name}"
        ),
        icon_url=user.display_avatar.url,
    )
    return embed


def reminder_embed(task: Task) -> discord.Embed:
    """Build a reminder notification embed.

    Args:
        task: The task whose reminder is firing.

    Returns:
        A highlighted reminder embed.
    """
    embed = discord.Embed(
        title=f"⏰ Reminder — {task.title}",
        description=(
            task.description
            or "*No description provided.*"
        ),
        colour=discord.Colour.orange(),
        timestamp=datetime.now(UTC),
    )
    embed.add_field(
        name="Priority",
        value=_PRIORITY_LABEL.get(task.priority, task.priority.value),
        inline=True,
    )
    embed.add_field(
        name="Due",
        value=_fmt_dt(task.due_at),
        inline=True,
    )
    embed.set_footer(text=f"Task #{task.id}")
    return embed


def task_assigned_embed(
    task: Task,
    *,
    assigner: discord.User | discord.Member,
) -> discord.Embed:
    """Build a notification embed sent to an assignee when a task is assigned.

    Args:
        task: The task that was assigned.
        assigner: The Discord member who performed the assignment.

    Returns:
        A styled embed for the assignment notification.
    """
    embed = discord.Embed(
        title=f"📬 You have been assigned a task — {task.title}",
        description=task.description or "*No description provided.*",
        colour=discord.Colour.blurple(),
        timestamp=datetime.now(UTC),
    )
    embed.add_field(
        name="Priority",
        value=_PRIORITY_LABEL.get(task.priority, task.priority.value),
        inline=True,
    )
    embed.add_field(
        name="Status",
        value=f"{task.status_emoji} {task.status.value.replace('_', ' ').title()}",
        inline=True,
    )
    embed.add_field(
        name="Due Date",
        value=_fmt_dt(task.due_at),
        inline=False,
    )
    embed.add_field(
        name="Assigned by",
        value=assigner.mention,
        inline=False,
    )
    embed.set_footer(text=f"Task #{task.id} • Use /task view {task.id} to see details")
    return embed


def success_embed(message: str, *, title: str = "Success") -> discord.Embed:
    """Build a simple success-state embed.

    Args:
        message: Body text to display.
        title: Embed title (default 'Success').

    Returns:
        A green-coloured embed.
    """
    return discord.Embed(
        title=f"✅ {title}",
        description=message,
        colour=discord.Colour.green(),
    )


def error_embed(message: str, *, title: str = "Error") -> discord.Embed:
    """Build a simple error-state embed.

    Args:
        message: Body text to display.
        title: Embed title (default 'Error').

    Returns:
        A red-coloured embed.
    """
    return discord.Embed(
        title=f"❌ {title}",
        description=message,
        colour=discord.Colour.red(),
    )
