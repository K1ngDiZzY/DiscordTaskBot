"""Task creation and editing modals.

Classes
-------
:class:`TaskCreateModal`      — step-1 modal collecting title + description.
:class:`TaskCreateSetupView`  — step-2 view with priority dropdown + date picker.
:class:`TaskEditModal`        — pre-filled modal for editing an existing task.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord import ui

from bot.models import Task, TaskCreateRequest, TaskPriority, TaskUpdateRequest
from bot.ui.embeds import error_embed, task_detail_embed
from bot.ui.helpers import _local_to_utc

if TYPE_CHECKING:
    from bot.database import Database

logger = logging.getLogger(__name__)


class TaskCreateModal(ui.Modal, title="Create New Task"):
    """Step-1 modal that collects title and description.

    After submission the bot shows a :class:`TaskCreateSetupView` where
    the user selects priority and an optional due date before confirming.
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
        """Show the priority + due-date setup view after title/description."""
        setup_view = TaskCreateSetupView(
            title=self.task_title.value,
            description=self.task_description.value or "",
            db=self._db,
            user_id=interaction.user.id,
            guild_id=interaction.guild_id or 0,
            channel_id=interaction.channel_id or 0,
        )
        await interaction.response.send_message(
            content=setup_view.summary(),
            view=setup_view,
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# TaskCreateSetupView — step-2 priority + due-date picker
# ---------------------------------------------------------------------------


class _PrioritySelect(ui.Select):
    """Row-0 dropdown for choosing task priority."""

    def __init__(self) -> None:
        options = [
            discord.SelectOption(
                label="🔴 High",
                value="high",
                description="Urgent / top priority",
            ),
            discord.SelectOption(
                label="🟡 Medium",
                value="medium",
                description="Normal priority",
                default=True,
            ),
            discord.SelectOption(
                label="🟢 Low",
                value="low",
                description="Nice to have",
            ),
        ]
        super().__init__(placeholder="⚡ Priority…", options=options, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: TaskCreateSetupView = self.view  # type: ignore[assignment]
        view._priority = TaskPriority(self.values[0])
        await interaction.response.edit_message(content=view.summary(), view=view)


class _CreateDaySelect(ui.Select):
    """Row-1 dropdown for choosing the due date day."""

    def __init__(self) -> None:
        options = [
            discord.SelectOption(label="Today",      value="today",   emoji="📅"),
            discord.SelectOption(label="Tomorrow",   value="tomorrow", emoji="📅"),
            discord.SelectOption(label="In 2 days",  value="2d",      emoji="📅"),
            discord.SelectOption(label="In 3 days",  value="3d",      emoji="📅"),
            discord.SelectOption(label="In 1 week",  value="7d",      emoji="📅"),
            discord.SelectOption(label="In 2 weeks", value="14d",     emoji="📅"),
            discord.SelectOption(label="In 1 month", value="30d",     emoji="📅"),
        ]
        super().__init__(
            placeholder="📅 Due date (optional)…", options=options, row=1
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: TaskCreateSetupView = self.view  # type: ignore[assignment]
        view._day = self.values[0]
        await interaction.response.edit_message(content=view.summary(), view=view)


class _CreateTimeSelect(ui.Select):
    """Row-2 dropdown for choosing due-date time (hourly, 24 options)."""

    def __init__(self) -> None:
        options: list[discord.SelectOption] = []
        for h in range(24):
            hour_12 = h % 12 or 12
            ampm = "AM" if h < 12 else "PM"
            label = f"{hour_12}:00 {ampm}"
            if h == 0:
                label += "  (midnight)"
            elif h == 12:
                label += "  (noon)"
            options.append(discord.SelectOption(label=label, value=str(h)))
        super().__init__(
            placeholder="🕐 Time (optional, needs day)…", options=options, row=2
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: TaskCreateSetupView = self.view  # type: ignore[assignment]
        view._hour_24 = int(self.values[0])
        await interaction.response.edit_message(content=view.summary(), view=view)


class TaskCreateSetupView(ui.View):
    """Step-2 view shown after the create modal.

    Row 0 — Priority dropdown (low / medium / high)
    Row 1 — Day dropdown    (Today … In 1 month)
    Row 2 — Time dropdown   (12:00 AM … 11:00 PM, hourly)
    Row 3 — ✅ Create Task  |  ⏭ Skip Date  |  ✖ Cancel
    """

    def __init__(
        self,
        title: str,
        description: str,
        db: "Database",
        user_id: int,
        guild_id: int,
        channel_id: int,
    ) -> None:
        super().__init__(timeout=120)
        self._title = title
        self._description = description
        self._db = db
        self._user_id = user_id
        self._guild_id = guild_id
        self._channel_id = channel_id
        self._priority: TaskPriority = TaskPriority.MEDIUM
        self._day: str | None = None
        self._hour_24: int | None = None

        self.add_item(_PrioritySelect())
        self.add_item(_CreateDaySelect())
        self.add_item(_CreateTimeSelect())

        confirm_btn: ui.Button = ui.Button(
            label="✅ Create Task",
            style=discord.ButtonStyle.success,
            row=3,
        )
        confirm_btn.callback = self._confirm

        skip_btn: ui.Button = ui.Button(
            label="⏭ Skip Date",
            style=discord.ButtonStyle.secondary,
            row=3,
        )
        skip_btn.callback = self._skip_date

        cancel_btn: ui.Button = ui.Button(
            label="✖ Cancel",
            style=discord.ButtonStyle.danger,
            row=3,
        )
        cancel_btn.callback = self._cancel

        self.add_item(confirm_btn)
        self.add_item(skip_btn)
        self.add_item(cancel_btn)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def summary(self) -> str:
        """Return the status line shown above the dropdowns."""
        priority_labels: dict[str, str] = {
            "low": "🟢 Low",
            "medium": "🟡 Medium",
            "high": "🔴 High",
        }
        p_label = priority_labels.get(self._priority.value, "🟡 Medium")
        day_labels: dict[str, str] = {
            "today": "Today", "tomorrow": "Tomorrow",
            "2d": "In 2 days", "3d": "In 3 days", "7d": "In 1 week",
            "14d": "In 2 weeks", "30d": "In 1 month",
        }
        date_info = ""
        if self._day:
            day_name = day_labels.get(self._day, self._day)
            if self._hour_24 is not None:
                h12 = self._hour_24 % 12 or 12
                ampm = "AM" if self._hour_24 < 12 else "PM"
                date_info = f"  ·  📅 {day_name} at {h12}:00 {ampm}"
            else:
                date_info = f"  ·  📅 {day_name} (no time set — defaults to 9:00 AM)"
        elif self._hour_24 is not None:
            h12 = self._hour_24 % 12 or 12
            ampm = "AM" if self._hour_24 < 12 else "PM"
            date_info = f"  ·  🕐 {h12}:00 {ampm} (select a day too)"
        return (
            f"**Creating:** {self._title}\n"
            f"Priority: {p_label}{date_info}\n\n"
            "Choose priority and optionally a due date, then press **Create Task**.\n"
            "Press **Skip Date** to create without a due date."
        )

    def _resolve_due_dt(self) -> datetime | None:
        """Compute UTC datetime from day + hour selections, or ``None``."""
        if self._day is None:
            return None
        try:
            from bot.config import settings as _cfg  # noqa: PLC0415

            tz: ZoneInfo | UTC = ZoneInfo(_cfg.bot_timezone)  # type: ignore[assignment]
        except (ZoneInfoNotFoundError, KeyError, ImportError):
            tz = UTC  # type: ignore[assignment]
        now_local = datetime.now(tz).replace(tzinfo=None)
        if self._day == "today":
            base = now_local
        elif self._day == "tomorrow":
            base = now_local + timedelta(days=1)
        else:
            base = now_local + timedelta(days=int(str(self._day).rstrip("d")))
        hour_24 = self._hour_24 if self._hour_24 is not None else 9
        local_dt = base.replace(hour=hour_24, minute=0, second=0, microsecond=0)
        return _local_to_utc(local_dt)

    # ------------------------------------------------------------------
    # Button callbacks
    # ------------------------------------------------------------------

    async def _confirm(self, interaction: discord.Interaction) -> None:
        """Create the task with the selected priority and due date."""
        await interaction.response.defer(ephemeral=True)
        due_at = self._resolve_due_dt()
        req = TaskCreateRequest(
            user_id=self._user_id,
            guild_id=self._guild_id,
            channel_id=self._channel_id,
            title=self._title,
            description=self._description,
            priority=self._priority,
            due_at=due_at,
            reminder_at=due_at,  # reminder mirrors due date automatically
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

        # Lazy import breaks the circular dependency with task_views.
        from bot.ui.task_views import TaskDetailView  # noqa: PLC0415

        detail_view = TaskDetailView(task=task, db=self._db)
        await interaction.followup.send(
            content="✅ Task created! Use **🔔 Reminder** below to add a reminder.",
            embed=task_detail_embed(task),
            view=detail_view,
            ephemeral=True,
        )
        self.stop()

    async def _skip_date(self, interaction: discord.Interaction) -> None:
        """Create the task without a due date."""
        self._day = None
        self._hour_24 = None
        await self._confirm(interaction)

    async def _cancel(self, interaction: discord.Interaction) -> None:
        """Discard the new task without saving."""
        await interaction.response.edit_message(content="Cancelled.", view=None)
        self.stop()


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

    def __init__(self, task: Task, db: "Database") -> None:
        super().__init__()
        self._task = task
        self._db = db
        # Pre-fill current values
        self.task_title.default = task.title
        self.task_description.default = task.description
        self.task_priority.default = task.priority.value

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

        req = TaskUpdateRequest(
            title=self.task_title.value,
            description=self.task_description.value or "",
            priority=priority,
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

        # Lazy import breaks the circular dependency with task_views.
        from bot.ui.task_views import TaskDetailView  # noqa: PLC0415

        view = TaskDetailView(task=updated, db=self._db)
        await interaction.followup.send(
            content="Task updated! Use **📅 Due Date** and **🔔 Reminder** below to change dates.",
            embed=task_detail_embed(updated),
            view=view,
            ephemeral=True,
        )
