"""Async SQLite database layer for the task bot.

All database access is performed via aiosqlite so it never blocks the
Discord event loop.  The :class:`Database` class is a context manager and
should be opened once at bot startup and closed at shutdown.
"""

from __future__ import annotations

import logging
from datetime import datetime, UTC
from pathlib import Path

import aiosqlite

from bot.models import Task, TaskCreateRequest, TaskPriority, TaskStatus, TaskUpdateRequest

logger = logging.getLogger(__name__)

# Datetime convention: all datetimes are stored and returned as *naive UTC*.
# tzinfo is always stripped before storage and never re-attached on retrieval.
# Callers that need aware datetimes should do `dt.replace(tzinfo=UTC)`.

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    guild_id        INTEGER NOT NULL,
    channel_id      INTEGER,
    title           TEXT    NOT NULL,
    description     TEXT    NOT NULL DEFAULT '',
    status          TEXT    NOT NULL DEFAULT 'pending',
    priority        TEXT    NOT NULL DEFAULT 'medium',
    due_at          TEXT,
    reminder_at     TEXT,
    reminder_sent   INTEGER NOT NULL DEFAULT 0,
    assigned_to_id  INTEGER,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks (user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_reminder ON tasks (reminder_at, reminder_sent);
"""

# Separate statement so it only runs after the migration has added the column
# to pre-existing databases.  executescript() commits implicitly, so running
# the index creation in the same script as CREATE TABLE would fail on old DBs
# that don't yet have the column.
_CREATE_ASSIGNED_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_tasks_assigned ON tasks (assigned_to_id);
"""

# Migration: add assigned_to_id to existing databases that pre-date this column.
_MIGRATE_SQL = """
ALTER TABLE tasks ADD COLUMN assigned_to_id INTEGER;
"""

_DT_FMT = "%Y-%m-%dT%H:%M:%S"


def _dt_to_str(dt: datetime | None) -> str | None:
    """Serialize a datetime to ISO-8601 string for SQLite storage."""
    return dt.strftime(_DT_FMT) if dt is not None else None


def _str_to_dt(s: str | None) -> datetime | None:
    """Parse an ISO-8601 string from SQLite into a datetime."""
    return datetime.strptime(s, _DT_FMT) if s else None


def _row_to_task(row: aiosqlite.Row) -> Task:
    """Convert a raw SQLite row into a :class:`Task` dataclass."""
    created_raw = row["created_at"]
    updated_raw = row["updated_at"]
    if not created_raw or not updated_raw:
        raise RuntimeError(
            f"Data integrity error: task row id={row['id']} is missing "
            "created_at or updated_at (NOT NULL columns)."
        )
    return Task(
        id=row["id"],
        user_id=row["user_id"],
        guild_id=row["guild_id"],
        channel_id=row["channel_id"],
        title=row["title"],
        description=row["description"],
        status=TaskStatus(row["status"]),
        priority=TaskPriority(row["priority"]),
        due_at=_str_to_dt(row["due_at"]),
        reminder_at=_str_to_dt(row["reminder_at"]),
        reminder_sent=bool(row["reminder_sent"]),
        assigned_to_id=row["assigned_to_id"],
        created_at=_str_to_dt(created_raw),  # type: ignore[arg-type]  # guaranteed non-None by check above
        updated_at=_str_to_dt(updated_raw),  # type: ignore[arg-type]  # guaranteed non-None by check above
    )


class Database:
    """Async SQLite database interface.

    Usage::

        db = Database("data/tasks.db")
        await db.connect()
        # ... use db ...
        await db.close()

    Or use as an async context manager::

        async with Database("data/tasks.db") as db:
            task = await db.create_task(req)
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the database connection and initialise the schema."""
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        # 1. Create table + basic indexes (no assigned_to_id index yet).
        await self._conn.executescript(_CREATE_TABLE_SQL)
        await self._conn.commit()
        # 2. Best-effort migration: add assigned_to_id if the column is absent.
        try:
            await self._conn.execute(_MIGRATE_SQL)
            await self._conn.commit()
            logger.info("Migration applied: added assigned_to_id column.")
        except Exception:
            # Column already exists — SQLite raises OperationalError; swallow it.
            pass
        # 3. Now safe to create the index that depends on assigned_to_id.
        await self._conn.executescript(_CREATE_ASSIGNED_INDEX_SQL)
        await self._conn.commit()
        logger.info("Database connected: %s", self._path)

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            logger.info("Database closed.")

    async def __aenter__(self) -> "Database":
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _db(self) -> aiosqlite.Connection:
        """Return the active connection or raise if not connected."""
        if self._conn is None:
            raise RuntimeError("Database is not connected. Call connect() first.")
        return self._conn

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create_task(self, req: TaskCreateRequest) -> Task:
        """Insert a new task row and return the created :class:`Task`.

        Args:
            req: Validated create request payload.

        Returns:
            The newly created task with its assigned ID.
        """
        now = datetime.now(UTC).replace(tzinfo=None)
        async with self._db.execute(
            """
            INSERT INTO tasks
                (user_id, guild_id, channel_id, title, description,
                 status, priority, due_at, reminder_at, reminder_sent,
                 assigned_to_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                req.user_id,
                req.guild_id,
                req.channel_id,
                req.title,
                req.description,
                TaskStatus.PENDING.value,
                req.priority.value,
                _dt_to_str(req.due_at),
                _dt_to_str(req.reminder_at),
                getattr(req, "assigned_to_id", None),
                _dt_to_str(now),
                _dt_to_str(now),
            ),
        ) as cursor:
            task_id = cursor.lastrowid
        await self._db.commit()
        assert task_id is not None, "cursor.lastrowid was None after INSERT"
        task = await self.get_task(task_id)
        if task is None:
            raise RuntimeError(
                f"Failed to retrieve task after insert (last_row_id={task_id})"
            )
        return task

    async def get_task(self, task_id: int) -> Task | None:
        """Fetch a task by its primary key.

        Args:
            task_id: The task's database ID.

        Returns:
            The task, or None if not found.
        """
        async with self._db.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return _row_to_task(row) if row else None

    async def get_tasks_for_user(
        self,
        user_id: int,
        guild_id: int,
        *,
        status: TaskStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Task]:
        """Return tasks owned by a user in a guild.

        Args:
            user_id: Discord user snowflake.
            guild_id: Discord guild snowflake.
            status: Optional status filter.
            limit: Maximum rows to return (default 20).
            offset: Pagination offset.

        Returns:
            List of tasks ordered by created_at descending.
        """
        if status is not None:
            query = """
                SELECT * FROM tasks
                WHERE user_id = ? AND guild_id = ? AND status = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """
            params = (user_id, guild_id, status.value, limit, offset)
        else:
            query = """
                SELECT * FROM tasks
                WHERE user_id = ? AND guild_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """
            params = (user_id, guild_id, limit, offset)

        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_task(r) for r in rows]

    async def count_tasks_for_user(
        self,
        user_id: int,
        guild_id: int,
        *,
        status: TaskStatus | None = None,
    ) -> int:
        """Return the total number of tasks for a user.

        Args:
            user_id: Discord user snowflake.
            guild_id: Discord guild snowflake.
            status: Optional status filter.

        Returns:
            Row count.
        """
        if status is not None:
            query = (
                "SELECT COUNT(*) FROM tasks "
                "WHERE user_id = ? AND guild_id = ? AND status = ?"
            )
            params = (user_id, guild_id, status.value)
        else:
            query = (
                "SELECT COUNT(*) FROM tasks WHERE user_id = ? AND guild_id = ?"
            )
            params = (user_id, guild_id)

        async with self._db.execute(query, params) as cursor:
            row = await cursor.fetchone()
        return row[0] if row else 0

    async def update_task(self, task_id: int, req: TaskUpdateRequest) -> Task | None:
        """Apply partial updates to a task row.

        Only fields that are set (not None) on *req* are written.

        Args:
            task_id: The task's database ID.
            req: Update payload; None fields are left unchanged.

        Returns:
            The updated task, or None if the task was not found.
        """
        fields: list[str] = []
        values: list[object] = []

        if req.title is not None:
            fields.append("title = ?")
            values.append(req.title)
        if req.description is not None:
            fields.append("description = ?")
            values.append(req.description)
        if req.status is not None:
            fields.append("status = ?")
            values.append(req.status.value)
        if req.priority is not None:
            fields.append("priority = ?")
            values.append(req.priority.value)
        if req.clear_due:
            fields.append("due_at = ?")
            values.append(None)
        elif req.due_at is not None:
            fields.append("due_at = ?")
            values.append(_dt_to_str(req.due_at))
        if req.clear_reminder:
            fields.append("reminder_at = ?")
            values.append(None)
            fields.append("reminder_sent = ?")
            values.append(0)
        elif req.reminder_at is not None:
            fields.append("reminder_at = ?")
            values.append(_dt_to_str(req.reminder_at))
            fields.append("reminder_sent = ?")
            values.append(0)
        if req.clear_assigned:
            fields.append("assigned_to_id = ?")
            values.append(None)
        elif req.assigned_to_id is not None:
            fields.append("assigned_to_id = ?")
            values.append(req.assigned_to_id)

        if not fields:
            return await self.get_task(task_id)

        now = datetime.now(UTC).replace(tzinfo=None)
        fields.append("updated_at = ?")
        values.append(_dt_to_str(now))
        values.append(task_id)

        # noqa: S608 — safe: `fields` is built exclusively from hard-coded
        # string literals (column = ?) assembled by this method; no user input
        # ever reaches the column-name list.
        await self._db.execute(
            f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        await self._db.commit()
        return await self.get_task(task_id)

    async def delete_task(self, task_id: int) -> bool:
        """Delete a task by ID.

        Args:
            task_id: The task's database ID.

        Returns:
            True if a row was deleted, False otherwise.
        """
        async with self._db.execute(
            "DELETE FROM tasks WHERE id = ?", (task_id,)
        ) as cursor:
            deleted = cursor.rowcount > 0
        await self._db.commit()
        return deleted

    async def get_tasks_assigned_to(
        self,
        assigned_to_id: int,
        guild_id: int,
        *,
        status: TaskStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Task]:
        """Return tasks assigned to a specific user in a guild.

        Args:
            assigned_to_id: Discord user snowflake of the assignee.
            guild_id: Discord guild snowflake.
            status: Optional status filter.
            limit: Maximum rows to return.
            offset: Pagination offset.

        Returns:
            List of tasks ordered by created_at descending.
        """
        if status is not None:
            query = """
                SELECT * FROM tasks
                WHERE assigned_to_id = ? AND guild_id = ? AND status = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """
            params = (assigned_to_id, guild_id, status.value, limit, offset)
        else:
            query = """
                SELECT * FROM tasks
                WHERE assigned_to_id = ? AND guild_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """
            params = (assigned_to_id, guild_id, limit, offset)

        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_task(r) for r in rows]

    async def count_tasks_assigned_to(
        self,
        assigned_to_id: int,
        guild_id: int,
        *,
        status: TaskStatus | None = None,
    ) -> int:
        """Return total tasks assigned to a user in a guild.

        Args:
            assigned_to_id: Discord user snowflake of the assignee.
            guild_id: Discord guild snowflake.
            status: Optional status filter.

        Returns:
            Row count.
        """
        if status is not None:
            query = (
                "SELECT COUNT(*) FROM tasks "
                "WHERE assigned_to_id = ? AND guild_id = ? AND status = ?"
            )
            params = (assigned_to_id, guild_id, status.value)
        else:
            query = (
                "SELECT COUNT(*) FROM tasks "
                "WHERE assigned_to_id = ? AND guild_id = ?"
            )
            params = (assigned_to_id, guild_id)

        async with self._db.execute(query, params) as cursor:
            row = await cursor.fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # Reminder helpers
    # ------------------------------------------------------------------

    async def get_due_reminders(self) -> list[Task]:
        """Return all tasks with a reminder that is now due and unsent.

        Returns:
            Tasks whose reminder_at <= now and reminder_sent = 0.
        """
        now = _dt_to_str(datetime.now(UTC).replace(tzinfo=None))
        async with self._db.execute(
            """
            SELECT * FROM tasks
            WHERE reminder_at IS NOT NULL
              AND reminder_sent = 0
              AND reminder_at <= ?
            """,
            (now,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_task(r) for r in rows]

    async def mark_reminder_sent(self, task_id: int) -> None:
        """Flag a task's reminder as already dispatched.

        Args:
            task_id: The task's database ID.
        """
        await self._db.execute(
            "UPDATE tasks SET reminder_sent = 1 WHERE id = ?", (task_id,)
        )
        await self._db.commit()
