from __future__ import annotations

import json
import sqlite3
from typing import Any
from uuid import uuid4

from app.models.schemas import ControlTask, ControlTaskType


class TaskStore:
    def create_task(
        self,
        connection: sqlite3.Connection,
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
    ) -> ControlTask:
        task_id = str(uuid4())
        root_task_id = parent_task_id
        if parent_task_id:
            parent = self.get_task_row(connection, parent_task_id)
            root_task_id = parent["root_task_id"] or parent["task_id"]
        connection.execute(
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
        return self.deserialize_task(self.get_task_row(connection, task_id))

    def update_task(
        self,
        connection: sqlite3.Connection,
        task_id: str,
        *,
        status: str | None = None,
        title: str | None = None,
        external_ref: str | None = None,
        issue_number: int | None = None,
        payload_patch: dict[str, Any] | None = None,
    ) -> ControlTask:
        row = self.get_task_row(connection, task_id)
        current_payload = json.loads(row["payload"] or "{}")
        updated_payload = {**current_payload, **(payload_patch or {})}
        connection.execute(
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
        return self.deserialize_task(self.get_task_row(connection, task_id))

    def get_task(self, connection: sqlite3.Connection, task_id: str) -> ControlTask:
        return self.deserialize_task(self.get_task_row(connection, task_id))

    def find_task_by_external_ref(
        self,
        connection: sqlite3.Connection,
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
        row = connection.execute(query, tuple(params)).fetchone()
        return self.deserialize_task(row) if row else None

    def find_parent_for_issue(
        self,
        connection: sqlite3.Connection,
        repo: str,
        issue_number: int,
    ) -> ControlTask | None:
        return self.find_task_by_external_ref(
            connection,
            f"github_issue:{repo}#{issue_number}",
            task_type="main_agent_intake",
        )

    def find_latest_issue_task(
        self,
        connection: sqlite3.Connection,
        *,
        repo: str,
        issue_number: int,
        task_type: ControlTaskType,
        statuses: set[str] | None = None,
    ) -> ControlTask | None:
        query = [
            "SELECT * FROM control_tasks",
            "WHERE repo = ? AND issue_number = ? AND task_type = ?",
        ]
        params: list[Any] = [repo, issue_number, task_type]
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            query.append(f"AND status IN ({placeholders})")
            params.extend(sorted(statuses))
        query.append("ORDER BY datetime(created_at) DESC, rowid DESC LIMIT 1")
        row = connection.execute(" ".join(query), tuple(params)).fetchone()
        return self.deserialize_task(row) if row else None

    def find_latest_task(
        self,
        connection: sqlite3.Connection,
        *,
        task_type: ControlTaskType | None = None,
        statuses: set[str] | None = None,
    ) -> ControlTask | None:
        query = ["SELECT * FROM control_tasks WHERE 1 = 1"]
        params: list[Any] = []
        if task_type is not None:
            query.append("AND task_type = ?")
            params.append(task_type)
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            query.append(f"AND status IN ({placeholders})")
            params.extend(sorted(statuses))
        query.append("ORDER BY datetime(created_at) DESC, rowid DESC LIMIT 1")
        row = connection.execute(" ".join(query), tuple(params)).fetchone()
        return self.deserialize_task(row) if row else None

    def get_task_row(self, connection: sqlite3.Connection, task_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM control_tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Control task not found: {task_id}")
        return row

    def deserialize_task(self, row: sqlite3.Row | None) -> ControlTask:
        if row is None:
            raise ValueError("Control task row is required")
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
