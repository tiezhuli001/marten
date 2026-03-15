from __future__ import annotations

import json
import sqlite3
import subprocess
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import Settings, get_settings
from app.ledger.service import TokenLedgerService
from app.models.schemas import (
    GitExecutionResult,
    SleepCodingIssue,
    SleepCodingPlan,
    SleepCodingPullRequest,
    SleepCodingTask,
    SleepCodingTaskActionRequest,
    SleepCodingTaskEvent,
    SleepCodingTaskRequest,
    TaskAction,
    TaskStatus,
    TokenUsage,
    ValidationResult,
)
from app.services.channel import ChannelNotificationService
from app.services.git_workspace import GitWorkspaceService
from app.services.github import GitHubService


class ValidationRunner:
    def run(self, repo_path: Path) -> ValidationResult:
        command = ["python", "-m", "unittest", "discover", "-s", "tests"]
        completed = subprocess.run(
            command,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        return ValidationResult(
            status="passed" if completed.returncode == 0 else "failed",
            command=" ".join(command),
            exit_code=completed.returncode,
            output=output,
        )


class SleepCodingService:
    def __init__(
        self,
        settings: Settings | None = None,
        github: GitHubService | None = None,
        channel: ChannelNotificationService | None = None,
        git_workspace: GitWorkspaceService | None = None,
        validator: ValidationRunner | None = None,
        ledger: TokenLedgerService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.github = github or GitHubService(self.settings)
        self.channel = channel or ChannelNotificationService(self.settings)
        self.git_workspace = git_workspace or GitWorkspaceService(self.settings)
        self.validator = validator or ValidationRunner()
        self.ledger = ledger or TokenLedgerService(self.settings)
        self.database_path = self.settings.resolved_database_path
        self.repo_path = self.settings.project_root
        self.sleep_coding_labels = self.settings.resolved_sleep_coding_labels
        self._ensure_parent_dir()
        self._initialize_schema()

    def _ensure_parent_dir(self) -> None:
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
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
                CREATE TABLE IF NOT EXISTS sleep_coding_tasks (
                    task_id TEXT PRIMARY KEY,
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
            connection.commit()

    def start_task(self, payload: SleepCodingTaskRequest) -> SleepCodingTask:
        repo = payload.repo or self.settings.github_repository
        task_id = str(uuid4())
        head_branch = payload.head_branch or f"codex/issue-{payload.issue_number}-sleep-coding"
        issue = self.github.get_issue(
            repo=repo,
            issue_number=payload.issue_number,
            title_override=payload.issue_title,
            body_override=payload.issue_body,
        )
        validation = ValidationResult(status="pending")
        git_execution = GitExecutionResult()
        with closing(self._connect()) as connection:
            self._insert_task(
                connection=connection,
                task_id=task_id,
                payload=payload,
                repo=repo,
                head_branch=head_branch,
                issue=issue,
                git_execution=git_execution,
                validation=validation,
            )
            self._append_event(connection, task_id, "task_created", {"status": "created"})
            self._update_status(connection, task_id, "planning")
            plan = self._build_plan(issue)
            comment_body = self._render_plan_comment(plan)
            comment = self.github.create_issue_comment(repo, payload.issue_number, comment_body)
            labels = sorted(set(issue.labels + self.sleep_coding_labels))
            label_result = self.github.apply_labels(repo, payload.issue_number, labels)
            self._update_task_payloads(
                connection,
                task_id,
                status="awaiting_confirmation",
                plan=plan,
                issue=issue.model_copy(
                    update={
                        "html_url": issue.html_url or comment.html_url,
                        "labels": label_result.labels or labels,
                        "is_dry_run": issue.is_dry_run or comment.is_dry_run,
                    }
                ),
            )
            self._append_event(
                connection,
                task_id,
                "plan_generated",
                {
                    "summary": plan.summary,
                    "issue_comment_url": comment.html_url,
                    "is_dry_run": comment.is_dry_run,
                },
            )
            self._append_event(
                connection,
                task_id,
                "labels_synced",
                {
                    "target": "issue",
                    "labels": label_result.labels or labels,
                    "is_dry_run": label_result.is_dry_run,
                },
            )
            notification = self.channel.notify(
                title=f"[Sleep Coding] Issue #{payload.issue_number} ready for confirmation",
                lines=[
                    f"Repo: {repo}",
                    f"Task: {task_id}",
                    f"Branch: {head_branch}",
                    f"Status: awaiting_confirmation",
                    f"Issue: {issue.html_url or 'n/a'}",
                ],
            )
            self._append_event(
                connection,
                task_id,
                "channel_notified",
                {
                    "provider": notification.provider,
                    "delivered": notification.delivered,
                    "is_dry_run": notification.is_dry_run,
                    "stage": "plan_ready",
                },
            )
            connection.commit()
        return self.get_task(task_id)

    def apply_action(
        self,
        task_id: str,
        payload: SleepCodingTaskActionRequest,
    ) -> SleepCodingTask:
        with closing(self._connect()) as connection:
            task = self._get_task_row(connection, task_id)
            action = payload.action
            if action == "approve_plan":
                self._handle_approve_plan(connection, task)
            elif action == "request_changes":
                self._handle_request_changes(connection, task)
            elif action == "approve_pr":
                self._handle_terminal_action(connection, task, action, "approved")
            elif action in {"reject_plan", "cancel_task"}:
                self._handle_terminal_action(connection, task, action, "cancelled")
            else:
                raise ValueError(f"Unsupported action: {action}")
            connection.commit()
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> SleepCodingTask:
        with closing(self._connect()) as connection:
            row = self._get_task_row(connection, task_id)
            events = connection.execute(
                """
                SELECT id, event_type, payload, created_at
                FROM task_events
                WHERE task_id = ?
                ORDER BY id ASC
                """,
                (task_id,),
            ).fetchall()
        return self._deserialize_task(row, events)

    def _handle_approve_plan(self, connection: sqlite3.Connection, task: sqlite3.Row) -> None:
        self._ensure_status(task["status"], {"awaiting_confirmation", "changes_requested"})
        self._update_status(connection, task["task_id"], "coding")
        self._append_event(connection, task["task_id"], "coding_started", {})
        git_execution = self.git_workspace.prepare_worktree(task["head_branch"])
        plan = SleepCodingPlan.model_validate_json(task["plan_payload"])
        artifact_result = self.git_workspace.write_task_artifact(
            branch=task["head_branch"],
            task_id=task["task_id"],
            issue_number=task["issue_number"],
            plan_summary=plan.summary,
        )
        git_execution = artifact_result.model_copy(
            update={
                "status": artifact_result.status,
                "worktree_path": artifact_result.worktree_path or git_execution.worktree_path,
                "artifact_path": artifact_result.artifact_path,
                "output": "\n".join(
                    part
                    for part in (git_execution.output, artifact_result.output)
                    if part
                ),
                "is_dry_run": git_execution.is_dry_run and artifact_result.is_dry_run,
            }
        )
        self._update_task_payloads(
            connection,
            task["task_id"],
            status="coding",
            git_execution=git_execution,
        )
        self._append_event(
            connection,
            task["task_id"],
            "worktree_prepared",
            {
                "worktree_path": git_execution.worktree_path,
                "artifact_path": git_execution.artifact_path,
                "is_dry_run": git_execution.is_dry_run,
            },
        )
        self._update_status(connection, task["task_id"], "validating")

        validation_repo_path = (
            Path(git_execution.worktree_path)
            if git_execution.worktree_path and not git_execution.is_dry_run
            else self.repo_path
        )
        validation = self.validator.run(validation_repo_path)
        if validation.status == "failed":
            self._update_task_payloads(
                connection,
                task["task_id"],
                status="failed",
                git_execution=git_execution,
                validation=validation,
                last_error="Local validation failed.",
            )
            self._append_event(
                connection,
                task["task_id"],
                "validation_failed",
                {"exit_code": validation.exit_code},
            )
            notification = self.channel.notify(
                title=f"[Sleep Coding] Validation failed for Issue #{task['issue_number']}",
                lines=[
                    f"Repo: {task['repo']}",
                    f"Task: {task['task_id']}",
                    f"Branch: {task['head_branch']}",
                    f"Status: failed",
                    f"Exit code: {validation.exit_code}",
                ],
            )
            self._append_event(
                connection,
                task["task_id"],
                "channel_notified",
                {
                    "provider": notification.provider,
                    "delivered": notification.delivered,
                    "is_dry_run": notification.is_dry_run,
                    "stage": "validation_failed",
                },
            )
            self._sync_task_tokens(connection, task)
            return

        issue = SleepCodingIssue.model_validate_json(task["issue_payload"])
        commit_result = self.git_workspace.commit_changes(
            branch=task["head_branch"],
            message=f"Sleep coding: issue #{task['issue_number']}",
        )
        self._append_event(
            connection,
            task["task_id"],
            "git_commit",
            {
                "status": commit_result.status,
                "commit_sha": commit_result.commit_sha,
                "is_dry_run": commit_result.is_dry_run,
            },
        )
        push_result = self.git_workspace.push_branch(task["head_branch"])
        self._append_event(
            connection,
            task["task_id"],
            "git_push",
            {
                "status": push_result.status,
                "push_remote": push_result.push_remote,
                "commit_sha": push_result.commit_sha,
                "is_dry_run": push_result.is_dry_run,
            },
        )
        combined_git_execution = push_result.model_copy(
            update={
                "status": push_result.status
                if push_result.status != "skipped"
                else commit_result.status,
                "worktree_path": push_result.worktree_path or commit_result.worktree_path or git_execution.worktree_path,
                "artifact_path": git_execution.artifact_path,
                "commit_sha": push_result.commit_sha or commit_result.commit_sha,
                "output": "\n".join(
                    part
                    for part in (
                        git_execution.output,
                        commit_result.output,
                        push_result.output,
                    )
                    if part
                ),
                "is_dry_run": git_execution.is_dry_run and commit_result.is_dry_run and push_result.is_dry_run,
            }
        )
        pull_request = self.github.create_pull_request(
            repo=task["repo"],
            issue=issue,
            plan=plan,
            validation=validation,
            head_branch=task["head_branch"],
            base_branch=task["base_branch"],
        )
        pr_labels = self.github.apply_labels(
            task["repo"],
            pull_request.pr_number or task["issue_number"],
            self.sleep_coding_labels,
        )
        self.github.create_issue_comment(
            task["repo"],
            task["issue_number"],
            self._render_pr_comment(pull_request),
        )
        self._update_task_payloads(
            connection,
            task["task_id"],
            status="in_review",
            git_execution=combined_git_execution,
            validation=validation,
            pull_request=pull_request.model_copy(
                update={"labels": pr_labels.labels or self.sleep_coding_labels}
            ),
            last_error=None,
        )
        self._append_event(
            connection,
            task["task_id"],
            "pr_opened",
            {
                "pr_url": pull_request.html_url,
                "pr_number": pull_request.pr_number,
                "is_dry_run": pull_request.is_dry_run,
            },
        )
        self._append_event(
            connection,
            task["task_id"],
            "labels_synced",
            {
                "target": "pull_request",
                "labels": pr_labels.labels or self.sleep_coding_labels,
                "is_dry_run": pr_labels.is_dry_run,
            },
        )
        notification = self.channel.notify(
            title=f"[Sleep Coding] PR ready for Issue #{task['issue_number']}",
            lines=[
                f"Repo: {task['repo']}",
                f"Task: {task['task_id']}",
                f"Branch: {task['head_branch']}",
                f"Status: in_review",
                f"PR: {pull_request.html_url or 'n/a'}",
            ],
        )
        self._append_event(
            connection,
            task["task_id"],
            "channel_notified",
            {
                "provider": notification.provider,
                "delivered": notification.delivered,
                "is_dry_run": notification.is_dry_run,
                "stage": "pr_ready",
            },
        )

    def _handle_request_changes(self, connection: sqlite3.Connection, task: sqlite3.Row) -> None:
        self._ensure_status(task["status"], {"in_review", "approved"})
        self._update_status(connection, task["task_id"], "changes_requested")
        self._append_event(connection, task["task_id"], "changes_requested", {})

    def _handle_terminal_action(
        self,
        connection: sqlite3.Connection,
        task: sqlite3.Row,
        action: TaskAction,
        target_status: TaskStatus,
    ) -> None:
        allowed_statuses = {
            "approve_pr": {"in_review", "changes_requested"},
            "reject_plan": {"awaiting_confirmation"},
            "cancel_task": {"created", "planning", "awaiting_confirmation", "changes_requested", "in_review"},
        }
        self._ensure_status(task["status"], allowed_statuses[action])
        self._update_status(connection, task["task_id"], target_status)
        self._append_event(connection, task["task_id"], action, {"status": target_status})
        self._sync_task_tokens(connection, task)

    def _sync_task_tokens(self, connection: sqlite3.Connection, task: sqlite3.Row) -> None:
        usage = (
            self.ledger.get_request_usage(task["kickoff_request_id"])
            if task["kickoff_request_id"]
            else TokenUsage()
        )
        connection.execute(
            """
            UPDATE sleep_coding_tasks
            SET prompt_tokens = ?, completion_tokens = ?, total_tokens = ?, updated_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
            """,
            (
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.total_tokens,
                task["task_id"],
            ),
        )

    def _build_plan(self, issue: SleepCodingIssue) -> SleepCodingPlan:
        issue_body = issue.body.strip() or "Issue body is empty."
        summary = f"Implement Issue #{issue.issue_number}: {issue.title}"
        return SleepCodingPlan(
            summary=summary,
            scope=[
                "Read the issue context and confirm the affected modules.",
                "Implement the minimum code path required for the issue.",
                "Prepare a reviewable branch and PR summary.",
            ],
            validation=[
                "Run python -m unittest discover -s tests",
                "Record the command, exit code, and captured output in task state.",
            ],
            risks=[
                "Issue details may be incomplete, so the generated plan may need human correction.",
                f"Current issue context: {issue_body[:160]}",
            ],
        )

    def _render_plan_comment(self, plan: SleepCodingPlan) -> str:
        scope = "\n".join(f"- {item}" for item in plan.scope)
        validation = "\n".join(f"- {item}" for item in plan.validation)
        risks = "\n".join(f"- {item}" for item in plan.risks)
        return (
            "## Sleep Coding Plan\n"
            f"{plan.summary}\n\n"
            f"### Scope\n{scope}\n\n"
            f"### Validation\n{validation}\n\n"
            f"### Risks\n{risks}"
        )

    def _render_pr_comment(self, pull_request: SleepCodingPullRequest) -> str:
        return (
            "## Sleep Coding PR Ready\n"
            f"- PR: {pull_request.html_url or 'pending'}\n"
            f"- Dry run: {pull_request.is_dry_run}"
        )

    def _insert_task(
        self,
        connection: sqlite3.Connection,
        task_id: str,
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
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

    def _update_status(
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

    def _update_task_payloads(
        self,
        connection: sqlite3.Connection,
        task_id: str,
        status: TaskStatus,
        issue: SleepCodingIssue | None = None,
        plan: SleepCodingPlan | None = None,
        git_execution: GitExecutionResult | None = None,
        validation: ValidationResult | None = None,
        pull_request: SleepCodingPullRequest | None = None,
        last_error: str | None = None,
    ) -> None:
        current = self._get_task_row(connection, task_id)
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
                (
                    plan.model_dump_json()
                    if plan
                    else current["plan_payload"]
                ),
                (
                    git_execution.model_dump_json()
                    if git_execution
                    else current["git_execution_payload"]
                ),
                (validation or ValidationResult.model_validate_json(current["validation_payload"])).model_dump_json(),
                (
                    pull_request.model_dump_json()
                    if pull_request
                    else current["pr_payload"]
                ),
                last_error,
                task_id,
            ),
        )

    def _append_event(
        self,
        connection: sqlite3.Connection,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO task_events (task_id, event_type, payload)
            VALUES (?, ?, ?)
            """,
            (task_id, event_type, json.dumps(payload, ensure_ascii=True)),
        )

    def _get_task_row(self, connection: sqlite3.Connection, task_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM sleep_coding_tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Task not found: {task_id}")
        return row

    def _deserialize_task(
        self,
        row: sqlite3.Row,
        events: list[sqlite3.Row],
    ) -> SleepCodingTask:
        return SleepCodingTask(
            task_id=row["task_id"],
            issue_number=row["issue_number"],
            repo=row["repo"],
            base_branch=row["base_branch"],
            head_branch=row["head_branch"],
            status=row["status"],
            issue=SleepCodingIssue.model_validate_json(row["issue_payload"]),
            plan=(
                SleepCodingPlan.model_validate_json(row["plan_payload"])
                if row["plan_payload"]
                else None
            ),
            git_execution=GitExecutionResult.model_validate_json(row["git_execution_payload"]),
            validation=ValidationResult.model_validate_json(row["validation_payload"]),
            pull_request=(
                SleepCodingPullRequest.model_validate_json(row["pr_payload"])
                if row["pr_payload"]
                else None
            ),
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
            last_error=row["last_error"],
            kickoff_request_id=row["kickoff_request_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _ensure_status(self, current_status: str, allowed_statuses: set[str]) -> None:
        if current_status not in allowed_statuses:
            expected = ", ".join(sorted(allowed_statuses))
            raise ValueError(f"Action is not allowed from status={current_status}. Expected one of: {expected}")
