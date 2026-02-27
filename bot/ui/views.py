"""Discord UI Views and Modals for the task bot.

Contains interactive UI components:
- :class:`TaskCreateModal` — modal form for creating a new task.
- :class:`TaskEditModal` — modal form for editing an existing task.
- :class:`TaskDetailView` — button panel shown below a task detail embed.
- :class:`TaskListView` — pagination controls for the task list.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord import ui

from bot.config import settings
from bot.models import (
    Task,
    TaskCreateRequest,
    TaskPriority,
    TaskStatus,
    TaskUpdateRequest,
)
from bot.ui.embeds import (
    error_embed,
    success_embed,
    task_detail_embed,
    task_list_embed,
)

if TYPE_CHECKING:
    from bot.database import Database

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DT_FORMATS = [
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M",
    "%d/%m/%Y %H:%M",
    "%d-%m-%Y %H:%M",
    "%Y-%m-%d",
]

# Presets shown in the quick-date select menu.
# Value format:  "<offset_hours>h" | "today_<HH>" | "tomorrow_<HH>" | "<days>d"
_DATE_PRESETS: list[tuple[str, str, str]] = [
    ("⏰", "In 1 hour",          "1h"),
    ("⏰", "In 2 hours",         "2h"),
    ("⏰", "In 4 hours",         "4h"),
    ("📅", "Today at 5:00 PM",   "today_17"),
    ("📅", "Tomorrow at 9:00 AM","tomorrow_09"),
    ("📅", "Tomorrow at 5:00 PM","tomorrow_17"),
    ("📅", "In 1 week",          "7d"),
    ("✏️", "Custom date/time…",  "custom"),
]


def _resolve_preset(value: str) -> datetime:
    """Convert a preset select value to a UTC-naive :class:`datetime`.

    Args:
        value: One of the preset strings from :data:`_DATE_PRESETS`.

    Returns:
        A naive datetime representing the resolved UTC time.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    if value.endswith("h"):
        return now + timedelta(hours=int(value[:-1]))
    if value.endswith("d"):
        return now + timedelta(days=int(value[:-1]))
    if value.startswith("today_"):
        hour = int(value.split("_")[1])
        return now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if value.startswith("tomorrow_"):
        hour = int(value.split("_")[1])
        return (now + timedelta(days=1)).replace(
            hour=hour, minute=0, second=0, microsecond=0
        )
    raise ValueError(f"Unknown preset: {value}")


def _local_to_utc(dt: datetime) -> datetime:
    """Convert a naive datetime in ``bot_timezone`` to a naive UTC datetime.

    If the configured timezone is invalid, falls back to treating the
    input as UTC and logs a warning.

    Args:
        dt: A naive datetime in the bot's configured local timezone.

    Returns:
        A naive datetime in UTC.
    """
    try:
        tz = ZoneInfo(settings.bot_timezone)
    except (ZoneInfoNotFoundError, KeyError):
        logger.warning(
            "Unknown BOT_TIMEZONE %r — treating input as UTC.",
            settings.bot_timezone,
        )
        return dt
    aware_local = dt.replace(tzinfo=tz)
    return aware_local.astimezone(UTC).replace(tzinfo=None)


def _parse_dt(value: str) -> datetime | None:
    """Try to parse a user-supplied datetime string.

    Supports ``YYYY-MM-DD HH:MM`` and common shorthand:
    ``today HH:MM``, ``tomorrow HH:MM``, ``in Xh``, ``in Xd``.

    Args:
        value: Raw string from the user.

    Returns:
        A naive :class:`datetime` (treated as UTC), or ``None`` if empty.

    Raises:
        ValueError: If the string cannot be parsed.
    """
    value = value.strip()
    if not value:
        return None

    now = datetime.now(UTC).replace(tzinfo=None)
    lower = value.lower()

    # Relative shorthands — relative to now in UTC
    if lower.startswith("in "):
        rest = lower[3:].strip()
        try:
            if rest.endswith("h"):
                return datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=float(rest[:-1]))
            if rest.endswith("d"):
                return datetime.now(UTC).replace(tzinfo=None) + timedelta(days=float(rest[:-1]))
        except ValueError:
            pass

    # today / tomorrow — interpret entered time as local, convert to UTC
    for prefix, delta_days in (("today ", 0), ("tomorrow ", 1)):
        if lower.startswith(prefix):
            time_part = value[len(prefix):].strip()
            for fmt in ("%H:%M", "%I:%M %p", "%I%p"):
                try:
                    t = datetime.strptime(time_part, fmt)
                    local_now = datetime.now(ZoneInfo(settings.bot_timezone)).replace(tzinfo=None)
                    base = (local_now + timedelta(days=delta_days)).replace(
                        hour=t.hour, minute=t.minute, second=0, microsecond=0
                    )
                    return _local_to_utc(base)
                except (ValueError, ZoneInfoNotFoundError):
                    continue
            raise ValueError(
                f"Could not parse time '{time_part}'. Use HH:MM (e.g. 09:00)."
            )

    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(
        f"Could not parse '{value}'. "
        "Try: YYYY-MM-DD HH:MM · today 09:00 · tomorrow 17:00 · in 2h"
    )


