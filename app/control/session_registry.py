from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from app.control.session_store import SessionStore
from app.core.config import Settings, get_settings
from app.infra.sqlite_utils import connect_sqlite, ensure_writable_parent
from app.models.schemas import ControlSession, ControlSessionType


def build_user_session_external_ref(
    *,
    source: str,
    user_id: str,
    session_key: str | None = None,
) -> str:
    normalized_session_key = session_key.strip() if isinstance(session_key, str) else ""
    if normalized_session_key:
        return normalized_session_key
    return f"{source}:{user_id}"


def build_agent_session_external_ref(*, agent_id: str, user_session_ref: str) -> str:
    return f"{agent_id}:{user_session_ref}"


class SessionRegistryService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.database_path = self.settings.resolved_database_path
        self.store = SessionStore()
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
            session = self.store.get_or_create_session(
                connection,
                session_type=session_type,
                external_ref=external_ref,
                agent_id=agent_id,
                user_id=user_id,
                source=source,
                parent_session_id=parent_session_id,
                payload=payload,
            )
            connection.commit()
            return session

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
            session = self.store.create_child_session(
                connection,
                session_type=session_type,
                parent_session_id=parent_session_id,
                agent_id=agent_id,
                user_id=user_id,
                source=source,
                external_ref=external_ref,
                payload=payload,
            )
            connection.commit()
            return session

    def get_session(self, session_id: str) -> ControlSession:
        with closing(self._connect()) as connection:
            return self.store.get_session(connection, session_id)

    def find_by_external_ref(self, external_ref: str) -> ControlSession | None:
        with closing(self._connect()) as connection:
            return self.store.find_by_external_ref(connection, external_ref)

    def update_session_payload(
        self,
        session_id: str,
        payload_patch: dict[str, Any],
    ) -> ControlSession:
        with closing(self._connect()) as connection:
            updated = self.store.update_payload(connection, session_id, payload_patch)
            connection.commit()
            return updated

    def set_active_agent(
        self,
        session_id: str,
        agent_id: str,
    ) -> ControlSession:
        return self.update_session_payload(
            session_id,
            {
                "active_agent": agent_id,
            },
        )

    def list_session_chain(self, session_id: str) -> list[ControlSession]:
        with closing(self._connect()) as connection:
            return self.store.list_session_chain(connection, session_id)

    def find_inbound_receipt(self, dedupe_key: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT response_payload FROM inbound_receipts WHERE dedupe_key = ?",
                (dedupe_key,),
            ).fetchone()
            if row is None:
                return None
            return self.store.deserialize_json_payload(row["response_payload"])

    def record_inbound_receipt(
        self,
        dedupe_key: str,
        response_payload: dict[str, Any],
    ) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO inbound_receipts (dedupe_key, response_payload)
                VALUES (?, ?)
                ON CONFLICT(dedupe_key) DO UPDATE SET
                    response_payload = excluded.response_payload,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (dedupe_key, self.store.serialize_json_payload(response_payload)),
            )
            connection.commit()
            return response_payload

    def _ensure_parent_dir(self) -> None:
        self.database_path = ensure_writable_parent(self.database_path)

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.database_path)

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

                CREATE TABLE IF NOT EXISTS inbound_receipts (
                    dedupe_key TEXT PRIMARY KEY,
                    response_payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            connection.commit()
