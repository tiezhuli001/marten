from __future__ import annotations

import re
import shlex
import sqlite3
import subprocess
import tempfile
from contextlib import closing
from pathlib import Path
from shutil import which
from uuid import uuid4

from app.core.config import Settings, get_settings
from app.models.schemas import (
    ReviewActionRequest,
    ReviewRun,
    ReviewRunRequest,
    ReviewSource,
    SleepCodingTaskActionRequest,
)
from app.services.github import GitHubCommentResult, GitHubService
from app.services.gitlab import GitLabService
from app.services.sleep_coding import SleepCodingService


class ReviewSkillService:
    def __init__(self, settings: Settings) -> None:
        self.skill_name = settings.review_skill_name
        self.command = settings.review_skill_command
        self.project_root = settings.project_root

    def run(self, source: ReviewSource, context: str) -> tuple[str, str]:
        command = self._resolve_command(source, context)
        if command is None:
            summary = f"Dry-run review generated for {source.source_type}."
            body = self._render_dry_run_review(source, context)
            return summary, body

        prompt = self._build_prompt(source)
        review_dir = self._resolve_dir(source)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as handle:
            handle.write(context)
            context_path = Path(handle.name)

        try:
            completed = subprocess.run(
                [*command, prompt, "-f", str(context_path)],
                cwd=review_dir,
                text=True,
                capture_output=True,
                check=False,
            )
        finally:
            context_path.unlink(missing_ok=True)
        output = "\n".join(
            part for part in (completed.stdout, completed.stderr) if part
        ).strip()
        if completed.returncode != 0:
            raise RuntimeError(
                f"Review skill command failed with exit_code={completed.returncode}: {output}"
            )
        summary = output.splitlines()[0] if output else f"Review completed via {self.skill_name}."
        return summary, output

    def _resolve_command(self, source: ReviewSource, context: str) -> list[str] | None:
        if self.command:
            return shlex.split(self.command)
        if which("opencode") is None:
            return None
        review_dir = self._resolve_dir(source)
        return [
            "opencode",
            "run",
            "--dir",
            str(review_dir),
            "--format",
            "default",
        ]

    def _resolve_dir(self, source: ReviewSource) -> Path:
        if source.local_path:
            return Path(source.local_path).expanduser()
        return self.project_root

    def _build_prompt(self, source: ReviewSource) -> str:
        return (
            f"Use the {self.skill_name} skill to review this source. "
            f"Source type: {source.source_type}. "
            "Follow the skill output format and return markdown only."
        )

    def _render_dry_run_review(self, source: ReviewSource, context: str) -> str:
        return (
            "## Code Review Agent\n\n"
            f"- Skill: `{self.skill_name}`\n"
            f"- Source Type: `{source.source_type}`\n"
            f"- Run Mode: `dry_run`\n\n"
            "### Summary\n"
            "Dry-run review executed because no review skill command is configured.\n\n"
            "### Context\n"
            f"{context}\n"
        )