# ---------------------------------------------------------------------------
# Modals
# ---------------------------------------------------------------------------

class TaskCreateModal(ui.Modal, title="Create New Task"):
    """Modal form that collects all fields required to create a task.

    After submission the bot inserts the task into the database and
    replies with a detail embed + action buttons.
    """

    task_title: ui.TextInput = ui.TextInput(
        label="Title",
        placeholder="Enter a short task title…",
        min_length=1,
        max_length=200,
    )
    task_description: ui.TextInput = ui.TextInput(
        label="Description (optional)",
        style=discord.TextStyle.paragraph,
        placeholder="Add more detail about the task…",
        required=False,
        max_length=1000,
    )
    task_priority: ui.TextInput = ui.TextInput(
        label="Priority (low / medium / high)",
        placeholder="medium",
        default="medium",
        max_length=10,
    )
    task_due: ui.TextInput = ui.TextInput(
        label="Due date (optional) — YYYY-MM-DD HH:MM",
        placeholder="e.g. 2026-03-15 09:00",
        required=False,
        max_length=20,
    )
    task_reminder: ui.TextInput = ui.TextInput(
        label="Reminder (optional) — YYYY-MM-DD HH:MM",
        placeholder="e.g. 2026-03-14 09:00",
        required=False,
        max_length=20,
    )

    def __init__(self, db: "Database") -> None:
        super().__init__()
        self._db = db

    # discord.py stubs (discord-stubs) declare Modal.on_submit with 0
    # parameters; the runtime signature and official docs require
    # (self, interaction: discord.Interaction). This is a known stubs gap:
    # https://github.com/discord/discord.py/issues/9426
    # The type: ignore[override] silences the false-positive Pylance error.
    async def on_submit(  # type: ignore[override]
        self, interaction: discord.Interaction
    ) -> None:
        """Handle task creation modal submission."""
        await interaction.response.defer(ephemeral=True)

        # Validate priority
        raw_priority = self.task_priority.value.strip().lower()
        try:
            priority = TaskPriority(raw_priority)
        except ValueError:
            await interaction.followup.send(
                embed=error_embed(
                    "Priority must be **low**, **medium**, or **high**."
                ),
                ephemeral=True,
            )
            return

        # Parse dates
        try:
            due_at = _parse_dt(self.task_due.value)
            reminder_at = _parse_dt(self.task_reminder.value)
        except ValueError as exc:
            await interaction.followup.send(
                embed=error_embed(str(exc)), ephemeral=True
            )
            return

        req = TaskCreateRequest(
            user_id=interaction.user.id,
            guild_id=interaction.guild_id or 0,
            channel_id=interaction.channel_id or 0,
            title=self.task_title.value,
            description=self.task_description.value or "",
            priority=priority,
            due_at=due_at,
            reminder_at=reminder_at,
        )

        try:
            task = await self._db.create_task(req)
        except (OSError, RuntimeError, ValueError) as exc:
            logger.exception("Failed to create task: %s", exc)
            await interaction.followup.send(
                embed=error_embed("Failed to save the task. Please try again."),
                ephemeral=True,
            )
            return

        view = TaskDetailView(task=task, db=self._db)
        await interaction.followup.send(
            embed=task_detail_embed(task),
            view=view,
            ephemeral=True,
        )


