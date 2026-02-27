"""Task-related Discord UI views and selects.

Classes
-------
:class:`StatusSelect`     — drop-down to change a task's status.
:class:`TaskDetailView`   — button panel shown below a task detail embed.
:class:`ConfirmDeleteView` — two-button confirmation before deleting.
:class:`TaskListView`     — pagination controls for the task list.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import ui

from bot.models import Task, TaskStatus, TaskUpdateRequest
from bot.ui.date_picker import DatePickerView
from bot.ui.embeds import error_embed, success_embed, task_detail_embed, task_list_embed
from bot.ui.modals import TaskEditModal

if TYPE_CHECKING:
    from bot.database import Database

logger = logging.getLogger(__name__)


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

    Row 0 — ✏️ Edit  |  ✅ Mark Done  |  🗑️ Delete
    Row 1 — 📅 Due Date  |  🔔 Reminder
    Select — Change status…
    """

    def __init__(self, task: Task, db: "Database") -> None:
        super().__init__(timeout=300)
        self._task = task
        self._db = db
        self.add_item(StatusSelect(task=task, db=db))

    async def on_timeout(self) -> None:
        """Disable all components when the view expires."""
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True

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
                embed=success_embed(f"Task **#{self._task_id}** has been deleted."),
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

    async def _render_page(self, interaction: discord.Interaction) -> None:
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
