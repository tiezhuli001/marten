from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from app.infra.sqlite_utils import connect_sqlite, ensure_writable_parent
from app.models.schemas import SleepCodingTask, SleepCodingWorkerClaim, WorkerDiscoveredIssue


class SleepCodingWorkerStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.ensure_parent_dir()
        self.initialize_schema()

    def ensure_parent_dir(self) -> None:
        self.database_path = ensure_writable_parent(self.database_path)

    def connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.database_path)

    def initialize_schema(self) -> None:
        with closing(self.connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sleep_coding_issue_claims (
                    repo TEXT NOT NULL,
                    issue_number INTEGER NOT NULL,
                    task_id TEXT,
                    status TEXT NOT NULL,
                    title TEXT NOT NULL,
                    html_url TEXT,
                    labels_payload TEXT NOT NULL DEFAULT '[]',
                    worker_id TEXT,
                    lease_expires_at TEXT,
                    last_heartbeat_at TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    next_retry_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (repo, issue_number)
                );
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(sleep_coding_issue_claims)")
            }
            for column_name, ddl in (
                ("lease_expires_at", "ALTER TABLE sleep_coding_issue_claims ADD COLUMN lease_expires_at TEXT"),
                ("last_heartbeat_at", "ALTER TABLE sleep_coding_issue_claims ADD COLUMN last_heartbeat_at TEXT"),
                ("retry_count", "ALTER TABLE sleep_coding_issue_claims ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0"),
                ("next_retry_at", "ALTER TABLE sleep_coding_issue_claims ADD COLUMN next_retry_at TEXT"),
                ("last_error", "ALTER TABLE sleep_coding_issue_claims ADD COLUMN last_error TEXT"),
            ):
                if column_name not in columns:
                    connection.execute(ddl)
            connection.commit()

    def record_discovered_issue(
        self,
        connection: sqlite3.Connection,
        repo: str,
        worker_id: str,
        issue: WorkerDiscoveredIssue,
    ) -> None:
        connection.execute(
            """
            INSERT INTO sleep_coding_issue_claims (
                repo,
                issue_number,
                task_id,
                status,
                title,
                html_url,
                labels_payload,
                worker_id,
                updated_at
            )
            VALUES (?, ?, NULL, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(repo, issue_number) DO UPDATE SET
                title = excluded.title,
                html_url = excluded.html_url,
                labels_payload = excluded.labels_payload,
                worker_id = excluded.worker_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                repo,
                issue.issue_number,
                "discovered",
                issue.title,
                issue.html_url,
                json.dumps(issue.labels, ensure_ascii=True),
                worker_id,
            ),
        )
        connection.execute(
            """
            UPDATE sleep_coding_issue_claims
            SET status = CASE WHEN status = 'timed_out' THEN 'discovered' ELSE status END,
                updated_at = CURRENT_TIMESTAMP
            WHERE repo = ? AND issue_number = ? AND status = 'timed_out'
            """,
            (repo, issue.issue_number),
        )

    def mark_claim_status(
        self,
        connection: sqlite3.Connection,
        repo: str,
        issue_number: int,
        status: str,
    ) -> None:
        connection.execute(
            """
            UPDATE sleep_coding_issue_claims
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE repo = ? AND issue_number = ?
            """,
            (status, repo, issue_number),
        )

    def attach_task_to_claim(
        self,
        connection: sqlite3.Connection,
        repo: str,
        worker_id: str,
        issue: WorkerDiscoveredIssue,
        task: SleepCodingTask,
        status: str,
    ) -> None:
        connection.execute(
            """
            UPDATE sleep_coding_issue_claims
            SET task_id = ?,
                status = ?,
                title = ?,
                html_url = ?,
                labels_payload = ?,
                worker_id = ?,
                lease_expires_at = NULL,
                last_heartbeat_at = CURRENT_TIMESTAMP,
                last_error = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE repo = ? AND issue_number = ?
            """,
            (
                task.task_id,
                status,
                issue.title,
                issue.html_url,
                json.dumps(issue.labels, ensure_ascii=True),
                worker_id,
                repo,
                issue.issue_number,
            ),
        )

    def list_claims(
        self,
        connection: sqlite3.Connection,
        repo: str,
    ) -> list[SleepCodingWorkerClaim]:
        rows = connection.execute(
            """
            SELECT repo, issue_number, task_id, status, title, html_url, labels_payload, worker_id,
                   lease_expires_at, last_heartbeat_at, retry_count, next_retry_at, last_error, created_at, updated_at
            FROM sleep_coding_issue_claims
            WHERE repo = ?
            ORDER BY issue_number DESC
            """,
            (repo,),
        ).fetchall()
        return [
            SleepCodingWorkerClaim(
                repo=row["repo"],
                issue_number=row["issue_number"],
                task_id=row["task_id"],
                status=row["status"],
                title=row["title"],
                html_url=row["html_url"],
                labels=json.loads(row["labels_payload"]),
                worker_id=row["worker_id"],
                lease_expires_at=row["lease_expires_at"],
                last_heartbeat_at=row["last_heartbeat_at"],
                retry_count=row["retry_count"],
                next_retry_at=row["next_retry_at"],
                last_error=row["last_error"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def acquire_lease(
        self,
        connection: sqlite3.Connection,
        repo: str,
        issue_number: int,
        worker_id: str,
        *,
        lease_expires_at: str,
        heartbeat_at: str,
    ) -> None:
        connection.execute(
            """
            UPDATE sleep_coding_issue_claims
            SET status = 'claimed',
                worker_id = ?,
                lease_expires_at = ?,
                last_heartbeat_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE repo = ? AND issue_number = ?
            """,
            (worker_id, lease_expires_at, heartbeat_at, repo, issue_number),
        )

    def heartbeat(
        self,
        connection: sqlite3.Connection,
        repo: str,
        issue_number: int,
        worker_id: str,
        *,
        lease_expires_at: str,
        heartbeat_at: str,
    ) -> None:
        connection.execute(
            """
            UPDATE sleep_coding_issue_claims
            SET worker_id = ?,
                lease_expires_at = ?,
                last_heartbeat_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE repo = ? AND issue_number = ?
            """,
            (worker_id, lease_expires_at, heartbeat_at, repo, issue_number),
        )

    def release_lease(
        self,
        connection: sqlite3.Connection,
        repo: str,
        issue_number: int,
        status: str,
    ) -> None:
        connection.execute(
            """
            UPDATE sleep_coding_issue_claims
            SET status = ?, lease_expires_at = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE repo = ? AND issue_number = ?
            """,
            (status, repo, issue_number),
        )

    def record_failure(
        self,
        connection: sqlite3.Connection,
        repo: str,
        issue_number: int,
        worker_id: str,
        error_text: str,
        *,
        retry_count: int,
        next_retry_at: str,
        status: str,
    ) -> None:
        connection.execute(
            """
            UPDATE sleep_coding_issue_claims
            SET status = ?,
                worker_id = ?,
                lease_expires_at = NULL,
                retry_count = ?,
                next_retry_at = ?,
                last_error = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE repo = ? AND issue_number = ?
            """,
            (status, worker_id, retry_count, next_retry_at, error_text[:500], repo, issue_number),
        )

    def get_retry_state(
        self,
        connection: sqlite3.Connection,
        repo: str,
        issue_number: int,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT status, next_retry_at, retry_count
            FROM sleep_coding_issue_claims
            WHERE repo = ? AND issue_number = ?
            """,
            (repo, issue_number),
        ).fetchone()

    def expire_claim(
        self,
        connection: sqlite3.Connection,
        repo: str,
        issue_number: int,
    ) -> None:
        connection.execute(
            """
            UPDATE sleep_coding_issue_claims
            SET status = 'timed_out',
                lease_expires_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE repo = ? AND issue_number = ?
            """,
            (repo, issue_number),
        )

    def parse_dt(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
