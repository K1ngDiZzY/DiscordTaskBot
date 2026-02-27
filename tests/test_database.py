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


# ---------------------------------------------------------------------------
# Assignment-related tests
# ---------------------------------------------------------------------------

async def test_create_task_with_assignment(db: Database) -> None:  # noqa: F811
    """Creating a task with assigned_to_id persists the assignment."""
    req = TaskCreateRequest(
        user_id=100,
        guild_id=200,
        channel_id=300,
        title="Assigned task",
        assigned_to_id=999,
    )
    task = await db.create_task(req)

    assert task.id is not None
    assert task.assigned_to_id == 999

    # Verify persistence
    fetched = await db.get_task(task.id)
    assert fetched is not None
    assert fetched.assigned_to_id == 999


async def test_update_task_assign(db: Database) -> None:  # noqa: F811
    """Updating a task to assign it to someone sets assigned_to_id."""
    task = await db.create_task(
        TaskCreateRequest(
            user_id=1, guild_id=1, channel_id=1, title="Unassigned"
        )
    )
    assert task.assigned_to_id is None

    updated = await db.update_task(
        task.id, TaskUpdateRequest(assigned_to_id=555)
    )
    assert updated is not None
    assert updated.assigned_to_id == 555


async def test_update_task_unassign(db: Database) -> None:  # noqa: F811
    """Updating a task with clear_assigned removes the assignment."""
    task = await db.create_task(
        TaskCreateRequest(
            user_id=1,
            guild_id=1,
            channel_id=1,
            title="Initially assigned",
            assigned_to_id=777,
        )
    )
    assert task.assigned_to_id == 777

    unassigned = await db.update_task(
        task.id, TaskUpdateRequest(clear_assigned=True)
    )
    assert unassigned is not None
    assert unassigned.assigned_to_id is None


async def test_get_tasks_assigned_to(db: Database) -> None:  # noqa: F811
    """get_tasks_assigned_to returns tasks assigned to a specific user."""
    # Create tasks with different assignments
    await db.create_task(
        TaskCreateRequest(
            user_id=1, guild_id=1, channel_id=1,
            title="Task A", assigned_to_id=100
        )
    )
    await db.create_task(
        TaskCreateRequest(
            user_id=1, guild_id=1, channel_id=1,
            title="Task B", assigned_to_id=100
        )
    )
    await db.create_task(
        TaskCreateRequest(
            user_id=1, guild_id=1, channel_id=1,
            title="Task C", assigned_to_id=200
        )
    )
    await db.create_task(
        TaskCreateRequest(
            user_id=1, guild_id=1, channel_id=1,
            title="Task D"  # No assignment
        )
    )

    # Fetch tasks assigned to user 100
    tasks = await db.get_tasks_assigned_to(100, 1)
    assert len(tasks) == 2
    titles = {t.title for t in tasks}
    assert titles == {"Task A", "Task B"}


async def test_get_tasks_assigned_to_with_status_filter(db: Database) -> None:  # noqa: F811
    """get_tasks_assigned_to filters by status when provided."""
    task1 = await db.create_task(
        TaskCreateRequest(
            user_id=1, guild_id=1, channel_id=1,
            title="Pending assigned", assigned_to_id=100
        )
    )
    task2 = await db.create_task(
        TaskCreateRequest(
            user_id=1, guild_id=1, channel_id=1,
            title="In progress assigned", assigned_to_id=100
        )
    )
    await db.update_task(task2.id, TaskUpdateRequest(status=TaskStatus.IN_PROGRESS))

    # Filter for pending only
    pending = await db.get_tasks_assigned_to(
        100, 1, status=TaskStatus.PENDING
    )
    assert len(pending) == 1
    assert pending[0].title == "Pending assigned"

    # Filter for in-progress only
    in_progress = await db.get_tasks_assigned_to(
        100, 1, status=TaskStatus.IN_PROGRESS
    )
    assert len(in_progress) == 1
    assert in_progress[0].title == "In progress assigned"


async def test_get_tasks_assigned_to_pagination(db: Database) -> None:  # noqa: F811
    """get_tasks_assigned_to respects limit and offset."""
    for i in range(5):
        await db.create_task(
            TaskCreateRequest(
                user_id=1, guild_id=1, channel_id=1,
                title=f"Assigned {i}", assigned_to_id=100
            )
        )

    page1 = await db.get_tasks_assigned_to(100, 1, limit=3, offset=0)
    page2 = await db.get_tasks_assigned_to(100, 1, limit=3, offset=3)

    assert len(page1) == 3
    assert len(page2) == 2


async def test_count_tasks_assigned_to(db: Database) -> None:  # noqa: F811
    """count_tasks_assigned_to returns correct count without status filter."""
    for i in range(4):
        await db.create_task(
            TaskCreateRequest(
                user_id=1, guild_id=1, channel_id=1,
                title=f"Task {i}", assigned_to_id=100
            )
        )

    count = await db.count_tasks_assigned_to(100, 1)
    assert count == 4


async def test_count_tasks_assigned_to_with_status(db: Database) -> None:  # noqa: F811
    """count_tasks_assigned_to filters by status when provided."""
    tasks = []
    for i in range(3):
        task = await db.create_task(
            TaskCreateRequest(
                user_id=1, guild_id=1, channel_id=1,
                title=f"Task {i}", assigned_to_id=100
            )
        )
        tasks.append(task)

    # Mark one as DONE
    await db.update_task(tasks[0].id, TaskUpdateRequest(status=TaskStatus.DONE))

    total = await db.count_tasks_assigned_to(100, 1)
    assert total == 3

    done_count = await db.count_tasks_assigned_to(100, 1, status=TaskStatus.DONE)
    assert done_count == 1

    pending_count = await db.count_tasks_assigned_to(100, 1, status=TaskStatus.PENDING)
    assert pending_count == 2
