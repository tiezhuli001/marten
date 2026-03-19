from __future__ import annotations

import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import Settings, get_settings
from app.models.schemas import ControlSession, ControlSessionType


class SessionRegistryService:
    _SHORT_MEMORY_LIMIT = 5

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.database_path = self.settings.resolved_database_path
        self._ensure_parent_dir()
        self._initialize_schema()

    def get_or_create_session(
        self,
        *,
        session_type: ControlSessionType,
        external_ref: str,
        agent_id: str | None = None,
        user_id: str | None = None,
        source: str | None = None,
        parent_session_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> ControlSession:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM control_sessions WHERE external_ref = ? LIMIT 1",
                (external_ref,),
            ).fetchone()
            if row is not None:
                return self._deserialize_session(row)
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
            connection.commit()
            created = connection.execute(
                "SELECT * FROM control_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if created is None:
            raise ValueError("Failed to create control session")
        return self._deserialize_session(created)

    def create_child_session(
        self,
        *,
        session_type: ControlSessionType,
        parent_session_id: str | None,
        agent_id: str | None = None,
        user_id: str | None = None,
        source: str | None = None,
        external_ref: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> ControlSession:
        with closing(self._connect()) as connection:
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
            connection.commit()
            row = connection.execute(
                "SELECT * FROM control_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            raise ValueError("Failed to create child control session")
        return self._deserialize_session(row)

    def get_session(self, session_id: str) -> ControlSession:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM control_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"Control session not found: {session_id}")
        return self._deserialize_session(row)

    def find_by_external_ref(self, external_ref: str) -> ControlSession | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM control_sessions WHERE external_ref = ? LIMIT 1",
                (external_ref,),
            ).fetchone()
        return self._deserialize_session(row) if row is not None else None

    def update_session_payload(
        self,
        session_id: str,
        payload_patch: dict[str, Any],
    ) -> ControlSession:
        with closing(self._connect()) as connection:
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
            connection.commit()
        return self.get_session(session_id)

    def list_session_chain(self, session_id: str) -> list[ControlSession]:
        sessions: list[ControlSession] = []
        current = self.get_session(session_id)
        sessions.append(current)
        while current.parent_session_id:
            current = self.get_session(current.parent_session_id)
            sessions.append(current)
        sessions.reverse()
        return sessions

    def append_short_memory(
        self,
        session_id: str,
        summary: str,
    ) -> ControlSession:
        normalized = " ".join(summary.strip().split())
        if not normalized:
            return self.get_session(session_id)
        session = self.get_session(session_id)
        current_entries = session.payload.get("short_memory_entries")
        entries = (
            [str(item).strip() for item in current_entries if isinstance(item, str) and str(item).strip()]
            if isinstance(current_entries, list)
            else []
        )
        entries.append(normalized[:500])
        trimmed = entries[-self._SHORT_MEMORY_LIMIT :]
        return self.update_session_payload(
            session_id,
            {
                "short_memory_summary": trimmed[-1],
                "short_memory_entries": trimmed,
            },
        )

    def list_short_memory(self, session_id: str | None) -> list[str]:
        if not session_id:
            return []
        chain = self.list_session_chain(session_id)
        summaries: list[str] = []
        for session in chain:
            raw_entries = session.payload.get("short_memory_entries")
            if isinstance(raw_entries, list):
                for item in raw_entries:
                    if isinstance(item, str) and item.strip():
                        summaries.append(item.strip())
                continue
            summary = session.payload.get("short_memory_summary")
            if isinstance(summary, str) and summary.strip():
                summaries.append(summary.strip())
        return summaries

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
                CREATE TABLE IF NOT EXISTS control_sessions (
                    session_id TEXT PRIMARY KEY,
                    session_type TEXT NOT NULL,
                    agent_id TEXT,
                    user_id TEXT,
                    source TEXT,
                    parent_session_id TEXT,
                    external_ref TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    payload TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            connection.commit()

    def _deserialize_session(self, row: sqlite3.Row) -> ControlSession:
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
