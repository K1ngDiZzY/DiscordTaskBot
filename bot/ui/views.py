"""Discord UI Views and Modals for the task bot.

Contains interactive UI components:
- :class:`TaskCreateModal` — modal form for creating a new task.
- :class:`TaskEditModal` — modal form for editing an existing task.
- :class:`TaskDetailView` — button panel shown below a task detail embed.
- :class:`TaskListView` — pagination controls for the task list.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

import discord
from discord import ui

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


def _parse_dt(value: str) -> datetime | None:
    """Try to parse a user-supplied datetime string.

    Attempts several common formats.

    Args:
        value: Raw string from the user.

    Returns:
        A naive :class:`datetime` (treated as UTC by convention), or None if
        the string is empty.

    Raises:
        ValueError: If the string is non-empty but cannot be parsed.
    """
    value = value.strip()
    if not value:
        return None
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(
        f"Could not parse '{value}'. "
        "Please use format: YYYY-MM-DD HH:MM  (e.g. 2026-03-15 09:00)"
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
        label="Due date — YYYY-MM-DD HH:MM  (clear = leave blank)",
        required=False,
        max_length=20,
    )
    task_reminder: ui.TextInput = ui.TextInput(
        label="Reminder — YYYY-MM-DD HH:MM  (clear = leave blank)",
        required=False,
        max_length=20,
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
        if interaction.user.id != self._task.user_id:
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

    @ui.button(label="✏️ Edit", style=discord.ButtonStyle.primary)
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

    @ui.button(label="✅ Mark Done", style=discord.ButtonStyle.success)
    async def done_button(
        self, interaction: discord.Interaction, _button: ui.Button
    ) -> None:
        """Mark this task as done instantly."""
        if interaction.user.id != self._task.user_id:
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

    @ui.button(label="🗑️ Delete", style=discord.ButtonStyle.danger)
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
