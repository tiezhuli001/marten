from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from app.ledger.service import TokenLedgerService
from app.infra.sqlite_utils import connect_sqlite, ensure_writable_parent
from app.models.schemas import (
    GitExecutionResult,
    SleepCodingIssue,
    SleepCodingPlan,
    SleepCodingPullRequest,
    SleepCodingTask,
    SleepCodingTaskEvent,
    SleepCodingTaskRequest,
    TaskStatus,
    TokenUsage,
    ValidationResult,
)


class SleepCodingTaskStore:
    def __init__(self, database_path: Path, ledger: TokenLedgerService) -> None:
        self.database_path = database_path
        self.ledger = ledger
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
                CREATE TABLE IF NOT EXISTS sleep_coding_tasks (
                    task_id TEXT PRIMARY KEY,
                    control_task_id TEXT,
                    parent_task_id TEXT,
                    issue_number INTEGER NOT NULL,
                    repo TEXT NOT NULL,
                    base_branch TEXT NOT NULL,
                    head_branch TEXT NOT NULL,
                    status TEXT NOT NULL,
                    issue_payload TEXT NOT NULL,
                    plan_payload TEXT,
                    git_execution_payload TEXT NOT NULL,
                    validation_payload TEXT NOT NULL,
                    pr_payload TEXT,
                    kickoff_request_id TEXT,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    background_follow_up_status TEXT NOT NULL DEFAULT 'idle',
                    background_follow_up_error TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES sleep_coding_tasks(task_id)
                );
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(sleep_coding_tasks)")
            }
            if "git_execution_payload" not in columns:
                connection.execute(
                    """
                    ALTER TABLE sleep_coding_tasks
                    ADD COLUMN git_execution_payload TEXT NOT NULL
                    DEFAULT '{"status":"pending","output":"","is_dry_run":true}'
                    """
                )
            for column_name in ("control_task_id", "parent_task_id"):
                if column_name in columns:
                    continue
                connection.execute(
                    f"ALTER TABLE sleep_coding_tasks ADD COLUMN {column_name} TEXT"
                )
            if "background_follow_up_status" not in columns:
                connection.execute(
                    """
                    ALTER TABLE sleep_coding_tasks
                    ADD COLUMN background_follow_up_status TEXT NOT NULL DEFAULT 'idle'
                    """
                )
            if "background_follow_up_error" not in columns:
                connection.execute(
                    """
                    ALTER TABLE sleep_coding_tasks
                    ADD COLUMN background_follow_up_error TEXT
                    """
                )
            connection.commit()

    def insert_task(
        self,
        connection: sqlite3.Connection,
        *,
        task_id: str,
        control_task_id: str | None,
        parent_task_id: str | None,
        payload: SleepCodingTaskRequest,
        repo: str,
        head_branch: str,
        issue: SleepCodingIssue,
        git_execution: GitExecutionResult,
        validation: ValidationResult,
    ) -> None:
        connection.execute(
            """
            INSERT INTO sleep_coding_tasks (
                task_id,
                control_task_id,
                parent_task_id,
                issue_number,
                repo,
                base_branch,
                head_branch,
                status,
                issue_payload,
                git_execution_payload,
                validation_payload,
                kickoff_request_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                control_task_id,
                parent_task_id,
                payload.issue_number,
                repo,
                payload.base_branch,
                head_branch,
                "created",
                issue.model_dump_json(),
                git_execution.model_dump_json(),
                validation.model_dump_json(),
                payload.request_id,
            ),
        )

    def update_status(
        self,
        connection: sqlite3.Connection,
        task_id: str,
        status: TaskStatus,
    ) -> None:
        connection.execute(
            """
            UPDATE sleep_coding_tasks
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
            """,
            (status, task_id),
        )

    def update_task_payloads(
        self,
        connection: sqlite3.Connection,
        task_id: str,
        *,
        status: TaskStatus,
        issue: SleepCodingIssue | None = None,
        plan: SleepCodingPlan | None = None,
        git_execution: GitExecutionResult | None = None,
        validation: ValidationResult | None = None,
        pull_request: SleepCodingPullRequest | None = None,
        last_error: str | None = None,
    ) -> None:
        current = self.get_task_row(connection, task_id)
        connection.execute(
            """
            UPDATE sleep_coding_tasks
            SET status = ?,
                issue_payload = ?,
                plan_payload = ?,
                git_execution_payload = ?,
                validation_payload = ?,
                pr_payload = ?,
                last_error = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
            """,
            (
                status,
                (issue or SleepCodingIssue.model_validate_json(current["issue_payload"])).model_dump_json(),
                plan.model_dump_json() if plan else current["plan_payload"],
                git_execution.model_dump_json() if git_execution else current["git_execution_payload"],
                (validation or ValidationResult.model_validate_json(current["validation_payload"])).model_dump_json(),
                pull_request.model_dump_json() if pull_request else current["pr_payload"],
                last_error,
                task_id,
            ),
        )

    def append_event(
        self,
        connection: sqlite3.Connection,
        task_id: str,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        connection.execute(
            """
            INSERT INTO task_events (task_id, event_type, payload)
            VALUES (?, ?, ?)
            """,
            (task_id, event_type, json.dumps(payload, ensure_ascii=True)),
        )

    def get_task_row(self, connection: sqlite3.Connection, task_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM sleep_coding_tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Task not found: {task_id}")
        return row

    def list_events(
        self,
        connection: sqlite3.Connection,
        task_id: str,
    ) -> list[sqlite3.Row]:
        return connection.execute(
            """
            SELECT id, event_type, payload, created_at
            FROM task_events
            WHERE task_id = ?
            ORDER BY id ASC
            """,
            (task_id,),
        ).fetchall()

    def load_task(self, task_id: str) -> SleepCodingTask:
        with closing(self.connect()) as connection:
            row = self.get_task_row(connection, task_id)
            events = self.list_events(connection, task_id)
        return self.deserialize_task(row, events)

    def deserialize_task(
        self,
        row: sqlite3.Row,
        events: list[sqlite3.Row],
    ) -> SleepCodingTask:
        usage = (
            self.ledger.get_request_usage(row["kickoff_request_id"])
            if row["kickoff_request_id"]
            else TokenUsage(
                prompt_tokens=row["prompt_tokens"],
                completion_tokens=row["completion_tokens"],
                total_tokens=row["total_tokens"],
            )
        )
        return SleepCodingTask(
            task_id=row["task_id"],
            control_task_id=row["control_task_id"],
            parent_task_id=row["parent_task_id"],
            issue_number=row["issue_number"],
            repo=row["repo"],
            base_branch=row["base_branch"],
            head_branch=row["head_branch"],
            status=row["status"],
            issue=SleepCodingIssue.model_validate_json(row["issue_payload"]),
            plan=SleepCodingPlan.model_validate_json(row["plan_payload"]) if row["plan_payload"] else None,
            git_execution=GitExecutionResult.model_validate_json(row["git_execution_payload"]),
            validation=ValidationResult.model_validate_json(row["validation_payload"]),
            pull_request=SleepCodingPullRequest.model_validate_json(row["pr_payload"]) if row["pr_payload"] else None,
            events=[
                SleepCodingTaskEvent(
                    id=event["id"],
                    event_type=event["event_type"],
                    payload=json.loads(event["payload"]),
                    created_at=event["created_at"],
                )
                for event in events
            ],
            prompt_tokens=row["prompt_tokens"],
            completion_tokens=row["completion_tokens"],
            total_tokens=row["total_tokens"],
            token_usage=usage,
            background_follow_up_status=row["background_follow_up_status"],
            background_follow_up_error=row["background_follow_up_error"],
            last_error=row["last_error"],
            kickoff_request_id=row["kickoff_request_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