class TaskEditModal(ui.Modal, title="Edit Task"):
    """Pre-filled modal for editing an existing task's core fields."""

    task_title: ui.TextInput = ui.TextInput(
        label="Title",
        min_length=1,
        max_length=200,
    )
    task_description: ui.TextInput = ui.TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000,
    )
    task_priority: ui.TextInput = ui.TextInput(
        label="Priority (low / medium / high)",
        max_length=10,
    )
    task_due: ui.TextInput = ui.TextInput(
        label="Due date (YYYY-MM-DD HH:MM, blank=clear)",
        placeholder="e.g. 2026-03-15 09:00  ·  tomorrow 17:00  ·  in 2h",
        required=False,
        max_length=30,
    )
    task_reminder: ui.TextInput = ui.TextInput(
        label="Reminder (YYYY-MM-DD HH:MM, blank=clear)",
        placeholder="e.g. 2026-03-14 09:00  ·  tomorrow 08:00  ·  in 1h",
        required=False,
        max_length=30,
    )

    def __init__(self, task: Task, db: "Database") -> None:
        super().__init__()
        self._task = task
        self._db = db
        # Pre-fill current values
        self.task_title.default = task.title
        self.task_description.default = task.description
        self.task_priority.default = task.priority.value
        if task.due_at:
            self.task_due.default = task.due_at.strftime("%Y-%m-%d %H:%M")
        if task.reminder_at:
            self.task_reminder.default = task.reminder_at.strftime(
                "%Y-%m-%d %H:%M"
            )

    # See TaskCreateModal.on_submit for the stubs gap rationale.
    # https://github.com/discord/discord.py/issues/9426
    async def on_submit(  # type: ignore[override]
        self, interaction: discord.Interaction
    ) -> None:
        """Handle task edit modal submission."""
        await interaction.response.defer(ephemeral=True)

        raw_priority = self.task_priority.value.strip().lower()
        try:
            priority = TaskPriority(raw_priority)
        except ValueError:
            await interaction.followup.send(
                embed=error_embed(
                    "Priority must be **low**, **medium**, or **high**."
                ),
                ephemeral=True,
            )
            return

        try:
            due_at = _parse_dt(self.task_due.value)
            reminder_at = _parse_dt(self.task_reminder.value)
        except ValueError as exc:
            await interaction.followup.send(
                embed=error_embed(str(exc)), ephemeral=True
            )
            return

        req = TaskUpdateRequest(
            title=self.task_title.value,
            description=self.task_description.value or "",
            priority=priority,
            due_at=due_at,
            reminder_at=reminder_at,
            clear_due=(not self.task_due.value.strip()),
            clear_reminder=(not self.task_reminder.value.strip()),
        )

        try:
            updated = await self._db.update_task(self._task.id, req)
        except (OSError, RuntimeError, ValueError) as exc:
            logger.exception("Failed to update task %s: %s", self._task.id, exc)
            await interaction.followup.send(
                embed=error_embed("Failed to update the task. Please try again."),
                ephemeral=True,
            )
            return

        if updated is None:
            await interaction.followup.send(
                embed=error_embed("Task not found."), ephemeral=True
            )
            return

        view = TaskDetailView(task=updated, db=self._db)
        await interaction.followup.send(
            content="Task updated!",
            embed=task_detail_embed(updated),
            view=view,
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# Quick date picker
# ---------------------------------------------------------------------------


class _CustomDateModal(ui.Modal, title="Set Custom Date/Time"):
    """Fallback single-field modal for power-user date entry."""

    date_input: ui.TextInput = ui.TextInput(
        label="Date & Time",
        placeholder="2026-03-15 09:00  ·  tomorrow 17:00  ·  in 2h",
        max_length=30,
    )

    def __init__(
        self,
        task: Task,
        db: "Database",
        field: "Literal['due_at', 'reminder_at']",
    ) -> None:
        super().__init__()
        self._task = task
        self._db = db
        self._field = field
        self.title = "Set Due Date" if field == "due_at" else "Set Reminder"

    async def on_submit(  # type: ignore[override]
        self, interaction: discord.Interaction
    ) -> None:
        """Parse the free-text entry and save."""
        await interaction.response.defer(ephemeral=True)
        try:
            dt = _parse_dt(self.date_input.value)
        except ValueError as exc:
            await interaction.followup.send(
                embed=error_embed(str(exc)), ephemeral=True
            )
            return
        if self._field == "due_at":
            req = TaskUpdateRequest(due_at=dt, clear_due=(dt is None))
        else:
            req = TaskUpdateRequest(reminder_at=dt, clear_reminder=(dt is None))
        updated = await self._db.update_task(self._task.id, req)
        if updated is None:
            await interaction.followup.send(
                embed=error_embed("Task not found."), ephemeral=True
            )
            return
        label = "Due date" if self._field == "due_at" else "Reminder"
        view = TaskDetailView(task=updated, db=self._db)
        await interaction.followup.send(
            content=f"✅ {label} updated!",
            embed=task_detail_embed(updated),
            view=view,
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# Day / Hour / AM-PM / Minute select components used by DatePickerView
# ---------------------------------------------------------------------------

class _DaySelect(ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(label="Today",      value="today",  emoji="📅"),
            discord.SelectOption(label="Tomorrow",   value="tomorrow", emoji="📅"),
            discord.SelectOption(label="In 2 days",  value="2d",    emoji="📅"),
            discord.SelectOption(label="In 3 days",  value="3d",    emoji="📅"),
            discord.SelectOption(label="In 1 week",  value="7d",    emoji="📅"),
            discord.SelectOption(label="In 2 weeks", value="14d",   emoji="📅"),
            discord.SelectOption(label="In 1 month", value="30d",   emoji="📅"),
            discord.SelectOption(label="Custom…",    value="custom", emoji="✏️"),
        ]
        super().__init__(placeholder="📅 Day…", options=options, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: DatePickerView = self.view  # type: ignore[assignment]
        if self.values[0] == "custom":
            await interaction.response.send_modal(
                _CustomDateModal(task=view._task, db=view._db, field=view._field)
            )
            return
        view._day = self.values[0]
        view._refresh_confirm()
        await interaction.response.edit_message(
            content=view._summary(), view=view
        )


class _HourSelect(ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(label=str(h), value=str(h))
            for h in range(1, 13)
        ]
        super().__init__(placeholder="🕐 Hour…", options=options, row=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: DatePickerView = self.view  # type: ignore[assignment]
        view._hour = int(self.values[0])
        view._refresh_confirm()
        await interaction.response.edit_message(
            content=view._summary(), view=view
        )


class _AmPmSelect(ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(label="AM", value="am", emoji="🌅"),
            discord.SelectOption(label="PM", value="pm", emoji="🌆"),
        ]
        super().__init__(placeholder="AM / PM", options=options, row=2)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: DatePickerView = self.view  # type: ignore[assignment]
        view._ampm = self.values[0]
        view._refresh_confirm()
        await interaction.response.edit_message(
            content=view._summary(), view=view
        )


class _MinuteSelect(ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(label=":00", value="0"),
            discord.SelectOption(label=":15", value="15"),
            discord.SelectOption(label=":30", value="30"),
            discord.SelectOption(label=":45", value="45"),
        ]
        super().__init__(
            placeholder="🕐 Minutes (default :00)…", options=options, row=3
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: DatePickerView = self.view  # type: ignore[assignment]
        view._minute = int(self.values[0])
        view._refresh_confirm()
        await interaction.response.edit_message(
            content=view._summary(), view=view
        )


class DatePickerView(ui.View):
    """Structured date/time picker using four dropdowns + a confirm button.

    Row 0 — Day (Today / Tomorrow / In X days / Custom…)
    Row 1 — Hour (1–12)
    Row 2 — AM / PM
    Row 3 — Minutes (:00 / :15 / :30 / :45)
    Row 4 — ✅ Confirm  |  ✖ Cancel
    """

    def __init__(
        self,
        task: Task,
        db: "Database",
        field: "Literal['due_at', 'reminder_at']",
    ) -> None:
        super().__init__(timeout=120)
        self._task = task
        self._db = db
        self._field = field
        self._day: str | None = None
        self._hour: int | None = None
        self._ampm: str | None = None
        self._minute: int = 0
        self.add_item(_DaySelect())
        self.add_item(_HourSelect())
        self.add_item(_AmPmSelect())
        self.add_item(_MinuteSelect())
        # Confirm button is added last so _refresh_confirm can find it
        self._confirm_btn: ui.Button = ui.Button(
            label="✅ Confirm",
            style=discord.ButtonStyle.success,
            row=4,
            disabled=True,
        )
        self._confirm_btn.callback = self._confirm_callback
        self._cancel_btn: ui.Button = ui.Button(
            label="✖ Cancel",
            style=discord.ButtonStyle.secondary,
            row=4,
        )
        self._cancel_btn.callback = self._cancel_callback
        self.add_item(self._confirm_btn)
        self.add_item(self._cancel_btn)

    # ------------------------------------------------------------------

    def _summary(self) -> str:
        """Build the picker status line shown above the dropdowns."""
        label = "📅 **Set due date**" if self._field == "due_at" else "🔔 **Set reminder**"
        parts: list[str] = []
        if self._day:
            day_label = {
                "today": "Today", "tomorrow": "Tomorrow",
                "2d": "In 2 days", "3d": "In 3 days", "7d": "In 1 week",
                "14d": "In 2 weeks", "30d": "In 1 month",
            }.get(self._day, self._day)
            parts.append(day_label)
        else:
            parts.append("*day?*")
        if self._hour and self._ampm:
            parts.append(f"{self._hour}:{self._minute:02d} {self._ampm.upper()}")
        elif self._hour:
            parts.append(f"{self._hour}:{self._minute:02d} *AM/PM?*")
        else:
            parts.append("*time?*")
        return (
            f"{label} — {' · '.join(parts)}\n"
            "Select all dropdowns then press **Confirm**."
        )

    def _refresh_confirm(self) -> None:
        """Enable the confirm button only when day + hour + am/pm are set."""
        self._confirm_btn.disabled = not (
            self._day and self._hour is not None and self._ampm
        )

    def _resolve_dt(self) -> datetime:
        """Build the final UTC-naive :class:`datetime` from current selections.

        The user's 12-hour selection is treated as ``bot_timezone`` local
        time and converted to UTC before storage.
        """
        try:
            tz = ZoneInfo(settings.bot_timezone)
        except (ZoneInfoNotFoundError, KeyError):
            tz = UTC  # type: ignore[assignment]
        now_local = datetime.now(tz).replace(tzinfo=None)
        if self._day == "today":
            base = now_local
        elif self._day == "tomorrow":
            base = now_local + timedelta(days=1)
        else:
            base = now_local + timedelta(days=int(str(self._day).rstrip("d")))

        hour_12 = self._hour or 12
        hour_24 = hour_12 % 12 + (12 if self._ampm == "pm" else 0)
        local_dt = base.replace(hour=hour_24, minute=self._minute, second=0, microsecond=0)
        return _local_to_utc(local_dt)

    # ------------------------------------------------------------------
    # Confirm / Cancel button callbacks
    # ------------------------------------------------------------------

    async def _confirm_callback(self, interaction: discord.Interaction) -> None:
        """Save the selected date/time to the task."""
        if interaction.user.id != self._task.user_id:
            await interaction.response.send_message(
                embed=error_embed("You don't have permission to modify this task."),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        dt = self._resolve_dt()
        if self._field == "due_at":
            req = TaskUpdateRequest(due_at=dt)
        else:
            req = TaskUpdateRequest(reminder_at=dt)
        updated = await self._db.update_task(self._task.id, req)
        if updated is None:
            await interaction.followup.send(
                embed=error_embed("Task not found."), ephemeral=True
            )
            return
        label = "Due date" if self._field == "due_at" else "Reminder"
        detail_view = TaskDetailView(task=updated, db=self._db)
        await interaction.followup.send(
            content=f"✅ {label} set!",
            embed=task_detail_embed(updated),
            view=detail_view,
            ephemeral=True,
        )
        self.stop()

    async def _cancel_callback(self, interaction: discord.Interaction) -> None:
        """Dismiss the picker without saving."""
        await interaction.response.edit_message(content="Cancelled.", view=None)
        self.stop()


# ---------------------------------------------------------------------------
# Status selector
# ---------------------------------------------------------------------------

class StatusSelect(ui.Select):
    """Drop-down to change a task's status."""

    def __init__(self, task: Task, db: "Database") -> None:
        self._task = task
        self._db = db
        options = [
            discord.SelectOption(
                label=s.value.replace("_", " ").title(),
                value=s.value,
                default=(s == task.status),
                emoji={
                    TaskStatus.PENDING: "⏳",
                    TaskStatus.IN_PROGRESS: "🔄",
                    TaskStatus.DONE: "✅",
                    TaskStatus.CANCELLED: "❌",
                }.get(s),
            )
            for s in TaskStatus
        ]
        super().__init__(
            placeholder="Change status…",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle status selection and update the task in the database."""
        user_id = interaction.user.id
        if user_id != self._task.user_id and user_id != self._task.assigned_to_id:
            await interaction.response.send_message(
                embed=error_embed("You don't have permission to modify this task."),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        new_status = TaskStatus(self.values[0])
        req = TaskUpdateRequest(status=new_status)
        updated = await self._db.update_task(self._task.id, req)
        if updated is None:
            await interaction.followup.send(
                embed=error_embed("Task not found."), ephemeral=True
            )
            return
        view = TaskDetailView(task=updated, db=self._db)
        await interaction.followup.send(
            embed=task_detail_embed(updated), view=view, ephemeral=True
        )


# ---------------------------------------------------------------------------
# Task detail buttons
# ---------------------------------------------------------------------------

class TaskDetailView(ui.View):
    """Button row shown below a task detail embed.

    Provides quick actions: Edit, Mark Done, Delete.
    """

    def __init__(self, task: Task, db: "Database") -> None:
        super().__init__(timeout=300)
        self._task = task
        self._db = db
        # Add the status selector
        self.add_item(StatusSelect(task=task, db=db))

    async def on_timeout(self) -> None:
        """Disable all components when the view expires."""
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True

    @ui.button(label="📅 Due Date", style=discord.ButtonStyle.secondary, row=1)
    async def due_date_button(
        self, interaction: discord.Interaction, _button: ui.Button
    ) -> None:
        """Open the quick due-date picker."""
        if interaction.user.id != self._task.user_id:
            await interaction.response.send_message(
                embed=error_embed("You don't have permission to modify this task."),
                ephemeral=True,
            )
            return
        picker = DatePickerView(task=self._task, db=self._db, field="due_at")
        await interaction.response.send_message(
            content=picker._summary(),
            view=picker,
            ephemeral=True,
        )

    @ui.button(label="🔔 Reminder", style=discord.ButtonStyle.secondary, row=1)
    async def reminder_button(
        self, interaction: discord.Interaction, _button: ui.Button
    ) -> None:
        """Open the quick reminder picker."""
        if interaction.user.id != self._task.user_id:
            await interaction.response.send_message(
                embed=error_embed("You don't have permission to modify this task."),
                ephemeral=True,
            )
            return
        picker = DatePickerView(task=self._task, db=self._db, field="reminder_at")
        await interaction.response.send_message(
            content=picker._summary(),
            view=picker,
            ephemeral=True,
        )

    @ui.button(label="✏️ Edit", style=discord.ButtonStyle.primary, row=0)
    async def edit_button(
        self, interaction: discord.Interaction, _button: ui.Button
    ) -> None:
        """Open the edit modal for this task."""
        if interaction.user.id != self._task.user_id:
            await interaction.response.send_message(
                embed=error_embed("You don't have permission to modify this task."),
                ephemeral=True,
            )
            return
        modal = TaskEditModal(task=self._task, db=self._db)
        await interaction.response.send_modal(modal)

    @ui.button(label="✅ Mark Done", style=discord.ButtonStyle.success, row=0)
    async def done_button(
        self, interaction: discord.Interaction, _button: ui.Button
    ) -> None:
        """Mark this task as done instantly."""
        user_id = interaction.user.id
        if user_id != self._task.user_id and user_id != self._task.assigned_to_id:
            await interaction.response.send_message(
                embed=error_embed("You don't have permission to modify this task."),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        req = TaskUpdateRequest(status=TaskStatus.DONE)
        updated = await self._db.update_task(self._task.id, req)
        if updated is None:
            await interaction.followup.send(
                embed=error_embed("Task not found."), ephemeral=True
            )
            return
        view = TaskDetailView(task=updated, db=self._db)
        await interaction.followup.send(
            embed=task_detail_embed(updated), view=view, ephemeral=True
        )

    @ui.button(label="🗑️ Delete", style=discord.ButtonStyle.danger, row=0)
    async def delete_button(
        self, interaction: discord.Interaction, _button: ui.Button
    ) -> None:
        """Show a confirmation prompt before deleting."""
        if interaction.user.id != self._task.user_id:
            await interaction.response.send_message(
                embed=error_embed("You don't have permission to delete this task."),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚠️ Confirm Deletion",
                description=(
                    f"Are you sure you want to delete task "
                    f"**#{self._task.id} — {self._task.title}**?\n"
                    "This action **cannot** be undone."
                ),
                colour=discord.Colour.orange(),
            ),
            view=ConfirmDeleteView(task_id=self._task.id, db=self._db),
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# Confirm-delete view
# ---------------------------------------------------------------------------

class ConfirmDeleteView(ui.View):
    """Two-button confirmation prompt before deleting a task."""

    def __init__(self, task_id: int, db: "Database") -> None:
        super().__init__(timeout=60)
        self._task_id = task_id
        self._db = db

    async def on_timeout(self) -> None:
        """Disable confirm/cancel buttons when the prompt expires."""
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True

    @ui.button(label="Yes, delete it", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, _button: ui.Button
    ) -> None:
        """Execute the deletion."""
        await interaction.response.defer(ephemeral=True)
        deleted = await self._db.delete_task(self._task_id)
        if deleted:
            await interaction.followup.send(
                embed=success_embed(
                    f"Task **#{self._task_id}** has been deleted."
                ),
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                embed=error_embed("Task not found or already deleted."),
                ephemeral=True,
            )
        self.stop()

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, _button: ui.Button
    ) -> None:
        """Dismiss the confirmation prompt."""
        await interaction.response.send_message(
            "Deletion cancelled.", ephemeral=True
        )
        self.stop()


# ---------------------------------------------------------------------------
# Task list pagination
# ---------------------------------------------------------------------------

class TaskListView(ui.View):
    """Pagination controls for the /task list command.

    Maintains the current page state and re-fetches from the DB on each
    button press.
    """

    PAGE_SIZE = 10

    def __init__(
        self,
        *,
        db: "Database",
        user: discord.User | discord.Member,
        guild_id: int,
        status_filter: TaskStatus | None,
        total_tasks: int,
        page: int = 1,
    ) -> None:
        super().__init__(timeout=300)
        self._db = db
        self._user = user
        self._guild_id = guild_id
        self._status_filter = status_filter
        self._total_tasks = total_tasks
        self._page = page
        self._total_pages = max(1, -(-total_tasks // self.PAGE_SIZE))  # ceil div
        self._update_buttons()

    async def on_timeout(self) -> None:
        """Disable pagination buttons when the view expires."""
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True

    def _update_buttons(self) -> None:
        """Enable/disable navigation buttons based on the current page."""
        self.prev_button.disabled = self._page <= 1
        self.next_button.disabled = self._page >= self._total_pages

    async def _render_page(
        self, interaction: discord.Interaction
    ) -> None:
        """Fetch the current page from the DB and edit the message."""
        tasks = await self._db.get_tasks_for_user(
            self._user.id,
            self._guild_id,
            status=self._status_filter,
            limit=self.PAGE_SIZE,
            offset=(self._page - 1) * self.PAGE_SIZE,
        )
        embed = task_list_embed(
            tasks,
            user=self._user,
            page=self._page,
            total_pages=self._total_pages,
            total_tasks=self._total_tasks,
            status_filter=self._status_filter,
        )
        self._update_buttons()
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_button(
        self, interaction: discord.Interaction, _button: ui.Button
    ) -> None:
        """Go to the previous page."""
        if self._page > 1:
            self._page -= 1
        await self._render_page(interaction)

    @ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_button(
        self, interaction: discord.Interaction, _button: ui.Button
    ) -> None:
        """Go to the next page."""
        if self._page < self._total_pages:
            self._page += 1
        await self._render_page(interaction)
