from __future__ import annotations

import json
import sqlite3
from typing import Any
from uuid import uuid4

from app.models.schemas import ControlSession, ControlSessionType


class SessionStore:
    def get_or_create_session(
        self,
        connection: sqlite3.Connection,
        *,
        session_type: ControlSessionType,
        external_ref: str,
        agent_id: str | None = None,
        user_id: str | None = None,
        source: str | None = None,
        parent_session_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> ControlSession:
        row = connection.execute(
            "SELECT * FROM control_sessions WHERE external_ref = ? LIMIT 1",
            (external_ref,),
        ).fetchone()
        if row is not None:
            return self.deserialize_session(row)
        session_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO control_sessions (
                session_id, session_type, agent_id, user_id, source,
                parent_session_id, external_ref, status, payload
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)
            """,
            (
                session_id,
                session_type,
                agent_id,
                user_id,
                source,
                parent_session_id,
                external_ref,
                json.dumps(payload or {}, ensure_ascii=True),
            ),
        )
        created = connection.execute(
            "SELECT * FROM control_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if created is None:
            raise ValueError("Failed to create control session")
        return self.deserialize_session(created)

    def create_child_session(
        self,
        connection: sqlite3.Connection,
        *,
        session_type: ControlSessionType,
        parent_session_id: str | None,
        agent_id: str | None = None,
        user_id: str | None = None,
        source: str | None = None,
        external_ref: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> ControlSession:
        session_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO control_sessions (
                session_id, session_type, agent_id, user_id, source,
                parent_session_id, external_ref, status, payload
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)
            """,
            (
                session_id,
                session_type,
                agent_id,
                user_id,
                source,
                parent_session_id,
                external_ref,
                json.dumps(payload or {}, ensure_ascii=True),
            ),
        )
        row = connection.execute(
            "SELECT * FROM control_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise ValueError("Failed to create child control session")
        return self.deserialize_session(row)

    def get_session(self, connection: sqlite3.Connection, session_id: str) -> ControlSession:
        row = connection.execute(
            "SELECT * FROM control_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Control session not found: {session_id}")
        return self.deserialize_session(row)

    def find_by_external_ref(
        self,
        connection: sqlite3.Connection,
        external_ref: str,
    ) -> ControlSession | None:
        row = connection.execute(
            "SELECT * FROM control_sessions WHERE external_ref = ? LIMIT 1",
            (external_ref,),
        ).fetchone()
        return self.deserialize_session(row) if row is not None else None

    def update_payload(
        self,
        connection: sqlite3.Connection,
        session_id: str,
        payload_patch: dict[str, Any],
    ) -> ControlSession:
        row = connection.execute(
            "SELECT * FROM control_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Control session not found: {session_id}")
        current_payload = json.loads(row["payload"] or "{}")
        updated_payload = {**current_payload, **payload_patch}
        connection.execute(
            """
            UPDATE control_sessions
            SET payload = ?, updated_at = CURRENT_TIMESTAMP
            WHERE session_id = ?
            """,
            (json.dumps(updated_payload, ensure_ascii=True), session_id),
        )
        return self.get_session(connection, session_id)

    def list_session_chain(
        self,
        connection: sqlite3.Connection,
        session_id: str,
    ) -> list[ControlSession]:
        sessions: list[ControlSession] = []
        current = self.get_session(connection, session_id)
        sessions.append(current)
        while current.parent_session_id:
            current = self.get_session(connection, current.parent_session_id)
            sessions.append(current)
        sessions.reverse()
        return sessions

    def deserialize_session(self, row: sqlite3.Row) -> ControlSession:
        return ControlSession(
            session_id=row["session_id"],
            session_type=row["session_type"],
            agent_id=row["agent_id"],
            user_id=row["user_id"],
            source=row["source"],
            parent_session_id=row["parent_session_id"],
            external_ref=row["external_ref"],
            status=row["status"],
            payload=json.loads(row["payload"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
