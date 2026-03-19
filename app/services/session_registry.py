from __future__ import annotations

import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any

from app.control.session_store import SessionStore
from app.core.config import Settings, get_settings
from app.models.schemas import ControlSession, ControlSessionType


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

    def list_session_chain(self, session_id: str) -> list[ControlSession]:
        with closing(self._connect()) as connection:
            return self.store.list_session_chain(connection, session_id)

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
