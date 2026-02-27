"""Data models for the task management bot.

All models use Python dataclasses for lightweight, typed structured data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class TaskStatus(str, Enum):
    """Lifecycle states a task can be in."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    """Priority levels for tasks."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


PRIORITY_EMOJI: dict[TaskPriority, str] = {
    TaskPriority.LOW: "🟢",
    TaskPriority.MEDIUM: "🟡",
    TaskPriority.HIGH: "🔴",
}

STATUS_EMOJI: dict[TaskStatus, str] = {
    TaskStatus.PENDING: "⏳",
    TaskStatus.IN_PROGRESS: "🔄",
    TaskStatus.DONE: "✅",
    TaskStatus.CANCELLED: "❌",
}


@dataclass
class Task:
    """Represents a single user task stored in the database.

    Attributes:
        id: Auto-incremented primary key.
        user_id: Discord user snowflake who owns the task.
        guild_id: Discord guild where the task was created.
        title: Short title of the task.
        description: Optional longer description.
        status: Current lifecycle status.
        priority: Task priority level.
        due_at: Optional datetime when the task is due.
        reminder_at: Optional datetime when a reminder should fire.
        reminder_sent: Whether the reminder has already been dispatched.
        channel_id: Channel to send the reminder to (falls back to DM).
        created_at: When the task was created.
        updated_at: When the task was last modified.
    """

    id: int
    user_id: int
    guild_id: int
    title: str
    description: str
    status: TaskStatus
    priority: TaskPriority
    due_at: datetime | None
    reminder_at: datetime | None
    reminder_sent: bool
    channel_id: int | None
    assigned_to_id: int | None
    created_at: datetime
    updated_at: datetime

    @property
    def priority_emoji(self) -> str:
        """Return the emoji for this task's priority."""
        return PRIORITY_EMOJI.get(self.priority, "⚪")

    @property
    def status_emoji(self) -> str:
        """Return the emoji for this task's status."""
        return STATUS_EMOJI.get(self.status, "❓")

    @property
    def is_overdue(self) -> bool:
        """Return True if the task is past its due date and not finished."""
        if self.due_at is None:
            return False
        return (
            datetime.now(UTC) > self.due_at.replace(tzinfo=UTC)
            and self.status not in (TaskStatus.DONE, TaskStatus.CANCELLED)
        )


@dataclass
class TaskCreateRequest:
    """Validated data needed to create a new task.

    Attributes:
        user_id: Discord user snowflake.
        guild_id: Discord guild snowflake.
        channel_id: Discord channel snowflake for reminders.
        title: Task title (1-200 characters).
        description: Optional task description.
        priority: Priority level (default MEDIUM).
        due_at: Optional due datetime (UTC).
        reminder_at: Optional reminder datetime (UTC).
    """

    user_id: int
    guild_id: int
    channel_id: int
    title: str
    description: str = ""
    priority: TaskPriority = TaskPriority.MEDIUM
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    assigned_to_id: int | None = None


@dataclass
class TaskUpdateRequest:
    """Fields that may be updated on an existing task.

    Only non-None fields are applied to the database row.
    """

    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_at: datetime | None = field(default=None)
    reminder_at: datetime | None = field(default=None)
    clear_due: bool = False
    clear_reminder: bool = False
    assigned_to_id: int | None = None
    clear_assigned: bool = False
