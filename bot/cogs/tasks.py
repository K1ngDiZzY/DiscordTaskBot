"""Tasks cog — slash commands for creating and managing tasks.

Commands
--------
/task add        — Open the 'Create Task' modal.
/task list       — Paginated list of your tasks (optional status filter).
/task view <id>  — Show full detail plus action buttons for one task.
/task done <id>  — Quick-mark a task as done without opening the modal.
/task delete <id>— Delete a task (with confirmation).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.models import TaskStatus, TaskUpdateRequest
from bot.ui.embeds import (
    error_embed,
    task_detail_embed,
    task_list_embed,
)
from bot.ui.views import (
    ConfirmDeleteView,
    TaskCreateModal,
    TaskDetailView,
    TaskListView,
)

if TYPE_CHECKING:
    from bot.core import DiscordBot

logger = logging.getLogger(__name__)

_STATUS_CHOICES = [
    app_commands.Choice(name="Pending", value="pending"),
    app_commands.Choice(name="In Progress", value="in_progress"),
    app_commands.Choice(name="Done", value="done"),
    app_commands.Choice(name="Cancelled", value="cancelled"),
]


class TasksCog(commands.Cog, name="Tasks"):
    """Cog that provides all task-management slash commands."""

    def __init__(self, bot: DiscordBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Called by discord.py after the cog is added to the bot."""
        logger.info("TasksCog loaded.")

    async def cog_unload(self) -> None:
        """Called by discord.py before the cog is removed."""
        logger.info("TasksCog unloaded.")

    # ------------------------------------------------------------------
    # Error handler
    # ------------------------------------------------------------------

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Handle slash command errors within this cog.

        Args:
            interaction: The interaction that triggered the error.
            error: The exception that was raised.
        """
        if isinstance(error, app_commands.CommandOnCooldown):
            embed = error_embed(
                f"Slow down! Try again in {error.retry_after:.1f}s.",
                title="Cooldown",
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        logger.exception("Task command error: %s", error)
        embed = error_embed("An unexpected error occurred. Please try again.")
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /task group
    # ------------------------------------------------------------------

    task_group = app_commands.Group(
        name="task",
        description="Manage your personal tasks",
    )

    # --- /task add ---

    @task_group.command(name="add", description="Create a new task")
    @app_commands.checks.cooldown(rate=5, per=60.0)
    async def task_add(self, interaction: discord.Interaction) -> None:
        """Open the task creation modal.

        Args:
            interaction: The Discord interaction.
        """
        modal = TaskCreateModal(db=self.bot.db)
        await interaction.response.send_modal(modal)

    # --- /task list ---

    @task_group.command(name="list", description="List your tasks")
    @app_commands.describe(status="Filter by task status (default: all)")
    @app_commands.choices(status=_STATUS_CHOICES)
    @app_commands.checks.cooldown(rate=3, per=10.0)
    async def task_list(
        self,
        interaction: discord.Interaction,
        status: app_commands.Choice[str] | None = None,
    ) -> None:
        """Return a paginated list of the caller's tasks.

        Args:
            interaction: The Discord interaction.
            status: Optional status filter choice.
        """
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild_id or 0
        user = interaction.user
        status_filter = TaskStatus(status.value) if status else None

        total = await self.bot.db.count_tasks_for_user(
            user.id, guild_id, status=status_filter
        )
        tasks = await self.bot.db.get_tasks_for_user(
            user.id,
            guild_id,
            status=status_filter,
            limit=TaskListView.PAGE_SIZE,
            offset=0,
        )

        embed = task_list_embed(
            tasks,
            user=user,
            page=1,
            total_pages=max(1, -(-total // TaskListView.PAGE_SIZE)),
            total_tasks=total,
            status_filter=status_filter,
        )
        view = TaskListView(
            db=self.bot.db,
            user=user,
            guild_id=guild_id,
            status_filter=status_filter,
            total_tasks=total,
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    # --- /task view ---

    @task_group.command(name="view", description="View details of a specific task")
    @app_commands.describe(task_id="The ID of the task to view")
    @app_commands.checks.cooldown(rate=5, per=30.0)
    async def task_view(
        self, interaction: discord.Interaction, task_id: int
    ) -> None:
        """Show a rich detail embed for a single task.

        Args:
            interaction: The Discord interaction.
            task_id: The task's database ID.
        """
        await interaction.response.defer(ephemeral=True)

        task = await self.bot.db.get_task(task_id)
        if task is None or task.user_id != interaction.user.id:
            await interaction.followup.send(
                embed=error_embed("Task not found or you don't have access to it."),
                ephemeral=True,
            )
            return

        view = TaskDetailView(task=task, db=self.bot.db)
        await interaction.followup.send(
            embed=task_detail_embed(task), view=view, ephemeral=True
        )

    # --- /task done ---

    @task_group.command(name="done", description="Mark a task as done")
    @app_commands.describe(task_id="The ID of the task to mark done")
    @app_commands.checks.cooldown(rate=5, per=30.0)
    async def task_done(
        self, interaction: discord.Interaction, task_id: int
    ) -> None:
        """Quick-action to mark a task complete without opening a modal.

        Args:
            interaction: The Discord interaction.
            task_id: The task's database ID.
        """
        await interaction.response.defer(ephemeral=True)

        task = await self.bot.db.get_task(task_id)
        if task is None or task.user_id != interaction.user.id:
            await interaction.followup.send(
                embed=error_embed("Task not found or you don't have access to it."),
                ephemeral=True,
            )
            return

        req = TaskUpdateRequest(status=TaskStatus.DONE)
        updated = await self.bot.db.update_task(task_id, req)
        if updated is None:
            await interaction.followup.send(
                embed=error_embed("Failed to update the task."), ephemeral=True
            )
            return

        view = TaskDetailView(task=updated, db=self.bot.db)
        await interaction.followup.send(
            embed=task_detail_embed(updated), view=view, ephemeral=True
        )

    # --- /task delete ---

    @task_group.command(name="delete", description="Delete a task permanently")
    @app_commands.describe(task_id="The ID of the task to delete")
    @app_commands.checks.cooldown(rate=3, per=30.0)
    async def task_delete(
        self, interaction: discord.Interaction, task_id: int
    ) -> None:
        """Show a confirmation prompt, then delete the task.

        Args:
            interaction: The Discord interaction.
            task_id: The task's database ID.
        """
        await interaction.response.defer(ephemeral=True)

        task = await self.bot.db.get_task(task_id)
        if task is None or task.user_id != interaction.user.id:
            await interaction.followup.send(
                embed=error_embed(
                    "Task not found or you don't have access to it."
                ),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            embed=discord.Embed(
                title="⚠️ Confirm Deletion",
                description=(
                    f"Are you sure you want to delete task "
                    f"**#{task.id} — {task.title}**?\n"
                    "This action **cannot** be undone."
                ),
                colour=discord.Colour.orange(),
            ),
            view=ConfirmDeleteView(task_id=task_id, db=self.bot.db),
            ephemeral=True,
        )


async def setup(bot: DiscordBot) -> None:
    """Register :class:`TasksCog` with the bot.

    discord.py's CogMeta automatically registers the ``task_group``
    :class:`app_commands.Group` with the bot's command tree when
    :meth:`bot.add_cog` is called, so we must NOT call
    ``bot.tree.add_command`` here to avoid a double-registration error.

    Args:
        bot: The running bot instance.
    """
    await bot.add_cog(TasksCog(bot))
