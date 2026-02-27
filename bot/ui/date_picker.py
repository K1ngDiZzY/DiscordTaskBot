"""Interactive date/time picker view for setting due dates and reminders.

Classes
-------
:class:`DatePickerView`    — four-dropdown + confirm/cancel/clear UI.
:class:`_CustomDateModal`  — free-text fallback modal for the picker.
:class:`_DaySelect`        — row-0 day dropdown.
:class:`_HourSelect`       — row-1 hour dropdown (1–12).
:class:`_AmPmSelect`       — row-2 AM/PM dropdown.
:class:`_MinuteSelect`     — row-3 minutes dropdown (:00/:15/:30/:45).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord import ui

from bot.config import settings
from bot.models import Task, TaskUpdateRequest
from bot.ui.embeds import error_embed, task_detail_embed
from bot.ui.helpers import _local_to_utc, _parse_dt

if TYPE_CHECKING:
    from bot.database import Database

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom free-text date modal (fallback from picker "Custom…" option)
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

        # Lazy import breaks the circular dependency with task_views.
        from bot.ui.task_views import TaskDetailView  # noqa: PLC0415

        view = TaskDetailView(task=updated, db=self._db)
        await interaction.followup.send(
            content=f"✅ {label} updated!",
            embed=task_detail_embed(updated),
            view=view,
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# Dropdown sub-components
# ---------------------------------------------------------------------------


class _DaySelect(ui.Select):
    """Row-0 dropdown for choosing which day."""

    def __init__(self) -> None:
        options = [
            discord.SelectOption(label="Today",      value="today",   emoji="📅"),
            discord.SelectOption(label="Tomorrow",   value="tomorrow", emoji="📅"),
            discord.SelectOption(label="In 2 days",  value="2d",      emoji="📅"),
            discord.SelectOption(label="In 3 days",  value="3d",      emoji="📅"),
            discord.SelectOption(label="In 1 week",  value="7d",      emoji="📅"),
            discord.SelectOption(label="In 2 weeks", value="14d",     emoji="📅"),
            discord.SelectOption(label="In 1 month", value="30d",     emoji="📅"),
            discord.SelectOption(label="Custom…",    value="custom",  emoji="✏️"),
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
        await interaction.response.edit_message(content=view._summary(), view=view)


class _HourSelect(ui.Select):
    """Row-1 dropdown for choosing the hour (1–12)."""

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
        await interaction.response.edit_message(content=view._summary(), view=view)


class _AmPmSelect(ui.Select):
    """Row-2 dropdown for AM/PM selection."""

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
        await interaction.response.edit_message(content=view._summary(), view=view)


class _MinuteSelect(ui.Select):
    """Row-3 dropdown for minute selection (:00 / :15 / :30 / :45)."""

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
        await interaction.response.edit_message(content=view._summary(), view=view)


# ---------------------------------------------------------------------------
# DatePickerView
# ---------------------------------------------------------------------------


class DatePickerView(ui.View):
    """Structured date/time picker using four dropdowns + action buttons.

    Row 0 — Day (Today / Tomorrow / In X days / Custom…)
    Row 1 — Hour (1–12)
    Row 2 — AM / PM
    Row 3 — Minutes (:00 / :15 / :30 / :45)
    Row 4 — ✅ Confirm  |  ✖ Cancel  |  🚫 Clear Date
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

        self._clear_btn: ui.Button = ui.Button(
            label="🚫 Clear Date",
            style=discord.ButtonStyle.danger,
            row=4,
        )
        self._clear_btn.callback = self._clear_callback

        self.add_item(self._confirm_btn)
        self.add_item(self._cancel_btn)
        self.add_item(self._clear_btn)

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _summary(self) -> str:
        """Build the picker status line shown above the dropdowns."""
        label = (
            "📅 **Set due date**" if self._field == "due_at" else "🔔 **Set reminder**"
        )
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
        local_dt = base.replace(
            hour=hour_24, minute=self._minute, second=0, microsecond=0
        )
        return _local_to_utc(local_dt)

    # ------------------------------------------------------------------
    # Button callbacks
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
            # Mirror reminder to the same datetime automatically.
            req = TaskUpdateRequest(due_at=dt, reminder_at=dt)
        else:
            req = TaskUpdateRequest(reminder_at=dt)
        updated = await self._db.update_task(self._task.id, req)
        if updated is None:
            await interaction.followup.send(
                embed=error_embed("Task not found."), ephemeral=True
            )
            return
        label = "Due date" if self._field == "due_at" else "Reminder"

        # Lazy import breaks the circular dependency with task_views.
        from bot.ui.task_views import TaskDetailView  # noqa: PLC0415

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

    async def _clear_callback(self, interaction: discord.Interaction) -> None:
        """Clear the date/time field on the task."""
        if interaction.user.id != self._task.user_id:
            await interaction.response.send_message(
                embed=error_embed("You don't have permission to modify this task."),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        if self._field == "due_at":
            # Clear reminder alongside due date.
            req = TaskUpdateRequest(clear_due=True, clear_reminder=True)
        else:
            req = TaskUpdateRequest(clear_reminder=True)
        updated = await self._db.update_task(self._task.id, req)
        if updated is None:
            await interaction.followup.send(
                embed=error_embed("Task not found."), ephemeral=True
            )
            return
        label = "Due date" if self._field == "due_at" else "Reminder"

        # Lazy import breaks the circular dependency with task_views.
        from bot.ui.task_views import TaskDetailView  # noqa: PLC0415

        detail_view = TaskDetailView(task=updated, db=self._db)
        await interaction.followup.send(
            content=f"🚫 {label} cleared.",
            embed=task_detail_embed(updated),
            view=detail_view,
            ephemeral=True,
        )
        self.stop()
