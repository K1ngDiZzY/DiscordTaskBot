"""Tests for the database layer."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, UTC
from pathlib import Path

import pytest_asyncio

from bot.database import Database
from bot.models import (
    TaskCreateRequest,
    TaskPriority,
    TaskStatus,
    TaskUpdateRequest,
)


@pytest_asyncio.fixture(loop_scope="function")
async def db(tmp_path: Path) -> AsyncGenerator[Database, None]:
    """Provide a temp-file Database for each test."""
    database = Database(str(tmp_path / "test.db"))
    await database.connect()
    yield database
    await database.close()


async def test_create_task(db: Database) -> None:  # noqa: F811
    """Creating a task returns a Task with an assigned ID."""
    req = TaskCreateRequest(
        user_id=123,
        guild_id=456,
        channel_id=789,
        title="Buy groceries",
        description="Milk, eggs, bread",
        priority=TaskPriority.HIGH,
    )
    task = await db.create_task(req)

    assert task.id is not None
    assert task.title == "Buy groceries"
    assert task.priority == TaskPriority.HIGH
    assert task.status == TaskStatus.PENDING


async def test_get_task_not_found(db: Database) -> None:  # noqa: F811
    """Fetching a non-existent task returns None."""
    result = await db.get_task(9999)
    assert result is None


async def test_update_task_status(db: Database) -> None:  # noqa: F811
    """Updating a task's status is reflected on re-fetch."""
    req = TaskCreateRequest(
        user_id=1, guild_id=1, channel_id=1, title="Test"
    )
    task = await db.create_task(req)

    updated = await db.update_task(
        task.id, TaskUpdateRequest(status=TaskStatus.DONE)
    )
    assert updated is not None
    assert updated.status == TaskStatus.DONE


async def test_delete_task(db: Database) -> None:  # noqa: F811
    """Deleting a task removes it from the database."""
    req = TaskCreateRequest(
        user_id=1, guild_id=1, channel_id=1, title="To delete"
    )
    task = await db.create_task(req)

    deleted = await db.delete_task(task.id)
    assert deleted is True

    result = await db.get_task(task.id)
    assert result is None


async def test_list_tasks_pagination(db: Database) -> None:  # noqa: F811
    """Listing tasks respects limit/offset."""
    for i in range(5):
        await db.create_task(
            TaskCreateRequest(
                user_id=1, guild_id=1, channel_id=1, title=f"Task {i}"
            )
        )

    page1 = await db.get_tasks_for_user(1, 1, limit=3, offset=0)
    page2 = await db.get_tasks_for_user(1, 1, limit=3, offset=3)

    assert len(page1) == 3
    assert len(page2) == 2


async def test_due_reminders(db: Database) -> None:  # noqa: F811
    """Tasks with past reminder_at are returned as due."""
    past = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
    future = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)

    await db.create_task(
        TaskCreateRequest(
            user_id=1, guild_id=1, channel_id=1,
            title="Past reminder", reminder_at=past,
        )
    )
    await db.create_task(
        TaskCreateRequest(
            user_id=1, guild_id=1, channel_id=1,
            title="Future reminder", reminder_at=future,
        )
    )

    due = await db.get_due_reminders()
    titles = [t.title for t in due]
    assert "Past reminder" in titles
    assert "Future reminder" not in titles


# ---------------------------------------------------------------------------
# Additional coverage — previously uncovered public methods
# ---------------------------------------------------------------------------

async def test_count_tasks_for_user(db: Database) -> None:  # noqa: F811
    """count_tasks_for_user returns the correct row count, with and without status filter."""
    for i in range(3):
        await db.create_task(
            TaskCreateRequest(user_id=1, guild_id=1, channel_id=1, title=f"T{i}")
        )
    # Mark one as DONE
    tasks = await db.get_tasks_for_user(1, 1)
    await db.update_task(tasks[0].id, TaskUpdateRequest(status=TaskStatus.DONE))

    total = await db.count_tasks_for_user(1, 1)
    assert total == 3

    done_count = await db.count_tasks_for_user(1, 1, status=TaskStatus.DONE)
    assert done_count == 1

    pending_count = await db.count_tasks_for_user(1, 1, status=TaskStatus.PENDING)
    assert pending_count == 2


async def test_get_tasks_for_user_status_filter(db: Database) -> None:  # noqa: F811
    """get_tasks_for_user filters correctly by status."""
    req = TaskCreateRequest(user_id=2, guild_id=2, channel_id=2, title="Todo")
    task = await db.create_task(req)
    await db.update_task(task.id, TaskUpdateRequest(status=TaskStatus.IN_PROGRESS))

    in_progress = await db.get_tasks_for_user(2, 2, status=TaskStatus.IN_PROGRESS)
    pending = await db.get_tasks_for_user(2, 2, status=TaskStatus.PENDING)

    assert len(in_progress) == 1
    assert in_progress[0].status == TaskStatus.IN_PROGRESS
    assert len(pending) == 0


async def test_update_task_clear_due_and_reminder(db: Database) -> None:  # noqa: F811
    """clear_due and clear_reminder flags remove scheduled fields."""
    due = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1)
    reminder = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)

    task = await db.create_task(
        TaskCreateRequest(
            user_id=1, guild_id=1, channel_id=1,
            title="Cleanup test",
            due_at=due,
            reminder_at=reminder,
        )
    )
    assert task.due_at is not None
    assert task.reminder_at is not None

    cleared = await db.update_task(
        task.id, TaskUpdateRequest(clear_due=True, clear_reminder=True)
    )
    assert cleared is not None
    assert cleared.due_at is None
    assert cleared.reminder_at is None


async def test_mark_reminder_sent(db: Database) -> None:  # noqa: F811
    """mark_reminder_sent flips reminder_sent to True."""
    past = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)
    task = await db.create_task(
        TaskCreateRequest(
            user_id=1, guild_id=1, channel_id=1,
            title="Remind me", reminder_at=past,
        )
    )
    assert not task.reminder_sent

    await db.mark_reminder_sent(task.id)
    refreshed = await db.get_task(task.id)
    assert refreshed is not None
    assert refreshed.reminder_sent is True

    # Should no longer appear in due reminders
    due = await db.get_due_reminders()
    ids = [t.id for t in due]
    assert task.id not in ids


async def test_delete_nonexistent_task(db: Database) -> None:  # noqa: F811
    """Deleting a task that does not exist returns False."""
    result = await db.delete_task(99999)
    assert result is False
