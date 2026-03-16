from __future__ import annotations

import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from app.core.config import Settings
from app.models.schemas import IntentType, TokenUsage


class TokenLedgerService:
    def __init__(self, settings: Settings) -> None:
        self.database_path = settings.resolved_database_path
        self._ensure_parent_dir()
        self._initialize_schema()

    def _ensure_parent_dir(self) -> None:
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            # Keep project-local storage as the default. Only fall back in restricted
            # environments like the current sandbox, where the repo path is read-only.
            fallback_dir = Path(tempfile.gettempdir()) / "youmeng-gateway"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            self.database_path = fallback_dir / self.database_path.name

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_schema(self) -> None:
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS requests (
                    request_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS workflow_runs (
                    run_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (request_id) REFERENCES requests(request_id)
                );

                CREATE TABLE IF NOT EXISTS token_usage_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    prompt_tokens INTEGER NOT NULL,
                    completion_tokens INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (request_id) REFERENCES requests(request_id),
                    FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id)
                );
                """
            )
            connection.commit()

    def record_request(
        self,
        request_id: str,
        run_id: str,
        user_id: str,
        source: str,
        intent: IntentType,
        content: str,
    ) -> TokenUsage:
        usage = TokenUsage()
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO requests (request_id, user_id, source, intent, content)
                VALUES (?, ?, ?, ?, ?)
                """,
                (request_id, user_id, source, intent, content),
            )
            connection.execute(
                """
                INSERT INTO workflow_runs (run_id, request_id, status)
                VALUES (?, ?, ?)
                """,
                (run_id, request_id, "completed"),
            )
            connection.execute(
                """
                INSERT INTO token_usage_records (
                    request_id,
                    run_id,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    run_id,
                    usage.prompt_tokens,
                    usage.completion_tokens,
                    usage.total_tokens,
                ),
            )
            connection.commit()
        return usage

    def get_usage_summary(self, query: str) -> str:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(DISTINCT request_id) AS request_count,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens
                FROM token_usage_records
                """
            ).fetchone()

        period = "all"
        if "最近7天" in query or "7天" in query:
            period = "7d"
        if "最近30天" in query or "30天" in query:
            period = "30d"

        return (
            f"Token ledger is initialized. Period={period}, "
            f"requests={row['request_count']}, total_tokens={row['total_tokens']}."
        )

    def get_request_usage(self, request_id: str) -> TokenUsage:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT
                    COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens
                FROM token_usage_records
                WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()

        return TokenUsage(
            prompt_tokens=row["prompt_tokens"],
            completion_tokens=row["completion_tokens"],
            total_tokens=row["total_tokens"],
        )
