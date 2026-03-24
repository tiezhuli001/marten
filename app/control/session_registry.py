from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from app.control.session_store import SessionStore
from app.core.config import Settings, get_settings
from app.infra.sqlite_utils import connect_sqlite, ensure_writable_parent
from app.models.schemas import (
    ControlSession,
    ControlSessionType,
    ExecutionLaneDecision,
    ExecutionLaneSnapshot,
)


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
    _DEFAULT_EXECUTION_LANE = "self_host:default"

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

    def record_session_turn(
        self,
        session_id: str,
        *,
        request_id: str,
        chain_request_id: str,
        intent: str,
        workflow_state: str,
        task_id: str | None,
        source_endpoint_id: str,
        delivery_endpoint_id: str,
        run_session_id: str | None = None,
    ) -> ControlSession:
        return self.update_session_payload(
            session_id,
            {
                "last_request_id": request_id,
                "last_chain_request_id": chain_request_id,
                "last_intent": intent,
                "last_workflow_state": workflow_state,
                "last_task_id": task_id,
                "source_endpoint_id": source_endpoint_id,
                "delivery_endpoint_id": delivery_endpoint_id,
                "last_run_session_id": run_session_id,
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

    def get_execution_lane(
        self,
        lane_key: str | None = None,
    ) -> ExecutionLaneSnapshot:
        target_lane = lane_key or self._DEFAULT_EXECUTION_LANE
        with closing(self._connect()) as connection:
            return self._read_execution_lane(connection, target_lane)

    def acquire_execution_lane(
        self,
        task_id: str,
        *,
        lane_key: str | None = None,
    ) -> ExecutionLaneDecision:
        target_lane = lane_key or self._DEFAULT_EXECUTION_LANE
        with closing(self._connect()) as connection:
            snapshot = self._read_execution_lane(connection, target_lane)
            disposition = "accepted"
            if snapshot.active_task_id and snapshot.active_task_id != task_id:
                disposition = "queued"
                if task_id not in snapshot.queued_task_ids:
                    snapshot.queued_task_ids.append(task_id)
            else:
                snapshot.active_task_id = task_id
                snapshot.queued_task_ids = [queued for queued in snapshot.queued_task_ids if queued != task_id]
            self._write_execution_lane(connection, snapshot)
            connection.commit()
            return ExecutionLaneDecision(disposition=disposition, snapshot=snapshot)

    def release_execution_lane(
        self,
        task_id: str,
        *,
        lane_key: str | None = None,
    ) -> ExecutionLaneDecision:
        target_lane = lane_key or self._DEFAULT_EXECUTION_LANE
        with closing(self._connect()) as connection:
            snapshot = self._read_execution_lane(connection, target_lane)
            if snapshot.active_task_id == task_id:
                snapshot.active_task_id = snapshot.queued_task_ids.pop(0) if snapshot.queued_task_ids else None
            else:
                snapshot.queued_task_ids = [queued for queued in snapshot.queued_task_ids if queued != task_id]
            self._write_execution_lane(connection, snapshot)
            connection.commit()
            return ExecutionLaneDecision(disposition="released", snapshot=snapshot)

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

                CREATE TABLE IF NOT EXISTS execution_lanes (
                    lane_key TEXT PRIMARY KEY,
                    active_task_id TEXT,
                    queued_task_ids TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            connection.commit()

    def _read_execution_lane(
        self,
        connection: sqlite3.Connection,
        lane_key: str,
    ) -> ExecutionLaneSnapshot:
        row = connection.execute(
            """
            SELECT lane_key, active_task_id, queued_task_ids
            FROM execution_lanes
            WHERE lane_key = ?
            """,
            (lane_key,),
        ).fetchone()
        if row is None:
            return ExecutionLaneSnapshot(lane_key=lane_key)
        try:
            queued_task_ids = json.loads(row["queued_task_ids"])
        except json.JSONDecodeError:
            queued_task_ids = []
        if not isinstance(queued_task_ids, list):
            queued_task_ids = []
        return ExecutionLaneSnapshot(
            lane_key=lane_key,
            active_task_id=row["active_task_id"],
            queued_task_ids=[str(item) for item in queued_task_ids if isinstance(item, str) and item],
        )

    def _write_execution_lane(
        self,
        connection: sqlite3.Connection,
        snapshot: ExecutionLaneSnapshot,
    ) -> None:
        connection.execute(
            """
            INSERT INTO execution_lanes (lane_key, active_task_id, queued_task_ids)
            VALUES (?, ?, ?)
            ON CONFLICT(lane_key) DO UPDATE SET
                active_task_id = excluded.active_task_id,
                queued_task_ids = excluded.queued_task_ids,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                snapshot.lane_key,
                snapshot.active_task_id,
                json.dumps(snapshot.queued_task_ids),
            ),
        )
