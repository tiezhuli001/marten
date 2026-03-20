from __future__ import annotations

import json
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING

from app.agents.code_review_agent.target import ReviewTarget
from app.infra.sqlite_utils import connect_sqlite, ensure_writable_dir, ensure_writable_parent
from app.models.schemas import ReviewFinding, ReviewRun, ReviewSource, TokenUsage

if TYPE_CHECKING:
    from app.control.context import ContextAssemblyService
    from app.core.config import Settings
    from app.control.session_registry import SessionRegistryService


class ReviewRunStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.database_path = settings.resolved_database_path
        self.review_runs_dir = settings.resolved_review_runs_dir
        self.ensure_parent_dir()
        self.initialize_schema()

    def ensure_parent_dir(self) -> None:
        self.database_path = ensure_writable_parent(self.database_path)
        self.review_runs_dir = ensure_writable_dir(self.review_runs_dir)

    def connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.database_path)

    def initialize_schema(self) -> None:
        with closing(self.connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS review_runs (
                    review_id TEXT PRIMARY KEY,
                    control_task_id TEXT,
                    parent_task_id TEXT,
                    source_payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    artifact_path TEXT,
                    comment_url TEXT,
                    summary TEXT NOT NULL,
                    content TEXT NOT NULL,
                    findings_payload TEXT NOT NULL DEFAULT '[]',
                    severity_counts_payload TEXT NOT NULL DEFAULT '{}',
                    is_blocking INTEGER NOT NULL DEFAULT 0,
                    run_mode TEXT NOT NULL,
                    task_id TEXT,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
                    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
                    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    duration_seconds REAL NOT NULL DEFAULT 0,
                    model_name TEXT,
                    provider TEXT,
                    cost_usd REAL NOT NULL DEFAULT 0,
                    step_name TEXT,
                    reviewed_at TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(review_runs)")
            }
            if "findings_payload" not in columns:
                connection.execute(
                    """
                    ALTER TABLE review_runs
                    ADD COLUMN findings_payload TEXT NOT NULL DEFAULT '[]'
                    """
                )
            if "control_task_id" not in columns:
                connection.execute(
                    """
                    ALTER TABLE review_runs
                    ADD COLUMN control_task_id TEXT
                    """
                )
            if "parent_task_id" not in columns:
                connection.execute(
                    """
                    ALTER TABLE review_runs
                    ADD COLUMN parent_task_id TEXT
                    """
                )
            if "severity_counts_payload" not in columns:
                connection.execute(
                    """
                    ALTER TABLE review_runs
                    ADD COLUMN severity_counts_payload TEXT NOT NULL DEFAULT '{}'
                    """
                )
            if "is_blocking" not in columns:
                connection.execute(
                    """
                    ALTER TABLE review_runs
                    ADD COLUMN is_blocking INTEGER NOT NULL DEFAULT 0
                    """
                )
            for column_name, definition in {
                "prompt_tokens": "INTEGER NOT NULL DEFAULT 0",
                "completion_tokens": "INTEGER NOT NULL DEFAULT 0",
                "total_tokens": "INTEGER NOT NULL DEFAULT 0",
                "cache_read_tokens": "INTEGER NOT NULL DEFAULT 0",
                "cache_write_tokens": "INTEGER NOT NULL DEFAULT 0",
                "reasoning_tokens": "INTEGER NOT NULL DEFAULT 0",
                "message_count": "INTEGER NOT NULL DEFAULT 0",
                "duration_seconds": "REAL NOT NULL DEFAULT 0",
                "model_name": "TEXT",
                "provider": "TEXT",
                "cost_usd": "REAL NOT NULL DEFAULT 0",
                "step_name": "TEXT",
            }.items():
                if column_name in columns:
                    continue
                connection.execute(
                    f"ALTER TABLE review_runs ADD COLUMN {column_name} {definition}"
                )
            connection.commit()

    def write_artifact(self, review_id: str, target: ReviewTarget, content: str) -> Path:
        filename = self.artifact_name(review_id, target)
        artifact_path = self.review_runs_dir / filename
        artifact_path.write_text(content, encoding="utf-8")
        return artifact_path

    def artifact_name(self, review_id: str, target: ReviewTarget) -> str:
        if target.task_id:
            return f"task-{target.task_id}-review.md"
        return f"review-{review_id}.md"

    def get_review(self, review_id: str) -> ReviewRun:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT * FROM review_runs WHERE review_id = ?",
                (review_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"Review not found: {review_id}")
        return self.deserialize_review(row)

    def list_task_reviews(self, task_id: str) -> list[ReviewRun]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM review_runs
                WHERE task_id = ?
                ORDER BY created_at ASC, review_id ASC
                """,
                (task_id,),
            ).fetchall()
        return [self.deserialize_review(row) for row in rows]

    def count_blocking_reviews(self, task_id: str) -> int:
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM review_runs
                WHERE task_id = ? AND is_blocking = 1
                """,
                (task_id,),
            ).fetchone()
        return int(row["count"]) if row else 0

    def deserialize_review(self, row: sqlite3.Row) -> ReviewRun:
        findings = [
            ReviewFinding.model_validate(item)
            for item in json.loads(row["findings_payload"] or "[]")
        ]
        return ReviewRun(
            review_id=row["review_id"],
            control_task_id=row["control_task_id"],
            parent_task_id=row["parent_task_id"],
            source=ReviewSource.model_validate_json(row["source_payload"]),
            status=row["status"],
            artifact_path=row["artifact_path"],
            comment_url=row["comment_url"],
            summary=row["summary"],
            content=row["content"],
            findings=findings,
            severity_counts=json.loads(row["severity_counts_payload"] or "{}"),
            is_blocking=bool(row["is_blocking"]),
            run_mode=row["run_mode"],
            task_id=row["task_id"],
            token_usage=TokenUsage(
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
                cost_usd=float(row["cost_usd"] or 0.0),
                step_name=row["step_name"],
            ),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            reviewed_at=row["reviewed_at"],
        )


