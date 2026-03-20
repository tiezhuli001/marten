from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

from app.core.config import Settings
from app.infra.sqlite_utils import connect_sqlite, ensure_writable_parent
from app.models.schemas import (
    DailyTokenSummary,
    IntentType,
    TokenReportResponse,
    TokenUsage,
    TokenUsageBreakdown,
    TokenWindowSummary,
)


class TokenLedgerService:
    _MIGRATION_COLUMNS: dict[str, set[str]] = {
        "token_usage_records": {
            "model_name",
            "provider",
            "cost_usd",
            "step_name",
            "cache_read_tokens",
            "cache_write_tokens",
            "reasoning_tokens",
            "message_count",
            "duration_seconds",
        },
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.database_path = settings.resolved_database_path
        self._ensure_parent_dir()
        self._initialize_schema()

    def _ensure_parent_dir(self) -> None:
        self.database_path = ensure_writable_parent(self.database_path)

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.database_path)

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
                    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
                    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
                    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    duration_seconds REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (request_id) REFERENCES requests(request_id),
                    FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS daily_token_summaries (
                    summary_date TEXT PRIMARY KEY,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    workflow_run_count INTEGER NOT NULL DEFAULT 0,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_cost_usd REAL NOT NULL DEFAULT 0,
                    top_intent TEXT,
                    top_step_name TEXT,
                    summary_text TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            self._ensure_columns(
                connection,
                table_name="token_usage_records",
                columns={
                    "model_name": "TEXT",
                    "provider": "TEXT",
                    "cost_usd": "REAL NOT NULL DEFAULT 0",
                    "step_name": "TEXT",
                    "cache_read_tokens": "INTEGER NOT NULL DEFAULT 0",
                    "cache_write_tokens": "INTEGER NOT NULL DEFAULT 0",
                    "reasoning_tokens": "INTEGER NOT NULL DEFAULT 0",
                    "message_count": "INTEGER NOT NULL DEFAULT 0",
                    "duration_seconds": "REAL NOT NULL DEFAULT 0",
                },
            )
            connection.commit()

    def _ensure_columns(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        columns: dict[str, str],
    ) -> None:
        self._validate_schema_targets(table_name, columns)
        existing_columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        for column_name, definition in columns.items():
            if column_name in existing_columns:
                continue
            connection.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
            )

    def _validate_schema_targets(
        self,
        table_name: str,
        columns: dict[str, str],
    ) -> None:
        allowed_columns = self._MIGRATION_COLUMNS.get(table_name)
        if allowed_columns is None:
            raise ValueError(f"Unsupported schema migration table: {table_name}")
        invalid_columns = sorted(set(columns) - allowed_columns)
        if invalid_columns:
            raise ValueError(
                "Unsupported schema migration columns for "
                f"{table_name}: {', '.join(invalid_columns)}"
            )

    def record_request(
        self,
        request_id: str,
        run_id: str,
        user_id: str,
        source: str,
        intent: IntentType,
        content: str,
        usage: TokenUsage | None = None,
        created_at: str | None = None,
        step_name: str | None = None,
    ) -> TokenUsage:
        usage = usage or TokenUsage(step_name=step_name)
        created_value = created_at or "CURRENT_TIMESTAMP"
        request_query = (
            """
            INSERT INTO requests (request_id, user_id, source, intent, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """
            if created_at
            else """
            INSERT INTO requests (request_id, user_id, source, intent, content)
            VALUES (?, ?, ?, ?, ?)
            """
        )
        workflow_query = (
            """
            INSERT INTO workflow_runs (run_id, request_id, status, created_at)
            VALUES (?, ?, ?, ?)
            """
            if created_at
            else """
            INSERT INTO workflow_runs (run_id, request_id, status)
            VALUES (?, ?, ?)
            """
        )
        token_query = (
            """
            INSERT INTO token_usage_records (
                request_id,
                run_id,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                cache_read_tokens,
                cache_write_tokens,
                reasoning_tokens,
                message_count,
                duration_seconds,
                model_name,
                provider,
                cost_usd,
                step_name,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            if created_at
            else """
            INSERT INTO token_usage_records (
                request_id,
                run_id,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                cache_read_tokens,
                cache_write_tokens,
                reasoning_tokens,
                message_count,
                duration_seconds,
                model_name,
                provider,
                cost_usd,
                step_name
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
        )

        with closing(self._connect()) as connection:
            request_params: tuple[object, ...] = (
                request_id,
                user_id,
                source,
                intent,
                content,
                created_value,
            ) if created_at else (
                request_id,
                user_id,
                source,
                intent,
                content,
            )
            workflow_params: tuple[object, ...] = (
                run_id,
                request_id,
                "completed",
                created_value,
            ) if created_at else (
                run_id,
                request_id,
                "completed",
            )
            token_params: tuple[object, ...] = (
                request_id,
                run_id,
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.total_tokens,
                usage.cache_read_tokens,
                usage.cache_write_tokens,
                usage.reasoning_tokens,
                usage.message_count,
                usage.duration_seconds,
                usage.model_name,
                usage.provider,
                usage.cost_usd,
                usage.step_name or step_name,
                created_value,
            ) if created_at else (
                request_id,
                run_id,
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.total_tokens,
                usage.cache_read_tokens,
                usage.cache_write_tokens,
                usage.reasoning_tokens,
                usage.message_count,
                usage.duration_seconds,
                usage.model_name,
                usage.provider,
                usage.cost_usd,
                usage.step_name or step_name,
            )
            connection.execute(request_query, request_params)
            connection.execute(workflow_query, workflow_params)
            connection.execute(token_query, token_params)
            connection.commit()
        return usage

    def append_usage(
        self,
        *,
        request_id: str,
        run_id: str,
        usage: TokenUsage,
        step_name: str | None = None,
        created_at: str | None = None,
    ) -> TokenUsage:
        created_value = created_at or "CURRENT_TIMESTAMP"
        workflow_query = (
            """
            INSERT OR IGNORE INTO workflow_runs (run_id, request_id, status, created_at)
            VALUES (?, ?, ?, ?)
            """
            if created_at
            else """
            INSERT OR IGNORE INTO workflow_runs (run_id, request_id, status)
            VALUES (?, ?, ?)
            """
        )
        token_query = (
            """
            INSERT INTO token_usage_records (
                request_id,
                run_id,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                cache_read_tokens,
                cache_write_tokens,
                reasoning_tokens,
                message_count,
                duration_seconds,
                model_name,
                provider,
                cost_usd,
                step_name,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            if created_at
            else """
            INSERT INTO token_usage_records (
                request_id,
                run_id,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                cache_read_tokens,
                cache_write_tokens,
                reasoning_tokens,
                message_count,
                duration_seconds,
                model_name,
                provider,
                cost_usd,
                step_name
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
        )
        with closing(self._connect()) as connection:
            request_row = connection.execute(
                "SELECT 1 FROM requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if request_row is None:
                raise ValueError(f"Request not found: {request_id}")
            workflow_params: tuple[object, ...] = (
                run_id,
                request_id,
                "completed",
                created_value,
            ) if created_at else (
                run_id,
                request_id,
                "completed",
            )
            token_params: tuple[object, ...] = (
                request_id,
                run_id,
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.total_tokens,
                usage.cache_read_tokens,
                usage.cache_write_tokens,
                usage.reasoning_tokens,
                usage.message_count,
                usage.duration_seconds,
                usage.model_name,
                usage.provider,
                usage.cost_usd,
                usage.step_name or step_name,
                created_value,
            ) if created_at else (
                request_id,
                run_id,
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.total_tokens,
                usage.cache_read_tokens,
                usage.cache_write_tokens,
                usage.reasoning_tokens,
                usage.message_count,
                usage.duration_seconds,
                usage.model_name,
                usage.provider,
                usage.cost_usd,
                usage.step_name or step_name,
            )
            connection.execute(workflow_query, workflow_params)
            connection.execute(token_query, token_params)
            connection.commit()
        return usage

    def get_usage_summary(self, query: str) -> str:
        if "昨天" in query or "昨日" in query:
            summary = self.generate_yesterday_summary()
            return summary.summary_text
        if "最近30天" in query or "30天" in query:
            return self.get_window_report("30d").summary_text
        if "最近7天" in query or "7天" in query:
            return self.get_window_report("7d").summary_text
        return self.get_window_report("7d").summary_text

    def get_request_usage(
        self,
        request_id: str,
        step_names: list[str] | None = None,
    ) -> TokenUsage:
        filters = ["request_id = ?"]
        params: list[object] = [request_id]
        if step_names:
            placeholders = ", ".join("?" for _ in step_names)
            filters.append(f"step_name IN ({placeholders})")
            params.extend(step_names)
        with closing(self._connect()) as connection:
            row = connection.execute(
                f"""
                SELECT
                    COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(cache_read_tokens), 0) AS cache_read_tokens,
                    COALESCE(SUM(cache_write_tokens), 0) AS cache_write_tokens,
                    COALESCE(SUM(reasoning_tokens), 0) AS reasoning_tokens,
                    COALESCE(SUM(message_count), 0) AS message_count,
                    COALESCE(SUM(duration_seconds), 0) AS duration_seconds,
                    CASE WHEN COUNT(DISTINCT model_name) = 1 THEN MAX(model_name) END AS model_name,
                    CASE WHEN COUNT(DISTINCT provider) = 1 THEN MAX(provider) END AS provider,
                    COALESCE(SUM(cost_usd), 0) AS cost_usd,
                    CASE WHEN COUNT(DISTINCT step_name) = 1 THEN MAX(step_name) END AS step_name
                FROM token_usage_records
                WHERE {" AND ".join(filters)}
                """,
                tuple(params),
            ).fetchone()

        return TokenUsage(
            prompt_tokens=row["prompt_tokens"],
            completion_tokens=row["completion_tokens"],
            total_tokens=row["total_tokens"],
            cache_read_tokens=row["cache_read_tokens"],
            cache_write_tokens=row["cache_write_tokens"],
            reasoning_tokens=row["reasoning_tokens"],
            message_count=row["message_count"],
            duration_seconds=float(row["duration_seconds"] or 0.0),
            model_name=row["model_name"],
            provider=row["provider"],
            cost_usd=self._normalize_cost(row["cost_usd"]),
            step_name=row["step_name"],
        )

    def get_window_report(
        self,
        window: str,
        as_of: date | None = None,
    ) -> TokenReportResponse:
        if window not in {"7d", "30d"}:
            raise ValueError(f"Unsupported token window: {window}")
        end_date = as_of or date.today()
        days = 7 if window == "7d" else 30
        start_date = end_date - timedelta(days=days - 1)
        summary = self._fetch_window_summary(window, start_date, end_date)
        summary_text = self._render_window_summary(summary)
        return TokenReportResponse(summary_text=summary_text, window_summary=summary)

    def generate_daily_summary(self, summary_date: str | date) -> DailyTokenSummary:
        if isinstance(summary_date, str):
            target_date = date.fromisoformat(summary_date)
        else:
            target_date = summary_date
        daily_summary = self._build_daily_summary(target_date)

        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO daily_token_summaries (
                    summary_date,
                    request_count,
                    workflow_run_count,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    estimated_cost_usd,
                    top_intent,
                    top_step_name,
                    summary_text,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(summary_date) DO UPDATE SET
                    request_count = excluded.request_count,
                    workflow_run_count = excluded.workflow_run_count,
                    prompt_tokens = excluded.prompt_tokens,
                    completion_tokens = excluded.completion_tokens,
                    total_tokens = excluded.total_tokens,
                    estimated_cost_usd = excluded.estimated_cost_usd,
                    top_intent = excluded.top_intent,
                    top_step_name = excluded.top_step_name,
                    summary_text = excluded.summary_text,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    daily_summary.summary_date,
                    daily_summary.request_count,
                    daily_summary.workflow_run_count,
                    daily_summary.prompt_tokens,
                    daily_summary.completion_tokens,
                    daily_summary.total_tokens,
                    daily_summary.estimated_cost_usd,
                    daily_summary.top_intent,
                    daily_summary.top_step_name,
                    daily_summary.summary_text,
                ),
            )
            connection.commit()
        return self.get_daily_summary(daily_summary.summary_date)

    def generate_yesterday_summary(
        self,
        today: date | None = None,
    ) -> DailyTokenSummary:
        current_day = today or date.today()
        return self.generate_daily_summary(current_day - timedelta(days=1))

    def get_daily_summary(self, summary_date: str | date) -> DailyTokenSummary:
        normalized_date = (
            summary_date.isoformat() if isinstance(summary_date, date) else summary_date
        )
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT
                    summary_date,
                    request_count,
                    workflow_run_count,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    estimated_cost_usd,
                    top_intent,
                    top_step_name,
                    summary_text
                FROM daily_token_summaries
                WHERE summary_date = ?
                """,
                (normalized_date,),
            ).fetchone()
        if row is None:
            raise ValueError(f"Daily token summary not found: {normalized_date}")
        return DailyTokenSummary(
            summary_date=row["summary_date"],
            request_count=row["request_count"],
            workflow_run_count=row["workflow_run_count"],
            prompt_tokens=row["prompt_tokens"],
            completion_tokens=row["completion_tokens"],
            total_tokens=row["total_tokens"],
            estimated_cost_usd=float(row["estimated_cost_usd"]),
            top_intent=row["top_intent"],
            top_step_name=row["top_step_name"],
            summary_text=row["summary_text"],
        )

    def _fetch_window_summary(
        self,
        window: str,
        start_date: date,
        end_date: date,
    ) -> TokenWindowSummary:
        window_start = start_date.isoformat()
        window_end = end_date.isoformat()
        params = (window_start, window_end)
        with closing(self._connect()) as connection:
            aggregate_row = connection.execute(
                """
                SELECT
                    COUNT(DISTINCT tur.request_id) AS request_count,
                    COUNT(DISTINCT tur.run_id) AS workflow_run_count,
                    COALESCE(SUM(tur.prompt_tokens), 0) AS prompt_tokens,
                    COALESCE(SUM(tur.completion_tokens), 0) AS completion_tokens,
                    COALESCE(SUM(tur.total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(tur.cost_usd), 0) AS estimated_cost_usd
                FROM token_usage_records tur
                WHERE DATE(tur.created_at) BETWEEN DATE(?) AND DATE(?)
                """,
                params,
            ).fetchone()
            by_intent = self._fetch_breakdown(
                connection,
                """
                SELECT
                    r.intent AS label,
                    COUNT(DISTINCT tur.request_id) AS request_count,
                    COUNT(DISTINCT tur.run_id) AS workflow_run_count,
                    COALESCE(SUM(tur.total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(tur.cost_usd), 0) AS estimated_cost_usd
                FROM token_usage_records tur
                JOIN requests r ON r.request_id = tur.request_id
                WHERE DATE(tur.created_at) BETWEEN DATE(?) AND DATE(?)
                GROUP BY r.intent
                ORDER BY total_tokens DESC, r.intent ASC
                """,
                params,
            )
            by_step_name = self._fetch_breakdown(
                connection,
                """
                SELECT
                    COALESCE(tur.step_name, 'unspecified') AS label,
                    COUNT(DISTINCT tur.request_id) AS request_count,
                    COUNT(DISTINCT tur.run_id) AS workflow_run_count,
                    COALESCE(SUM(tur.total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(tur.cost_usd), 0) AS estimated_cost_usd
                FROM token_usage_records tur
                WHERE DATE(tur.created_at) BETWEEN DATE(?) AND DATE(?)
                GROUP BY COALESCE(tur.step_name, 'unspecified')
                ORDER BY total_tokens DESC, label ASC
                """,
                params,
            )
            top_requests = self._fetch_breakdown(
                connection,
                """
                SELECT
                    tur.request_id AS label,
                    1 AS request_count,
                    COUNT(DISTINCT tur.run_id) AS workflow_run_count,
                    COALESCE(SUM(tur.total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(tur.cost_usd), 0) AS estimated_cost_usd
                FROM token_usage_records tur
                WHERE DATE(tur.created_at) BETWEEN DATE(?) AND DATE(?)
                GROUP BY tur.request_id
                ORDER BY total_tokens DESC, tur.request_id ASC
                LIMIT 5
                """,
                params,
            )

        return TokenWindowSummary(
            window=window,  # type: ignore[arg-type]
            start_date=window_start,
            end_date=window_end,
            request_count=aggregate_row["request_count"],
            workflow_run_count=aggregate_row["workflow_run_count"],
            prompt_tokens=aggregate_row["prompt_tokens"],
            completion_tokens=aggregate_row["completion_tokens"],
            total_tokens=aggregate_row["total_tokens"],
            estimated_cost_usd=self._normalize_cost(aggregate_row["estimated_cost_usd"]),
            by_intent=by_intent,
            by_step_name=by_step_name,
            top_requests=top_requests,
        )

    def _fetch_breakdown(
        self,
        connection: sqlite3.Connection,
        query: str,
        params: tuple[str, str],
    ) -> list[TokenUsageBreakdown]:
        rows = connection.execute(query, params).fetchall()
        return [
            TokenUsageBreakdown(
                label=row["label"],
                request_count=row["request_count"],
                workflow_run_count=row["workflow_run_count"],
                total_tokens=row["total_tokens"],
                estimated_cost_usd=self._normalize_cost(row["estimated_cost_usd"]),
            )
            for row in rows
        ]

    def _build_daily_summary(self, target_date: date) -> DailyTokenSummary:
        params = (target_date.isoformat(), target_date.isoformat())
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(DISTINCT tur.request_id) AS request_count,
                    COUNT(DISTINCT tur.run_id) AS workflow_run_count,
                    COALESCE(SUM(tur.prompt_tokens), 0) AS prompt_tokens,
                    COALESCE(SUM(tur.completion_tokens), 0) AS completion_tokens,
                    COALESCE(SUM(tur.total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(tur.cost_usd), 0) AS estimated_cost_usd
                FROM token_usage_records tur
                WHERE DATE(tur.created_at) BETWEEN DATE(?) AND DATE(?)
                """,
                params,
            ).fetchone()
            top_intent_row = connection.execute(
                """
                SELECT
                    r.intent AS label
                FROM token_usage_records tur
                JOIN requests r ON r.request_id = tur.request_id
                WHERE DATE(tur.created_at) BETWEEN DATE(?) AND DATE(?)
                GROUP BY r.intent
                ORDER BY SUM(tur.total_tokens) DESC, r.intent ASC
                LIMIT 1
                """,
                params,
            ).fetchone()
            top_step_row = connection.execute(
                """
                SELECT
                    COALESCE(tur.step_name, 'unspecified') AS label
                FROM token_usage_records tur
                WHERE DATE(tur.created_at) BETWEEN DATE(?) AND DATE(?)
                GROUP BY COALESCE(tur.step_name, 'unspecified')
                ORDER BY SUM(tur.total_tokens) DESC, label ASC
                LIMIT 1
                """,
                params,
            ).fetchone()

        summary = DailyTokenSummary(
            summary_date=target_date.isoformat(),
            request_count=row["request_count"],
            workflow_run_count=row["workflow_run_count"],
            prompt_tokens=row["prompt_tokens"],
            completion_tokens=row["completion_tokens"],
            total_tokens=row["total_tokens"],
            estimated_cost_usd=self._normalize_cost(row["estimated_cost_usd"]),
            top_intent=top_intent_row["label"] if top_intent_row else None,
            top_step_name=top_step_row["label"] if top_step_row else None,
        )
        return summary.model_copy(
            update={"summary_text": self._render_daily_summary(summary)}
        )

    def _render_window_summary(self, summary: TokenWindowSummary) -> str:
        top_intent = summary.by_intent[0].label if summary.by_intent else "n/a"
        top_step = summary.by_step_name[0].label if summary.by_step_name else "n/a"
        return (
            f"Token report for {summary.window} ({summary.start_date} to {summary.end_date}): "
            f"requests={summary.request_count}, workflow_runs={summary.workflow_run_count}, "
            f"total_tokens={summary.total_tokens}, estimated_cost_usd={summary.estimated_cost_usd:.4f}, "
            f"top_intent={top_intent}, top_step={top_step}."
        )

    def _render_daily_summary(self, summary: DailyTokenSummary) -> str:
        return (
            f"Daily token summary for {summary.summary_date}: "
            f"requests={summary.request_count}, workflow_runs={summary.workflow_run_count}, "
            f"total_tokens={summary.total_tokens}, estimated_cost_usd={summary.estimated_cost_usd:.4f}, "
            f"top_intent={summary.top_intent or 'n/a'}, top_step={summary.top_step_name or 'n/a'}."
        )

    def _normalize_cost(self, value: float | int) -> float:
        return round(float(value or 0), 6)