class ReviewService:
    def __init__(
        self,
        settings: Settings | None = None,
        github: GitHubService | None = None,
        gitlab: GitLabService | None = None,
        sleep_coding: SleepCodingService | None = None,
        skill: ReviewSkillService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.github = github or GitHubService(self.settings)
        self.gitlab = gitlab or GitLabService(self.settings)
        self.sleep_coding = sleep_coding or SleepCodingService(settings=self.settings)
        self.skill = skill or ReviewSkillService(self.settings)
        self.database_path = self.settings.resolved_database_path
        self.review_runs_dir = self.settings.resolved_review_runs_dir
        self._ensure_parent_dir()
        self._initialize_schema()

    def start_review(self, payload: ReviewRunRequest) -> ReviewRun:
        review_id = str(uuid4())
        source = self._normalize_source(payload.source)
        context = self._build_context(source)
        summary, content = self.skill.run(source, context)
        artifact_path = self._write_artifact(review_id, source, content)
        comment = self._write_comment(source, content)
        run_mode = "real_run" if self.settings.review_skill_command else "dry_run"

        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO review_runs (
                    review_id,
                    source_payload,
                    status,
                    artifact_path,
                    comment_url,
                    summary,
                    content,
                    run_mode,
                    task_id,
                    reviewed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    review_id,
                    source.model_dump_json(),
                    "completed",
                    str(artifact_path),
                    comment.html_url,
                    summary,
                    content,
                    run_mode,
                    source.task_id,
                ),
            )
            connection.commit()

        return self.get_review(review_id)

    def get_review(self, review_id: str) -> ReviewRun:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM review_runs WHERE review_id = ?",
                (review_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"Review not found: {review_id}")
        return self._deserialize_review(row)

    def apply_action(self, review_id: str, payload: ReviewActionRequest) -> ReviewRun:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM review_runs WHERE review_id = ?",
                (review_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Review not found: {review_id}")

            status_map = {
                "approve_review": "approved",
                "request_changes": "changes_requested",
                "cancel_review": "cancelled",
            }
            new_status = status_map[payload.action]
            connection.execute(
                """
                UPDATE review_runs
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE review_id = ?
                """,
                (new_status, review_id),
            )
            connection.commit()

        review = self.get_review(review_id)
        if review.task_id:
            if payload.action == "request_changes":
                self.sleep_coding.apply_action(
                    review.task_id,
                    SleepCodingTaskActionRequest(action="request_changes"),
                )
            elif payload.action == "approve_review":
                self.sleep_coding.apply_action(
                    review.task_id,
                    SleepCodingTaskActionRequest(action="approve_pr"),
                )
        return self.get_review(review_id)

    def trigger_for_task(self, task_id: str) -> ReviewRun:
        task = self.sleep_coding.get_task(task_id)
        source = ReviewSource(
            source_type="sleep_coding_task",
            repo=task.repo,
            pr_number=task.pull_request.pr_number if task.pull_request else None,
            url=task.pull_request.html_url if task.pull_request else None,
            base_branch=task.base_branch,
            head_branch=task.head_branch,
            task_id=task.task_id,
        )
        return self.start_review(ReviewRunRequest(source=source))

    def _ensure_parent_dir(self) -> None:
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            self.review_runs_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            fallback_dir = Path(tempfile.gettempdir()) / "youmeng-gateway"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            self.database_path = fallback_dir / self.database_path.name
            self.review_runs_dir = fallback_dir / "review-runs"
            self.review_runs_dir.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_schema(self) -> None:
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS review_runs (
                    review_id TEXT PRIMARY KEY,
                    source_payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    artifact_path TEXT,
                    comment_url TEXT,
                    summary TEXT NOT NULL,
                    content TEXT NOT NULL,
                    run_mode TEXT NOT NULL,
                    task_id TEXT,
                    reviewed_at TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            connection.commit()

    def _normalize_source(self, source: ReviewSource) -> ReviewSource:
        if source.url:
            github_match = re.match(
                r"https://github.com/(?P<repo>[^/]+/[^/]+)/pull/(?P<number>\d+)",
                source.url,
            )
            if github_match:
                return source.model_copy(
                    update={
                        "source_type": "github_pr",
                        "repo": github_match.group("repo"),
                        "pr_number": int(github_match.group("number")),
                    }
                )
            gitlab_match = re.match(
                r"https://gitlab.com/(?P<project>.+)/-/merge_requests/(?P<number>\d+)",
                source.url,
            )
            if gitlab_match:
                return source.model_copy(
                    update={
                        "source_type": "gitlab_mr",
                        "project_path": gitlab_match.group("project"),
                        "mr_number": int(gitlab_match.group("number")),
                    }
                )
        return source

    def _build_context(self, source: ReviewSource) -> str:
        if source.source_type == "sleep_coding_task" and source.task_id:
            task = self.sleep_coding.get_task(source.task_id)
            return (
                f"Task ID: {task.task_id}\n"
                f"Repo: {task.repo}\n"
                f"PR: {task.pull_request.html_url if task.pull_request else 'n/a'}\n"
                f"Validation: {task.validation.status}\n"
                f"Artifact: {task.git_execution.artifact_path or 'n/a'}\n"
                f"Plan: {task.plan.summary if task.plan else 'n/a'}\n"
            )
        if source.source_type == "local_code":
            return self._build_local_code_context(source)
        return (
            f"Source URL: {source.url or 'n/a'}\n"
            f"Repo: {source.repo or 'n/a'}\n"
            f"PR Number: {source.pr_number or 'n/a'}\n"
            f"MR Number: {source.mr_number or 'n/a'}\n"
            f"Project Path: {source.project_path or 'n/a'}\n"
        )

    def _build_local_code_context(self, source: ReviewSource) -> str:
        local_path = Path(source.local_path or self.settings.project_root).expanduser()
        base_branch = source.base_branch or "main"
        head_branch = source.head_branch
        if not (local_path / ".git").exists():
            return (
                f"Local Path: {local_path}\n"
                "Git metadata unavailable. Review the working tree content directly.\n"
            )

        diff_args = ["git", "diff", "--stat"]
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

        diff = subprocess.run(
            diff_args,
            cwd=local_path,
            capture_output=True,
            text=True,
            check=False,
        )
        detailed_diff = subprocess.run(
            ["git", "diff", "--unified=1"] if not head_branch else ["git", "diff", "--unified=1", f"{base_ref}..{head_branch}"],
            cwd=local_path,
            capture_output=True,
            text=True,
            check=False,
        )
        return (
            f"Local Path: {local_path}\n"
            f"Base Branch: {base_branch}\n"
            f"Head Branch: {head_branch or 'working-tree'}\n\n"
            "## Diff Stat\n"
            f"{diff.stdout.strip() or diff.stderr.strip() or 'n/a'}\n\n"
            "## Diff\n"
            f"{detailed_diff.stdout.strip() or detailed_diff.stderr.strip() or 'n/a'}\n"
        )

    def _write_artifact(self, review_id: str, source: ReviewSource, content: str) -> Path:
        filename = self._artifact_name(review_id, source)
        artifact_path = self.review_runs_dir / filename
        artifact_path.write_text(content, encoding="utf-8")
        return artifact_path

    def _artifact_name(self, review_id: str, source: ReviewSource) -> str:
        if source.source_type == "github_pr" and source.pr_number:
            return f"github-pr-{source.pr_number}-review.md"
        if source.source_type == "gitlab_mr" and source.mr_number:
            return f"gitlab-mr-{source.mr_number}-review.md"
        if source.source_type == "sleep_coding_task" and source.task_id:
            return f"task-{source.task_id}-review.md"
        return f"local-review-{review_id}.md"

    def _write_comment(self, source: ReviewSource, content: str) -> GitHubCommentResult:
        if source.source_type == "github_pr" and source.repo and source.pr_number:
            return self.github.create_pull_request_comment(
                repo=source.repo,
                pr_number=source.pr_number,
                body=content,
            )
        if source.source_type == "sleep_coding_task" and source.repo and source.pr_number:
            return self.github.create_pull_request_comment(
                repo=source.repo,
                pr_number=source.pr_number,
                body=content,
            )
        if source.source_type == "gitlab_mr" and source.project_path and source.mr_number:
            return self.gitlab.create_merge_request_comment(
                project_path=source.project_path,
                mr_number=source.mr_number,
                body=content,
            )
        return GitHubCommentResult(html_url=source.url, is_dry_run=True)

    def _deserialize_review(self, row: sqlite3.Row) -> ReviewRun:
        return ReviewRun(
            review_id=row["review_id"],
            source=ReviewSource.model_validate_json(row["source_payload"]),
            status=row["status"],
            artifact_path=row["artifact_path"],
            comment_url=row["comment_url"],
            summary=row["summary"],
            content=row["content"],
            run_mode=row["run_mode"],
            task_id=row["task_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            reviewed_at=row["reviewed_at"],
        )
