from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from app.control.task_events import TaskEventRecorder
from app.control.task_store import TaskStore
from app.core.config import Settings, get_settings
from app.infra.sqlite_utils import connect_sqlite, ensure_writable_parent
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
                    self._build_event_payload(
                        created,
                        {"status": status, **(payload or {})},
                    ),
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
            task = self.tasks.get_task(current_connection, task_id)
            event = self._with_locked_retry(
                lambda: self.events.append(
                    current_connection,
                    task_id,
                    event_type,
                    self._build_event_payload(task, payload),
                )
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
            task = self.tasks.get_task(current_connection, task_id)
            event = self._with_locked_retry(
                lambda: self.events.append_domain(
                    current_connection,
                    task_id,
                    event_type,
                    self._build_event_payload(task, payload),
                )
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

    def find_latest_issue_task(
        self,
        *,
        repo: str,
        issue_number: int,
        task_type: ControlTaskType,
        statuses: set[str] | None = None,
    ) -> ControlTask | None:
        with closing(self._connect()) as connection:
            return self.tasks.find_latest_issue_task(
                connection,
                repo=repo,
                issue_number=issue_number,
                task_type=task_type,
                statuses=statuses,
            )

    def build_recovery_snapshot(self, task_id: str) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            task = self.tasks.get_task(connection, task_id)
            events = self.events.list_events(connection, task_id)
        latest_event = events[-1] if events else None
        recovery_event = self._select_recovery_event(task, events)
        latest_payload = recovery_event.payload if recovery_event is not None else {}
        latest_domain_event = next(
            (event for event in reversed(events) if event.payload.get("domain_event") is True),
            None,
        )
        next_action = self._infer_next_action(task, latest_event_type=recovery_event.event_type if recovery_event else None)
        return {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "status": task.status,
            "owner_agent": self._coerce_string(task.payload, "owner_agent") or task.agent_id,
            "next_owner_agent": (
                self._coerce_string(latest_payload, "next_owner_agent")
                or self._coerce_string(task.payload, "next_owner_agent")
            ),
            "latest_event_type": recovery_event.event_type if recovery_event else None,
            "latest_domain_event_type": latest_domain_event.event_type if latest_domain_event else None,
            "next_action": next_action,
            "domain_task_id": self._coerce_string(latest_payload, "domain_task_id"),
            "child_control_task_id": self._coerce_string(latest_payload, "child_control_task_id"),
            "review_id": self._coerce_string(latest_payload, "review_id"),
            "delivery_endpoint_id": self._coerce_string(task.payload, "delivery_endpoint_id"),
            "last_event_type": latest_event.event_type if latest_event else None,
        }

    def _ensure_parent_dir(self) -> None:
        self.database_path = ensure_writable_parent(self.database_path)

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.database_path)

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

    def _build_event_payload(
        self,
        task: ControlTask,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        base_payload = dict(payload or {})
        metadata = {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "task_status": task.status,
            "agent_id": task.agent_id,
            "parent_task_id": task.parent_task_id,
            "root_task_id": task.root_task_id,
            "task_external_ref": task.external_ref,
        }
        return {**metadata, **base_payload}

    def _infer_next_action(
        self,
        task: ControlTask,
        *,
        latest_event_type: str | None,
    ) -> str:
        if task.status in {"approved", "completed", "cancelled", "failed"}:
            return "none"
        if task.status in {"needs_attention", "timed_out"}:
            return "operator_attention"
        if task.status == "changes_requested":
            return "rerun_coding"
        if task.status == "in_review":
            return "resume_review"
        if task.status in {"planning", "awaiting_confirmation", "coding", "validating", "pr_opened"}:
            return "resume_ralph"
        if task.status == "issue_created":
            if latest_event_type == "delivery.completed":
                return "none"
            return "resume_child_workflow"
        return "resume_task"

    def _coerce_string(self, payload: dict[str, Any], key: str) -> str | None:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
        return None

    def _select_recovery_event(
        self,
        task: ControlTask,
        events: list[ControlTaskEvent],
    ) -> ControlTaskEvent | None:
        if not events:
            return None
        if task.status in {"needs_attention", "timed_out"}:
            for preferred in ("follow_up.failed", "worker_timed_out", "needs_attention"):
                for event in reversed(events):
                    if event.event_type == preferred:
                        return event
        return events[-1]
