"""Reminders cog — background task loop that fires due reminders.

The loop polls the database every ``settings.reminder_poll_seconds`` seconds.
When a task's ``reminder_at`` is in the past and the reminder has not yet been
sent, the bot sends an embed to either the task's originating channel or, as a
fallback, a DM to the task owner.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks

from bot.config import settings
from bot.ui.embeds import reminder_embed
from bot.ui.views import TaskDetailView

if TYPE_CHECKING:
    from bot.core import DiscordBot
    from bot.models import Task

logger = logging.getLogger(__name__)


class RemindersCog(commands.Cog, name="Reminders"):
    """Cog responsible for dispatching task reminders on schedule."""

    def __init__(self, bot: DiscordBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Start the background reminder loop when the cog is loaded."""
        self._reminder_loop.change_interval(
            seconds=settings.reminder_poll_seconds
        )
        self._reminder_loop.start()
        logger.info(
            "RemindersCog loaded — polling every %s seconds.",
            settings.reminder_poll_seconds,
        )

    async def cog_unload(self) -> None:
        """Cancel the loop gracefully when the cog is unloaded."""
        self._reminder_loop.cancel()
        logger.info("RemindersCog unloaded.")

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    @tasks.loop(seconds=60)  # interval replaced in cog_load
    async def _reminder_loop(self) -> None:
        """Periodically check for and dispatch due reminders."""
        try:
            due_tasks = await self.bot.db.get_due_reminders()
        except (OSError, RuntimeError) as exc:
            logger.exception("Error fetching due reminders: %s", exc)
            return

        for task in due_tasks:
            try:
                await self._dispatch_reminder(task)
                await self.bot.db.mark_reminder_sent(task.id)
            except (OSError, RuntimeError, discord.DiscordException) as exc:
                logger.exception(
                    "Failed to dispatch reminder for task %s: %s", task.id, exc
                )

    @_reminder_loop.before_loop
    async def _before_reminder_loop(self) -> None:
        """Wait until the bot is fully ready before the first iteration."""
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    # Dispatch helpers
    # ------------------------------------------------------------------

    async def _dispatch_reminder(
        self, task: Task
    ) -> None:
        """Send a reminder embed to the appropriate destination.

        Tries the task's originating channel first.  If that channel is
        unavailable (e.g. bot no longer in the guild) it falls back to a
        DM with the task owner.

        Args:
            task: The task whose reminder is due.
        """
        embed = reminder_embed(task)
        view = TaskDetailView(task=task, db=self.bot.db)
        mention = f"<@{task.user_id}>"

        sent = False

        # Try the originating channel
        if task.channel_id:
            channel = self.bot.get_channel(task.channel_id)
            if isinstance(channel, (discord.TextChannel, discord.Thread)):
                try:
                    await channel.send(
                        content=f"⏰ {mention} — you have a task reminder!",
                        embed=embed,
                        view=view,
                    )
                    sent = True
                    logger.info(
                        "Reminder for task #%s sent to channel #%s",
                        task.id,
                        channel.name,
                    )
                except discord.DiscordException as exc:
                    logger.warning(
                        "Could not send reminder to channel %s: %s",
                        task.channel_id,
                        exc,
                    )

        # Fallback: DM the user
        if not sent:
            try:
                user = await self.bot.fetch_user(task.user_id)
                await user.send(
                    content="⏰ You have a task reminder!",
                    embed=embed,
                    view=view,
                )
                sent = True
                logger.info(
                    "Reminder for task #%s sent via DM to user %s",
                    task.id,
                    task.user_id,
                )
            except discord.DiscordException as exc:
                logger.error(
                    "Could not send DM reminder for task #%s to user %s: %s",
                    task.id,
                    task.user_id,
                    exc,
                )

        if not sent:
            raise RuntimeError(
                f"Could not deliver reminder for task #{task.id}: "
                "channel unavailable and DM failed."
            )


async def setup(bot: DiscordBot) -> None:
    """Register :class:`RemindersCog` with the bot.

    Args:
        bot: The running bot instance.
    """
    await bot.add_cog(RemindersCog(bot))
