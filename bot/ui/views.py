"""Backward-compatible re-export facade for ``bot.ui`` components.

The UI package has been split into focused modules:

- :mod:`bot.ui.helpers`     — date/time parsing utilities
- :mod:`bot.ui.modals`      — :class:`TaskCreateModal`, :class:`TaskEditModal`
- :mod:`bot.ui.date_picker` — :class:`DatePickerView` and its sub-components
- :mod:`bot.ui.task_views`  — :class:`TaskDetailView`, :class:`TaskListView`,
                               :class:`ConfirmDeleteView`, :class:`StatusSelect`

This module re-exports every public symbol so that existing importers
(e.g. ``bot.cogs.tasks``, ``bot.cogs.reminders``) continue to work
without any changes.
"""

from bot.ui.date_picker import DatePickerView
from bot.ui.helpers import _local_to_utc, _parse_dt, _resolve_preset
from bot.ui.modals import TaskCreateModal, TaskCreateSetupView, TaskEditModal
from bot.ui.task_views import (
    ConfirmDeleteView,
    StatusSelect,
    TaskDetailView,
    TaskListView,
)

__all__ = [
    # Modals
    "TaskCreateModal",
    "TaskCreateSetupView",
    "TaskEditModal",
    # Date picker
    "DatePickerView",
    # Task views
    "StatusSelect",
    "TaskDetailView",
    "ConfirmDeleteView",
    "TaskListView",
    # Helpers (re-exported for any direct callers)
    "_parse_dt",
    "_local_to_utc",
    "_resolve_preset",
]