class ReviewWorkspaceSupport:
    def __init__(self, settings: Settings, context: ContextAssemblyService) -> None:
        self.settings = settings
        self.context = context

    def build_workspace_context(self, target: ReviewTarget) -> str:
        local_path = Path(target.workspace_path or self.settings.project_root).expanduser()
        base_branch = target.base_branch or "main"
        head_branch = target.head_branch
        if not (local_path / ".git").exists():
            return (
                f"Local Path: {local_path}\n"
                "Git metadata unavailable. Review the working tree content directly.\n"
            )

        diff_args = ["git", "diff", "--stat"]
        diff_target = "working-tree"
        if head_branch:
            merge_base = subprocess.run(
                ["git", "merge-base", base_branch, head_branch],
                cwd=local_path,
                capture_output=True,
                text=True,
                check=False,
            )
            base_ref = merge_base.stdout.strip() if merge_base.returncode == 0 else base_branch
            diff_args = ["git", "diff", "--stat", f"{base_ref}..{head_branch}"]
            diff_target = f"{base_ref}..{head_branch}"
            merge_base_note = (
                ""
                if merge_base.returncode == 0
                else f"Merge-base resolution failed; fallback to `{base_branch}`.\n"
            )
        else:
            base_ref = base_branch
            merge_base_note = ""

        diff = subprocess.run(
            diff_args,
            cwd=local_path,
            capture_output=True,
            text=True,
            check=False,
        )
        diff_body = self.format_git_output(
            completed=diff,
            success_label="Diff stat collected successfully.",
            failure_label=(
                "Diff stat unavailable. Review should fall back to the working tree "
                "and repository files."
            ),
        )
        detailed_diff = subprocess.run(
            ["git", "diff", "--unified=1"]
            if not head_branch
            else ["git", "diff", "--unified=1", f"{base_ref}..{head_branch}"],
            cwd=local_path,
            capture_output=True,
            text=True,
            check=False,
        )
        detailed_diff_body = self.format_git_output(
            completed=detailed_diff,
            success_label="Detailed diff collected successfully.",
            failure_label=(
                "Detailed diff unavailable. Review should rely on repository files "
                "and changed file summaries."
            ),
        )
        return (
            f"Local Path: {local_path}\n"
            f"Base Branch: {base_branch}\n"
            f"Head Branch: {head_branch or 'working-tree'}\n"
            f"Diff Target: {diff_target}\n"
            f"{merge_base_note}\n"
            "## Diff Stat\n"
            f"{diff_body}\n\n"
            "## Diff\n"
            f"{detailed_diff_body}\n"
        )

    def format_git_output(
        self,
        completed: subprocess.CompletedProcess[str],
        success_label: str,
        failure_label: str,
    ) -> str:
        output = completed.stdout.strip() or completed.stderr.strip()
        if completed.returncode == 0:
            return output or success_label
        return (
            f"{failure_label}\n"
            f"Exit code: {completed.returncode}\n"
            f"Git output: {output or 'n/a'}"
        )
