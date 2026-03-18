from __future__ import annotations

import json
import re
import shlex
import sqlite3
import subprocess
import tempfile
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import Settings, get_settings
from app.ledger.service import TokenLedgerService
from app.models.schemas import (
    GitExecutionResult,
    SleepCodingExecutionDraft,
    SleepCodingFileChange,
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
from app.runtime.agent_runtime import AgentDescriptor, AgentRuntime
from app.runtime.mcp import MCPClient, MCPToolCall, build_default_mcp_client
from app.runtime.pricing import PricingRegistry
from app.runtime.token_counting import TokenCountingService
from app.services.channel import ChannelNotificationService
from app.services.git_workspace import GitWorkspaceService
from app.services.session_registry import SessionRegistryService
from app.services.task_registry import TaskRegistryService


@dataclass(frozen=True)
class GitHubCommentLike:
    html_url: str | None
    is_dry_run: bool


@dataclass(frozen=True)
class GitHubLabelLike:
    labels: list[str]
    is_dry_run: bool


class ValidationRunner:
    def __init__(self, command: str | None = None, project_root: Path | None = None) -> None:
        self.command = command or "python -m unittest discover -s tests"
        self.project_root = project_root

    def run(self, repo_path: Path) -> ValidationResult:
        command = self.command.strip()
        command_args = shlex.split(command)
        primary_args = self._resolve_command_args(command_args, repo_path)
        completed = self._run_command(primary_args, repo_path)
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        if (
            completed.returncode != 0
            and self.project_root is not None
            and repo_path.resolve() != self.project_root.resolve()
        ):
            fallback_args = self._resolve_command_args(command_args, self.project_root)
            fallback = self._run_command(fallback_args, self.project_root)
            fallback_output = "\n".join(
                part for part in (fallback.stdout, fallback.stderr) if part
            ).strip()
            if fallback.returncode == 0:
                combined_output = "\n".join(
                    part
                    for part in (
                        output,
                        f"Validation fallback succeeded in primary workspace: {self.project_root}",
                        fallback_output,
                    )
                    if part
                ).strip()
                return ValidationResult(
                    status="passed",
                    command=command,
                    exit_code=0,
                    output=combined_output,
                )
        return ValidationResult(
            status="passed" if completed.returncode == 0 else "failed",
            command=command,
            exit_code=completed.returncode,
            output=output,
        )

    def _resolve_command_args(self, command_args: list[str], cwd: Path) -> list[str]:
        resolved = list(command_args)
        if (
            len(resolved) >= 2
            and resolved[0].startswith("python")
            and self.project_root is not None
        ):
            script_path = Path(resolved[1])
            if not script_path.is_absolute():
                cwd_script = cwd / script_path
                project_script = self.project_root / script_path
                if not cwd_script.exists() and project_script.exists():
                    resolved[1] = str(project_script)
        return resolved

    def _run_command(
        self,
        command_args: list[str],
        cwd: Path,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command_args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )


class SleepCodingService:
    def __init__(
        self,
        settings: Settings | None = None,
        github: object | None = None,
        channel: ChannelNotificationService | None = None,
        git_workspace: GitWorkspaceService | None = None,
        validator: ValidationRunner | None = None,
        ledger: TokenLedgerService | None = None,
        agent_runtime: AgentRuntime | None = None,
        mcp_client: MCPClient | None = None,
        tasks: TaskRegistryService | None = None,
        sessions: SessionRegistryService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.repo_path = self.settings.project_root
        self.channel = channel or ChannelNotificationService(self.settings)
        self.git_workspace = git_workspace or GitWorkspaceService(self.settings)
        self.validator = validator or ValidationRunner(
            self.settings.resolved_sleep_coding_validation_command,
            project_root=self.repo_path,
        )
        self.ledger = ledger or TokenLedgerService(self.settings)
        self.mcp_client = mcp_client or build_default_mcp_client(self.settings)
        self.agent_runtime = agent_runtime or AgentRuntime(
            self.settings,
            mcp_client=self.mcp_client,
        )
        self.token_counter = TokenCountingService()
        self.pricing = PricingRegistry(self.settings)
        self.tasks = tasks or TaskRegistryService(self.settings)
        self.sessions = sessions or SessionRegistryService(self.settings)
        self.database_path = self.settings.resolved_database_path
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
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize_schema(self) -> None:
        with closing(self._connect()) as connection:
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
            if "control_task_id" not in columns:
                connection.execute(
                    """
                    ALTER TABLE sleep_coding_tasks
                    ADD COLUMN control_task_id TEXT
                    """
                )
            if "parent_task_id" not in columns:
                connection.execute(
                    """
                    ALTER TABLE sleep_coding_tasks
                    ADD COLUMN parent_task_id TEXT
                    """
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

    def start_task(self, payload: SleepCodingTaskRequest) -> SleepCodingTask:
        repo = payload.repo or self.settings.resolved_github_repository
        task_id = str(uuid4())
        head_branch = payload.head_branch or f"codex/issue-{payload.issue_number}-sleep-coding"
        pending_usage: tuple[str, str, TokenUsage] | None = None
        issue = self._get_issue(
            repo=repo,
            issue_number=payload.issue_number,
            title_override=payload.issue_title,
            body_override=payload.issue_body,
        )
        validation = ValidationResult(
            status="pending",
            command=self.settings.resolved_sleep_coding_validation_command,
        )
        git_execution = GitExecutionResult()
        parent_task = (
            self.tasks.get_task(payload.parent_task_id)
            if payload.parent_task_id
            else self.tasks.find_parent_for_issue(repo, payload.issue_number)
        )
        control_task = self.tasks.create_task(
            task_type="sleep_coding",
            agent_id="ralph",
            status="created",
            parent_task_id=parent_task.task_id if parent_task else None,
            repo=repo,
            issue_number=payload.issue_number,
            title=issue.title,
            external_ref=f"sleep_coding_task:{task_id}",
            payload={
                "head_branch": head_branch,
                "base_branch": payload.base_branch,
            },
        )
        parent_agent_session_id = (
            parent_task.payload.get("agent_session_id")
            if parent_task
            else None
        )
        run_session = self.sessions.create_child_session(
            session_type="run_session",
            parent_session_id=parent_agent_session_id,
            agent_id="ralph",
            user_id=parent_task.user_id if parent_task else None,
            source=parent_task.source if parent_task else None,
            external_ref=f"sleep-coding-run:{task_id}",
            payload={"repo": repo, "issue_number": payload.issue_number},
        )
        control_task = self.tasks.update_task(
            control_task.task_id,
            payload_patch={"run_session_id": run_session.session_id},
        )
        with closing(self._connect()) as connection:
            self._insert_task(
                connection=connection,
                task_id=task_id,
                control_task_id=control_task.task_id,
                parent_task_id=control_task.parent_task_id,
                payload=payload,
                repo=repo,
                head_branch=head_branch,
                issue=issue,
                git_execution=git_execution,
                validation=validation,
            )
            self._append_event(connection, task_id, "task_created", {"status": "created"})
            self.tasks.append_event(
                control_task.task_id,
                "sleep_coding_task_created",
                {"domain_task_id": task_id, "issue_number": payload.issue_number},
                connection=connection,
            )
            self._update_status(connection, task_id, "planning")
            self.tasks.update_task(control_task.task_id, status="planning", connection=connection)
            plan, plan_usage = self._build_plan(issue)
            if payload.request_id:
                pending_usage = (payload.request_id, "sleep_coding_plan", plan_usage)
            comment_body = self._render_plan_comment(plan)
            comment = self._create_issue_comment(repo, payload.issue_number, comment_body)
            labels = sorted(set(issue.labels + self.sleep_coding_labels))
            label_result = self._apply_labels(repo, payload.issue_number, labels)
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
            self.tasks.update_task(
                control_task.task_id,
                status="awaiting_confirmation",
                title=issue.title,
                issue_number=payload.issue_number,
                payload_patch={"plan_summary": plan.summary, "issue_url": issue.html_url or comment.html_url},
                connection=connection,
            )
            self.tasks.append_event(
                control_task.task_id,
                "plan_ready",
                {"domain_task_id": task_id, "plan_summary": plan.summary},
                connection=connection,
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
            if payload.notify_plan_ready:
                notification = self.channel.notify(
                    title=f"Ralph 执行计划：{issue.title}",
                    lines=[
                        f"来源: Issue #{payload.issue_number}",
                        f"仓库: {repo}",
                        f"分支: {head_branch}",
                        f"Issue: {issue.html_url or 'n/a'}",
                        "计划摘要:",
                        plan.summary,
                        "执行计划:",
                        *self._render_plan_preview(plan),
                        "Ralph 已开始编码，完成后将自动提交 Pull Request 并进入 Code Review。",
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
        if pending_usage is not None:
            request_id, step_name, usage = pending_usage
            self._record_task_usage(
                request_id=request_id,
                step_name=step_name,
                usage=usage,
            )
            self._refresh_task_tokens(task_id)
        return self.get_task(task_id)

    def apply_action(
        self,
        task_id: str,
        payload: SleepCodingTaskActionRequest,
    ) -> SleepCodingTask:
        pending_usage: tuple[str, str, TokenUsage] | None = None
        with closing(self._connect()) as connection:
            task = self._get_task_row(connection, task_id)
            action = payload.action
            if action == "approve_plan":
                pending_usage = self._handle_approve_plan(connection, task)
            elif action == "request_changes":
                self._handle_request_changes(connection, task)
            elif action == "approve_pr":
                self._handle_terminal_action(connection, task, action, "approved")
            elif action in {"reject_plan", "cancel_task"}:
                self._handle_terminal_action(connection, task, action, "cancelled")
            else:
                raise ValueError(f"Unsupported action: {action}")
            connection.commit()
        if pending_usage is not None:
            request_id, step_name, usage = pending_usage
            self._record_task_usage(
                request_id=request_id,
                step_name=step_name,
                usage=usage,
            )
            self._refresh_task_tokens(task_id)
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

    def set_background_follow_up_state(
        self,
        task_id: str,
        status: str,
        *,
        error: str | None = None,
        payload: dict[str, Any] | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> SleepCodingTask:
        owned_connection = connection is None
        current_connection = connection or self._connect()
        try:
            current_connection.execute(
                """
                UPDATE sleep_coding_tasks
                SET background_follow_up_status = ?,
                    background_follow_up_error = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE task_id = ?
                """,
                (status, error, task_id),
            )
            event_payload = {
                "background_follow_up_status": status,
                "error": error,
                **(payload or {}),
            }
            self._append_event(
                current_connection,
                task_id,
                f"background_follow_up_{status}",
                event_payload,
            )
            if owned_connection:
                current_connection.commit()
            row = self._get_task_row(current_connection, task_id)
            events = current_connection.execute(
                """
                SELECT id, event_type, payload, created_at
                FROM task_events
                WHERE task_id = ?
                ORDER BY id ASC
                """,
                (task_id,),
            ).fetchall()
            return self._deserialize_task(row, events)
        finally:
            if owned_connection:
                current_connection.close()

    def _handle_approve_plan(
        self,
        connection: sqlite3.Connection,
        task: sqlite3.Row,
    ) -> tuple[str, str, TokenUsage] | None:
        self._ensure_status(task["status"], {"awaiting_confirmation", "changes_requested"})
        was_awaiting_confirmation = task["status"] == "awaiting_confirmation"
        self._update_status(connection, task["task_id"], "coding")
        self._sync_control_task(task, status="coding", connection=connection)
        self._append_event(connection, task["task_id"], "coding_started", {})
        git_execution = self.git_workspace.prepare_worktree(task["head_branch"])
        plan = SleepCodingPlan.model_validate_json(task["plan_payload"])
        issue = SleepCodingIssue.model_validate_json(task["issue_payload"])
        execution, execution_usage = self._build_execution_draft(
            issue,
            plan,
            task["head_branch"],
        )
        artifact_result = self.git_workspace.write_task_artifact(
            branch=task["head_branch"],
            task_id=task["task_id"],
            issue_number=task["issue_number"],
            artifact_markdown=execution.artifact_markdown,
            file_changes=execution.file_changes,
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
        self._append_event(
            connection,
            task["task_id"],
            "coding_draft_generated",
            {
                "commit_message": execution.commit_message,
                "artifact_path": git_execution.artifact_path,
                "generated_files": [change.path for change in execution.file_changes],
                "file_changes": [
                    {
                        "path": change.path,
                        "description": change.description,
                    }
                    for change in execution.file_changes
                ],
            },
        )
        self._update_status(connection, task["task_id"], "validating")
        self._sync_control_task(task, status="validating", connection=connection)

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
            self._sync_control_task(
                task,
                status="failed",
                payload_patch={"validation_status": validation.status, "last_error": "Local validation failed."},
                connection=connection,
            )
            notification = self.channel.notify(
                title=f"[Ralph] Validation failed for Issue #{task['issue_number']}",
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
            self._cleanup_worktree(connection, task["task_id"], task["head_branch"])
            self._sync_task_tokens(connection, task)
            if task["kickoff_request_id"]:
                return (task["kickoff_request_id"], "sleep_coding_execution", execution_usage)
            return None

        commit_result = self.git_workspace.commit_changes(
            branch=task["head_branch"],
            message=execution.commit_message,
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
        existing_pull_request = self._resolve_existing_pull_request(task, connection)
        pull_request = existing_pull_request or self._create_pull_request(
            repo=task["repo"],
            issue=issue,
            plan=plan,
            validation=validation,
            head_branch=task["head_branch"],
            base_branch=task["base_branch"],
        )
        pr_labels = self._apply_labels(
            task["repo"],
            pull_request.pr_number or task["issue_number"],
            self.sleep_coding_labels,
        )
        self._create_issue_comment(
            task["repo"],
            task["issue_number"],
            self._render_pr_comment(
                issue=issue,
                pull_request=pull_request,
                plan=plan,
                validation=validation,
                head_branch=task["head_branch"],
            ),
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
            "pr_opened" if existing_pull_request is None else "pr_updated",
            {
                "pr_url": pull_request.html_url,
                "pr_number": pull_request.pr_number,
                "is_dry_run": pull_request.is_dry_run,
            },
        )
        self._sync_control_task(
            task,
            status="in_review",
            payload_patch={
                "pr_url": pull_request.html_url,
                "pr_number": pull_request.pr_number,
                "validation_status": validation.status,
            },
            connection=connection,
        )
        if task["control_task_id"] and pull_request.pr_number:
            self.tasks.update_task(
                task["control_task_id"],
                external_ref=f"github_pr:{task['repo']}#{pull_request.pr_number}",
                connection=connection,
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
        if task["kickoff_request_id"]:
            return (task["kickoff_request_id"], "sleep_coding_execution", execution_usage)
        return None

    def _handle_request_changes(self, connection: sqlite3.Connection, task: sqlite3.Row) -> None:
        self._ensure_status(task["status"], {"in_review", "approved"})
        self._update_status(connection, task["task_id"], "changes_requested")
        self._sync_control_task(task, status="changes_requested", connection=connection)
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
        self._sync_control_task(task, status=target_status, connection=connection)
        self._append_event(connection, task["task_id"], action, {"status": target_status})
        if action in {"reject_plan", "cancel_task"}:
            self._cleanup_worktree(connection, task["task_id"], task["head_branch"])
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

    def _refresh_task_tokens(self, task_id: str) -> None:
        with closing(self._connect()) as connection:
            task = self._get_task_row(connection, task_id)
            self._sync_task_tokens(connection, task)
            connection.commit()

    def _cleanup_worktree(
        self,
        connection: sqlite3.Connection,
        task_id: str,
        head_branch: str,
    ) -> None:
        try:
            self.git_workspace.cleanup_worktree(head_branch)
        except RuntimeError as exc:
            self._append_event(
                connection,
                task_id,
                "worktree_cleanup_failed",
                {"error": str(exc)},
            )
            return
        self._append_event(
            connection,
            task_id,
            "worktree_cleaned",
            {"branch": head_branch},
        )

    def _sync_control_task(
        self,
        task: sqlite3.Row,
        *,
        status: str,
        payload_patch: dict[str, Any] | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if not task["control_task_id"]:
            return
        self.tasks.update_task(
            task["control_task_id"],
            status=status,
            payload_patch=payload_patch,
            connection=connection,
        )
        self.tasks.append_event(
            task["control_task_id"],
            f"sleep_coding_{status}",
            {"domain_task_id": task["task_id"], **(payload_patch or {})},
            connection=connection,
        )

    def _resolve_existing_pull_request(
        self,
        task: sqlite3.Row,
        connection: sqlite3.Connection,
    ) -> SleepCodingPullRequest | None:
        if task["pr_payload"]:
            return SleepCodingPullRequest.model_validate_json(task["pr_payload"])
        control_task_id = task["control_task_id"]
        if not control_task_id:
            return None
        control_task = self.tasks.get_task(control_task_id, connection=connection)
        pr_url = control_task.payload.get("pr_url")
        pr_number = control_task.payload.get("pr_number")
        if not isinstance(pr_url, str) or not pr_url.strip():
            external_ref = control_task.external_ref or ""
            match = re.match(r"^github_pr:(?P<repo>[^#]+)#(?P<number>\d+)$", external_ref)
            if match:
                pr_number = int(match.group("number"))
                pr_url = f"https://github.com/{match.group('repo')}/pull/{match.group('number')}"
        if not isinstance(pr_url, str) or not pr_url.strip():
            return None
        if not isinstance(pr_number, int):
            match = re.search(r"/pull/(?P<number>\d+)$", pr_url)
            if match:
                pr_number = int(match.group("number"))
        return SleepCodingPullRequest(
            title=f"[Ralph] #{task['issue_number']} {SleepCodingIssue.model_validate_json(task['issue_payload']).title}",
            body="Recovered existing pull request metadata from control task.",
            html_url=pr_url,
            pr_number=pr_number if isinstance(pr_number, int) else None,
            state="open",
            labels=self.sleep_coding_labels,
            is_dry_run=False,
        )

    def _build_plan(self, issue: SleepCodingIssue) -> tuple[SleepCodingPlan, TokenUsage]:
        if self.settings.openai_api_key or self.settings.minimax_api_key:
            try:
                response = self.agent_runtime.generate_structured_output(
                    self._build_agent_descriptor(),
                    user_prompt=(
                        "Build a concise implementation plan for this GitHub issue.\n\n"
                        f"Issue #{issue.issue_number}: {issue.title}\n\n"
                        f"{issue.body.strip() or 'Issue body is empty.'}"
                    ),
                    output_contract=(
                        "Return strict JSON with keys `summary`, `scope`, `validation`, and `risks`. "
                        "Each non-summary key must be an array of short strings. "
                        "The plan must emphasize concrete code changes and tests."
                    ),
                )
                return (
                    SleepCodingPlan.model_validate_json(response.output_text),
                    response.usage.model_copy(update={"step_name": "sleep_coding_plan"}),
                )
            except Exception:
                if self.settings.app_env != "test":
                    raise
        plan = self._build_heuristic_plan(issue)
        usage = self._estimate_usage(
            step_name="sleep_coding_plan",
            input_text=(
                f"Issue #{issue.issue_number}: {issue.title}\n\n"
                f"{issue.body.strip() or 'Issue body is empty.'}"
            ),
            output_text=plan.model_dump_json(),
        )
        return plan, usage

    def _build_heuristic_plan(self, issue: SleepCodingIssue) -> SleepCodingPlan:
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
                f"Run {self.settings.resolved_sleep_coding_validation_command}",
                "Record the command, exit code, and captured output in task state.",
            ],
            risks=[
                "Issue details may be incomplete, so the generated plan may need human correction.",
                f"Current issue context: {issue_body[:160]}",
            ],
        )

    def _build_execution_draft(
        self,
        issue: SleepCodingIssue,
        plan: SleepCodingPlan,
        head_branch: str,
    ) -> tuple[SleepCodingExecutionDraft, TokenUsage]:
        if self.settings.openai_api_key or self.settings.minimax_api_key:
            try:
                response = self.agent_runtime.generate_structured_output(
                    self._build_agent_descriptor(),
                    user_prompt=(
                        "Generate the initial coding draft for this task.\n\n"
                        f"Issue #{issue.issue_number}: {issue.title}\n"
                        f"Branch: {head_branch}\n\n"
                        "Issue body:\n"
                        f"{issue.body.strip() or 'Issue body is empty.'}\n\n"
                        "Approved plan:\n"
                        f"{plan.model_dump_json(indent=2)}"
                    ),
                    output_contract=(
                        "Return strict JSON with keys `artifact_markdown`, `commit_message`, and `file_changes`. "
                        "`artifact_markdown` must be markdown for `.sleep_coding/issue-<number>.md`. "
                        "`commit_message` must be one concise git commit message. "
                        "`file_changes` must be an array of objects with keys `path`, `content`, and optional `description`. "
                        "Only include relative repo paths and include tests when code changes are proposed."
                    ),
                )
                return (
                    SleepCodingExecutionDraft.model_validate_json(response.output_text),
                    response.usage.model_copy(update={"step_name": "sleep_coding_execution"}),
                )
            except Exception:
                if self.settings.app_env != "test":
                    raise
        draft = self._build_heuristic_execution_draft(issue, plan, head_branch)
        usage = self._estimate_usage(
            step_name="sleep_coding_execution",
            input_text=(
                f"Issue #{issue.issue_number}: {issue.title}\n"
                f"Branch: {head_branch}\n\n"
                f"{issue.body.strip() or 'Issue body is empty.'}\n\n"
                f"{plan.model_dump_json(indent=2)}"
            ),
            output_text=draft.model_dump_json(),
        )
        return draft, usage

    def _build_heuristic_execution_draft(
        self,
        issue: SleepCodingIssue,
        plan: SleepCodingPlan,
        head_branch: str,
    ) -> SleepCodingExecutionDraft:
        artifact_markdown = (
            f"## Summary\n{plan.summary}\n\n"
            "## Scope\n"
            + "\n".join(f"- {item}" for item in plan.scope)
            + "\n\n## Validation\n"
            + "\n".join(f"- {item}" for item in plan.validation)
            + "\n\n## Risks\n"
            + "\n".join(f"- {item}" for item in plan.risks)
            + "\n\n## Working Branch\n"
            + f"- {head_branch}"
        )
        file_changes = self._build_heuristic_file_changes(issue)
        return SleepCodingExecutionDraft(
            artifact_markdown=artifact_markdown,
            commit_message=f"Sleep coding: issue #{issue.issue_number}",
            file_changes=file_changes,
        )

    def _build_heuristic_file_changes(
        self,
        issue: SleepCodingIssue,
    ) -> list[SleepCodingFileChange]:
        issue_text = f"{issue.title}\n{issue.body}".lower()
        marker = f"<!-- ralph-e2e-issue-{issue.issue_number} -->"
        if "readme" in issue_text:
            readme_path = self.repo_path / "README.md"
            if readme_path.exists():
                existing = readme_path.read_text(encoding="utf-8")
                if marker not in existing:
                    content = existing.rstrip() + f"\n\n{marker}\n"
                    return [
                        SleepCodingFileChange(
                            path="README.md",
                            content=content,
                            description="Append an issue marker to README for MVP integration validation.",
                        )
                    ]
        if any(keyword in issue_text for keyword in ("doc", "docs", "documentation", "markdown")):
            path = f"docs/e2e/issue-{issue.issue_number}.md"
            content = (
                f"# Ralph E2E Issue {issue.issue_number}\n\n"
                f"{marker}\n\n"
                f"Issue: {issue.title}\n"
            )
            return [
                SleepCodingFileChange(
                    path=path,
                    content=content,
                    description="Create a minimal documentation artifact for MVP integration validation.",
                )
            ]
        return []

    def _estimate_usage(
        self,
        *,
        step_name: str,
        input_text: str,
        output_text: str,
    ) -> TokenUsage:
        provider = self.settings.resolved_llm_default_provider
        model = self.settings.resolved_llm_default_model
        usage = self.token_counter.estimate_text_usage(
            provider=provider,
            model=model,
            input_text=input_text,
            output_text=output_text,
            existing_usage=TokenUsage(),
        )
        return usage.model_copy(
            update={
                "provider": provider,
                "model_name": model,
                "message_count": 2,
                "step_name": step_name,
                "cost_usd": self.pricing.calculate_cost_usd(
                    provider=provider,
                    model=model,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    cache_read_tokens=usage.cache_read_tokens,
                    cache_write_tokens=usage.cache_write_tokens,
                ),
            }
        )

    def _record_task_usage(
        self,
        *,
        request_id: str | None,
        step_name: str,
        usage: TokenUsage,
    ) -> None:
        if not request_id:
            return
        try:
            self.ledger.append_usage(
                request_id=request_id,
                run_id=str(uuid4()),
                usage=usage.model_copy(update={"step_name": step_name}),
                step_name=step_name,
            )
        except ValueError:
            # Direct task APIs and gateway intent shortcuts may not have persisted a
            # request ledger row yet. Skip child-step usage instead of failing task flow.
            return

    def _render_plan_comment(self, plan: SleepCodingPlan) -> str:
        scope = "\n".join(f"- {item}" for item in plan.scope)
        validation = "\n".join(f"- {item}" for item in plan.validation)
        risks = "\n".join(f"- {item}" for item in plan.risks)
        return (
            "## Ralph Plan\n"
            f"{plan.summary}\n\n"
            f"### Scope\n{scope}\n\n"
            f"### Validation\n{validation}\n\n"
            f"### Risks\n{risks}"
        )

    def _render_pr_comment(
        self,
        *,
        issue: SleepCodingIssue,
        pull_request: SleepCodingPullRequest,
        plan: SleepCodingPlan,
        validation: ValidationResult,
        head_branch: str,
    ) -> str:
        return (
            "## Ralph PR Ready\n"
            f"- 来源 Issue: #{issue.issue_number} {issue.title}\n"
            f"- Issue: {issue.html_url or 'n/a'}\n"
            f"- PR: {pull_request.html_url or 'pending'}\n"
            f"- Branch: {head_branch}\n"
            f"- Plan Summary: {plan.summary}\n"
            f"- Validation: {validation.status} ({validation.command})\n"
            f"- Dry run: {pull_request.is_dry_run}\n"
            "- 下一步: 等待 Code Review 与最终交付通知"
        )

    def _issue_creator_display(self, issue: SleepCodingIssue) -> str:
        if issue.creator_name and issue.creator_login:
            return f"{issue.creator_name} (@{issue.creator_login})"
        if issue.creator_login:
            return f"@{issue.creator_login}"
        if issue.creator_name:
            return issue.creator_name
        return "n/a"

    def _summarize_issue_for_notification(
        self,
        issue: SleepCodingIssue,
        plan: SleepCodingPlan,
    ) -> str:
        normalized = " ".join(issue.body.split())
        if normalized:
            return normalized[:240]
        return plan.summary

    def _render_plan_preview(self, plan: SleepCodingPlan) -> list[str]:
        steps: list[str] = []
        for item in plan.scope:
            if item.strip():
                steps.append(item.strip())
        for item in plan.validation:
            if item.strip():
                steps.append(f"验证: {item.strip()}")
        if not steps and plan.summary.strip():
            steps.append(plan.summary.strip())
        return [f"{index}. {item}" for index, item in enumerate(steps[:5], start=1)]

    def _build_agent_descriptor(self) -> AgentDescriptor:
        return AgentDescriptor(
            agent_id="ralph",
            workspace=self.settings.resolved_sleep_coding_workspace,
            skill_names=self.settings.resolved_sleep_coding_skills,
            mcp_servers=self.settings.resolved_sleep_coding_mcp_servers,
            model_profile=self.settings.resolved_sleep_coding_model_profile,
            system_instruction=(
                "Plan and execute software tasks with concrete code changes, tests, and GitHub workflow hygiene."
            ),
        )

    def _get_issue(
        self,
        repo: str,
        issue_number: int,
        title_override: str | None = None,
        body_override: str | None = None,
    ) -> SleepCodingIssue:
        server = self._require_github_server("get_issue")
        result = self.mcp_client.call_tool(
            MCPToolCall(
                server=server,
                tool="get_issue",
                arguments={"repo": repo, "issue_number": issue_number},
            )
        )
        payload = self._coerce_mapping(result.content)
        return SleepCodingIssue.model_validate(
            {
                "issue_number": payload.get("number", issue_number),
                "title": payload.get("title") or title_override or f"Sleep coding issue #{issue_number}",
                "body": payload.get("body") or body_override or "",
                "state": payload.get("state", "open"),
                "html_url": payload.get("html_url"),
                "labels": payload.get("labels", []),
                "is_dry_run": False,
            }
        )

    def _create_issue_comment(
        self,
        repo: str,
        issue_number: int,
        body: str,
    ) -> GitHubCommentLike:
        server = self._require_github_server("create_issue_comment")
        result = self.mcp_client.call_tool(
            MCPToolCall(
                server=server,
                tool="create_issue_comment",
                arguments={"repo": repo, "issue_number": issue_number, "body": body},
            )
        )
        payload = self._coerce_mapping(result.content)
        return GitHubCommentLike(
            html_url=self._coerce_html_url(payload),
            is_dry_run=False,
        )

    def _apply_labels(
        self,
        repo: str,
        issue_number: int,
        labels: list[str],
    ) -> GitHubLabelLike:
        if not labels:
            return GitHubLabelLike(labels=[], is_dry_run=False)
        server = self._require_github_server("apply_labels")
        result = self.mcp_client.call_tool(
            MCPToolCall(
                server=server,
                tool="apply_labels",
                arguments={"repo": repo, "issue_number": issue_number, "labels": labels},
            )
        )
        payload = self._coerce_mapping(result.content)
        resolved = payload.get("labels", labels)
        return GitHubLabelLike(
            labels=list(resolved) if isinstance(resolved, list) else labels,
            is_dry_run=False,
        )

    def _create_pull_request(
        self,
        repo: str,
        issue: SleepCodingIssue,
        plan: SleepCodingPlan,
        validation: ValidationResult,
        head_branch: str,
        base_branch: str,
    ) -> SleepCodingPullRequest:
        title = f"[Ralph] #{issue.issue_number} {issue.title}"
        body = (
            "## Summary\n"
            f"{plan.summary}\n\n"
            "## Validation\n"
            f"- {validation.command}\n"
            f"- status: {validation.status}\n"
            f"- exit_code: {validation.exit_code}\n"
        )
        server = self._require_github_server("create_pull_request")
        for attempt in range(3):
            try:
                result = self.mcp_client.call_tool(
                    MCPToolCall(
                        server=server,
                        tool="create_pull_request",
                        arguments={
                            "repo": repo,
                            "title": title,
                            "body": body,
                            "head_branch": head_branch,
                            "base_branch": base_branch,
                        },
                    )
                )
                payload = self._coerce_mapping(result.content)
                pr_url = self._coerce_html_url(payload)
                pr_number = payload.get("number")
                if pr_number is None and pr_url:
                    match = re.search(r"/pull/(?P<number>\d+)$", pr_url)
                    if match:
                        pr_number = int(match.group("number"))
                return SleepCodingPullRequest.model_validate(
                    {
                        "title": payload.get("title") or title,
                        "body": payload.get("body") or body,
                        "html_url": pr_url,
                        "pr_number": pr_number,
                        "state": payload.get("state", "open"),
                        "labels": [],
                        "is_dry_run": False,
                    }
                )
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2)

    def _coerce_mapping(self, content: object) -> dict[str, Any]:
        if isinstance(content, dict):
            return content
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    return item
        raise ValueError("MCP response did not contain a mapping payload")

    def _require_github_server(self, tool: str) -> str:
        server = self.settings.mcp_github_server_name
        if server not in self.mcp_client.available_servers():
            raise RuntimeError(
                f"GitHub MCP server `{server}` is not configured. Define it in {self.settings.resolved_mcp_config_path.name}."
            )
        if not self.mcp_client.has_tool(server, tool):
            raise RuntimeError(
                f"GitHub MCP server `{server}` does not expose required tool `{tool}`."
            )
        return server

    def _coerce_html_url(self, payload: dict[str, Any]) -> str | None:
        for key in ("html_url", "url"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _insert_task(
        self,
        connection: sqlite3.Connection,
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
            token_usage=usage,
            background_follow_up_status=row["background_follow_up_status"],
            background_follow_up_error=row["background_follow_up_error"],
            last_error=row["last_error"],
            kickoff_request_id=row["kickoff_request_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _ensure_status(self, current_status: str, allowed_statuses: set[str]) -> None:
        if current_status not in allowed_statuses:
            expected = ", ".join(sorted(allowed_statuses))
            raise ValueError(f"Action is not allowed from status={current_status}. Expected one of: {expected}")
