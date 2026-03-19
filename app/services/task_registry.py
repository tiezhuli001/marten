from __future__ import annotations

import json
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import Settings, get_settings
from app.models.schemas import ControlTask, ControlTaskEvent, ControlTaskType


class TaskRegistryService:
    _LOCK_RETRY_ATTEMPTS = 5
    _LOCK_RETRY_DELAY_SECONDS = 0.2

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.database_path = self.settings.resolved_database_path
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
        task_id = str(uuid4())
        owned_connection = connection is None
        current_connection = connection or self._connect()
        try:
            def _create() -> None:
                root_task_id = parent_task_id
                if parent_task_id:
                    parent = self._get_task_row(current_connection, parent_task_id)
                    root_task_id = parent["root_task_id"] or parent["task_id"]
                current_connection.execute(
                    """
                    INSERT INTO control_tasks (
                        task_id, task_type, agent_id, status, parent_task_id, root_task_id,
                        user_id, source, repo, issue_number, title, external_ref, payload
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        task_type,
                        agent_id,
                        status,
                        parent_task_id,
                        root_task_id,
                        user_id,
                        source,
                        repo,
                        issue_number,
                        title,
                        external_ref,
                        json.dumps(payload or {}, ensure_ascii=True),
                    ),
                )
                self._append_event(
                    current_connection,
                    task_id,
                    "task_created",
                    {"status": status, **(payload or {})},
                )

            self._with_locked_retry(_create)
            if owned_connection:
                current_connection.commit()
            row = self._get_task_row(current_connection, task_id)
            return self._deserialize_task(row)
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
            row = self._get_task_row(current_connection, task_id)
            current_payload = json.loads(row["payload"] or "{}")
            updated_payload = {**current_payload, **(payload_patch or {})}
            self._with_locked_retry(
                lambda: current_connection.execute(
                    """
                    UPDATE control_tasks
                    SET status = ?, title = ?, external_ref = ?, issue_number = ?, payload = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE task_id = ?
                    """,
                    (
                        status or row["status"],
                        title if title is not None else row["title"],
                        external_ref if external_ref is not None else row["external_ref"],
                        issue_number if issue_number is not None else row["issue_number"],
                        json.dumps(updated_payload, ensure_ascii=True),
                        task_id,
                    ),
                )
            )
            if owned_connection:
                current_connection.commit()
            updated = self._get_task_row(current_connection, task_id)
            return self._deserialize_task(updated)
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
                lambda: self._append_event(current_connection, task_id, event_type, payload)
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
        return self.append_event(
            task_id,
            event_type,
            {
                "domain_event": True,
                **payload,
            },
            connection=connection,
        )

    def get_task(self, task_id: str, *, connection: sqlite3.Connection | None = None) -> ControlTask:
        owned_connection = connection is None
        current_connection = connection or self._connect()
        try:
            return self._deserialize_task(self._get_task_row(current_connection, task_id))
        finally:
            if owned_connection:
                current_connection.close()

    def list_events(self, task_id: str) -> list[ControlTaskEvent]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT id, task_id, event_type, payload, created_at
                FROM control_task_events
                WHERE task_id = ?
                ORDER BY id ASC
                """,
                (task_id,),
            ).fetchall()
        return [self._deserialize_event(row) for row in rows]

    def find_task_by_external_ref(
        self,
        external_ref: str,
        *,
        task_type: ControlTaskType | None = None,
    ) -> ControlTask | None:
        query = "SELECT * FROM control_tasks WHERE external_ref = ?"
        params: list[Any] = [external_ref]
        if task_type:
            query += " AND task_type = ?"
            params.append(task_type)
        query += " ORDER BY created_at DESC LIMIT 1"
        with closing(self._connect()) as connection:
            row = connection.execute(query, tuple(params)).fetchone()
        return self._deserialize_task(row) if row else None

    def find_parent_for_issue(
        self,
        repo: str,
        issue_number: int,
    ) -> ControlTask | None:
        return self.find_task_by_external_ref(
            f"github_issue:{repo}#{issue_number}",
            task_type="main_agent_intake",
        )

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

    def _append_event(
        self,
        connection: sqlite3.Connection,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> ControlTaskEvent:
        cursor = connection.execute(
            """
            INSERT INTO control_task_events (task_id, event_type, payload)
            VALUES (?, ?, ?)
            """,
            (task_id, event_type, json.dumps(payload, ensure_ascii=True)),
        )
        row = connection.execute(
            """
            SELECT id, task_id, event_type, payload, created_at
            FROM control_task_events
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
        if row is None:
            raise ValueError("Failed to load appended control task event")
        return self._deserialize_event(row)

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
        row = connection.execute(
            "SELECT * FROM control_tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Control task not found: {task_id}")
        return row

    def _deserialize_task(self, row: sqlite3.Row) -> ControlTask:
        return ControlTask(
            task_id=row["task_id"],
            task_type=row["task_type"],
            agent_id=row["agent_id"],
            status=row["status"],
            parent_task_id=row["parent_task_id"],
            root_task_id=row["root_task_id"],
            user_id=row["user_id"],
            source=row["source"],
            repo=row["repo"],
            issue_number=row["issue_number"],
            title=row["title"],
            external_ref=row["external_ref"],
            payload=json.loads(row["payload"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _deserialize_event(self, row: sqlite3.Row) -> ControlTaskEvent:
        return ControlTaskEvent(
            event_id=row["id"],
            task_id=row["task_id"],
            event_type=row["event_type"],
            payload=json.loads(row["payload"] or "{}"),
            created_at=row["created_at"],
        )
