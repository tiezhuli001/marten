from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.models.schemas import ControlTaskEvent


class TaskEventRecorder:
    def append(
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
        return self.deserialize_event(row)

    def append_domain(
        self,
        connection: sqlite3.Connection,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> ControlTaskEvent:
        return self.append(
            connection,
            task_id,
            event_type,
            {"domain_event": True, **payload},
        )

    def list_events(
        self,
        connection: sqlite3.Connection,
        task_id: str,
    ) -> list[ControlTaskEvent]:
        rows = connection.execute(
            """
            SELECT id, task_id, event_type, payload, created_at
            FROM control_task_events
            WHERE task_id = ?
            ORDER BY id ASC
            """,
            (task_id,),
        ).fetchall()
        return [self.deserialize_event(row) for row in rows]

    def deserialize_event(self, row: sqlite3.Row) -> ControlTaskEvent:
        return ControlTaskEvent(
            event_id=row["id"],
            task_id=row["task_id"],
            event_type=row["event_type"],
            payload=json.loads(row["payload"] or "{}"),
            created_at=row["created_at"],
        )
