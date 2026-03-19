from __future__ import annotations

import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from app.control.task_events import TaskEventRecorder
from app.control.task_store import TaskStore
from app.core.config import Settings, get_settings
from app.models.schemas import ControlTask, ControlTaskEvent, ControlTaskType


class TaskRegistryService:
    _LOCK_RETRY_ATTEMPTS = 5
    _LOCK_RETRY_DELAY_SECONDS = 0.2

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.database_path = self.settings.resolved_database_path
        self.tasks = TaskStore()
        self.events = TaskEventRecorder()
        self._ensure_parent_dir()
        self._initialize_schema()

    def create_task(
        self,
        *,
        task_type: ControlTaskType,
        agent_id: str,
        status: str,
        parent_task_id: str | None = None,
        user_id: str | None = None,
        source: str | None = None,
        repo: str | None = None,
        issue_number: int | None = None,
        title: str | None = None,
        external_ref: str | None = None,
        payload: dict[str, Any] | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> ControlTask:
        owned_connection = connection is None
        current_connection = connection or self._connect()
        try:
            def _create() -> ControlTask:
                created = self.tasks.create_task(
                    current_connection,
                    task_type=task_type,
                    agent_id=agent_id,
                    status=status,
                    parent_task_id=parent_task_id,
                    user_id=user_id,
                    source=source,
                    repo=repo,
                    issue_number=issue_number,
                    title=title,
                    external_ref=external_ref,
                    payload=payload,
                )
                self.events.append(
                    current_connection,
                    created.task_id,
                    "task_created",
                    {"status": status, **(payload or {})},
                )
                return created

            created = self._with_locked_retry(_create)
            if owned_connection:
                current_connection.commit()
            return created
        finally:
            if owned_connection:
                current_connection.close()

    def update_task(
        self,
        task_id: str,
        *,
        status: str | None = None,
        title: str | None = None,
        external_ref: str | None = None,
        issue_number: int | None = None,
        payload_patch: dict[str, Any] | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> ControlTask:
        owned_connection = connection is None
        current_connection = connection or self._connect()
        try:
            updated = self._with_locked_retry(
                lambda: self.tasks.update_task(
                    current_connection,
                    task_id,
                    status=status,
                    title=title,
                    external_ref=external_ref,
                    issue_number=issue_number,
                    payload_patch=payload_patch,
                )
            )
            if owned_connection:
                current_connection.commit()
            return updated
        finally:
            if owned_connection:
                current_connection.close()

    def append_event(
        self,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> ControlTaskEvent:
        owned_connection = connection is None
        current_connection = connection or self._connect()
        try:
            event = self._with_locked_retry(
                lambda: self.events.append(current_connection, task_id, event_type, payload)
            )
            if owned_connection:
                current_connection.commit()
            return event
        finally:
            if owned_connection:
                current_connection.close()

    def append_domain_event(
        self,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> ControlTaskEvent:
        owned_connection = connection is None
        current_connection = connection or self._connect()
        try:
            event = self._with_locked_retry(
                lambda: self.events.append_domain(current_connection, task_id, event_type, payload)
            )
            if owned_connection:
                current_connection.commit()
            return event
        finally:
            if owned_connection:
                current_connection.close()

    def get_task(self, task_id: str, *, connection: sqlite3.Connection | None = None) -> ControlTask:
        owned_connection = connection is None
        current_connection = connection or self._connect()
        try:
            return self.tasks.get_task(current_connection, task_id)
        finally:
            if owned_connection:
                current_connection.close()

    def list_events(self, task_id: str) -> list[ControlTaskEvent]:
        with closing(self._connect()) as connection:
            return self.events.list_events(connection, task_id)

    def find_task_by_external_ref(
        self,
        external_ref: str,
        *,
        task_type: ControlTaskType | None = None,
    ) -> ControlTask | None:
        with closing(self._connect()) as connection:
            return self.tasks.find_task_by_external_ref(
                connection,
                external_ref,
                task_type=task_type,
            )

    def find_parent_for_issue(
        self,
        repo: str,
        issue_number: int,
    ) -> ControlTask | None:
        with closing(self._connect()) as connection:
            return self.tasks.find_parent_for_issue(connection, repo, issue_number)

    def _ensure_parent_dir(self) -> None:
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            fallback_dir = Path(tempfile.gettempdir()) / "youmeng-gateway"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            self.database_path = fallback_dir / self.database_path.name

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize_schema(self) -> None:
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS control_tasks (
                    task_id TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    parent_task_id TEXT,
                    root_task_id TEXT,
                    user_id TEXT,
                    source TEXT,
                    repo TEXT,
                    issue_number INTEGER,
                    title TEXT,
                    external_ref TEXT,
                    payload TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS control_task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES control_tasks(task_id)
                );
                """
            )
            connection.commit()

    def _with_locked_retry(self, operation):
        for attempt in range(self._LOCK_RETRY_ATTEMPTS):
            try:
                return operation()
            except sqlite3.OperationalError as exc:
                if "database is locked" not in str(exc).lower():
                    raise
                if attempt == self._LOCK_RETRY_ATTEMPTS - 1:
                    raise
                time.sleep(self._LOCK_RETRY_DELAY_SECONDS)

    def _get_task_row(self, connection: sqlite3.Connection, task_id: str) -> sqlite3.Row:
        return self.tasks.get_task_row(connection, task_id)

    def _deserialize_task(self, row: sqlite3.Row) -> ControlTask:
        return self.tasks.deserialize_task(row)

    def _deserialize_event(self, row: sqlite3.Row) -> ControlTaskEvent:
        return self.events.deserialize_event(row)
