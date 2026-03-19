from __future__ import annotations

import re
import shlex
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.control.context import ContextAssemblyService
from app.core.config import Settings, get_settings
from app.channel.notifications import ChannelNotificationService
from app.agents.ralph.drafting import RalphDraftingService
from app.agents.ralph.github_bridge import (
    GitHubCommentLike,
    GitHubLabelLike,
    RalphGitHubBridge,
)
from app.agents.ralph.store import SleepCodingTaskStore
from app.infra.git_workspace import GitWorkspaceService
from app.ledger.service import TokenLedgerService
from app.control.events import ControlEventType
from app.models.schemas import (
    GitExecutionResult,
    SleepCodingExecutionDraft,
    SleepCodingFileChange,
    SleepCodingIssue,
    SleepCodingPlan,
    SleepCodingPullRequest,
    SleepCodingTask,
    SleepCodingTaskActionRequest,
    SleepCodingTaskRequest,
    TaskAction,
    TaskStatus,
    TokenUsage,
    ValidationResult,
)
from app.runtime.agent_runtime import AgentDescriptor, AgentRuntime
from app.runtime.mcp import MCPClient, build_default_mcp_client
from app.services.session_registry import SessionRegistryService
from app.services.task_registry import TaskRegistryService


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
            resolved
            and resolved[0].startswith("python")
            and self.project_root is not None
        ):
            project_python = self.project_root / ".venv" / "bin" / "python"
            if project_python.exists():
                resolved[0] = str(project_python)
        if (
            len(resolved) >= 2
            and resolved[0].endswith("python")
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
        self.tasks = tasks or TaskRegistryService(self.settings)
        self.sessions = sessions or SessionRegistryService(self.settings)
        self.context = ContextAssemblyService(self.sessions)
        self.drafting = RalphDraftingService(
            settings=self.settings,
            repo_path=self.repo_path,
            context=self.context,
            tasks=self.tasks,
            agent_runtime=self.agent_runtime,
        )
        self.github = RalphGitHubBridge(self.settings, self.mcp_client)
        self.store = SleepCodingTaskStore(self.settings.resolved_database_path, self.ledger)
        self.database_path = self.store.database_path
        self.sleep_coding_labels = self.settings.resolved_sleep_coding_labels

    def _sync_helpers(self) -> None:
        self.drafting.agent_runtime = self.agent_runtime
        self.github.mcp_client = self.mcp_client

    def _ensure_parent_dir(self) -> None:
        self.store.ensure_parent_dir()
        self.database_path = self.store.database_path

    def _connect(self) -> sqlite3.Connection:
        return self.store.connect()

    def _initialize_schema(self) -> None:
        self.store.initialize_schema()

    def start_task(self, payload: SleepCodingTaskRequest) -> SleepCodingTask:
        repo = payload.repo or self.settings.resolved_github_repository
        task_id = str(uuid4())
        head_branch = payload.head_branch or f"codex/issue-{payload.issue_number}-sleep-coding"
        pending_usage: tuple[str, str, TokenUsage] | None = None
        pending_memories: list[tuple[str, str]] = []
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
            self.store.insert_task(
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
            self.store.append_event(connection, task_id, "task_created", {"status": "created"})
            self.tasks.append_event(
                control_task.task_id,
                "sleep_coding_task_created",
                {"domain_task_id": task_id, "issue_number": payload.issue_number},
                connection=connection,
            )
            self.store.update_status(connection, task_id, "planning")
            self.tasks.update_task(control_task.task_id, status="planning", connection=connection)
            plan, plan_usage = self._build_plan(issue, run_session.session_id)
            if payload.request_id:
                pending_usage = (payload.request_id, "sleep_coding_plan", plan_usage)
            comment_body = self._render_plan_comment(plan)
            comment = self._create_issue_comment(repo, payload.issue_number, comment_body)
            labels = sorted(set(issue.labels + self.sleep_coding_labels))
            label_result = self._apply_labels(repo, payload.issue_number, labels)
            self.store.update_task_payloads(
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
            self.store.append_event(
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
            self.tasks.append_domain_event(
                control_task.task_id,
                ControlEventType.PLAN_READY,
                {"domain_task_id": task_id, "plan_summary": plan.summary},
                connection=connection,
            )
            pending_memories.append(
                (
                    run_session.session_id,
                    f"Plan ready for Issue #{issue.issue_number}: {plan.summary}",
                )
            )
            self.store.append_event(
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
                self.store.append_event(
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
        for session_id, summary in pending_memories:
            self.context.record_short_memory(session_id, summary)
        return self.get_task(task_id)

    def apply_action(
        self,
        task_id: str,
        payload: SleepCodingTaskActionRequest,
    ) -> SleepCodingTask:
        pending_usage: tuple[str, str, TokenUsage] | None = None
        pending_memories: list[tuple[str, str]] = []
        with closing(self._connect()) as connection:
            task = self._get_task_row(connection, task_id)
            action = payload.action
            if action == "approve_plan":
                pending_usage = self._handle_approve_plan(connection, task, pending_memories)
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
        for session_id, summary in pending_memories:
            self.context.record_short_memory(session_id, summary)
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> SleepCodingTask:
        return self.store.load_task(task_id)

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
            self.store.append_event(
                current_connection,
                task_id,
                f"background_follow_up_{status}",
                event_payload,
            )
            if owned_connection:
                current_connection.commit()
            row = self.store.get_task_row(current_connection, task_id)
            events = self.store.list_events(current_connection, task_id)
            return self.store.deserialize_task(row, events)
        finally:
            if owned_connection:
                current_connection.close()

    def _handle_approve_plan(
        self,
        connection: sqlite3.Connection,
        task: sqlite3.Row,
        pending_memories: list[tuple[str, str]],
    ) -> tuple[str, str, TokenUsage] | None:
        self._ensure_status(task["status"], {"awaiting_confirmation", "changes_requested"})
        was_awaiting_confirmation = task["status"] == "awaiting_confirmation"
        self.store.update_status(connection, task["task_id"], "coding")
        self._sync_control_task(task, status="coding", connection=connection)
        self.store.append_event(connection, task["task_id"], "coding_started", {})
        git_execution = self.git_workspace.prepare_worktree(task["head_branch"])
        plan = SleepCodingPlan.model_validate_json(task["plan_payload"])
        issue = SleepCodingIssue.model_validate_json(task["issue_payload"])
        execution, execution_usage = self._build_execution_draft(
            issue,
            plan,
            task["head_branch"],
            task["control_task_id"],
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
        self.store.update_task_payloads(
            connection,
            task["task_id"],
            status="coding",
            git_execution=git_execution,
        )
        self.store.append_event(
            connection,
            task["task_id"],
            "worktree_prepared",
            {
                "worktree_path": git_execution.worktree_path,
                "artifact_path": git_execution.artifact_path,
                "is_dry_run": git_execution.is_dry_run,
            },
        )
        self.store.append_event(
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
        control_task = self.tasks.get_task(task["control_task_id"])
        run_session_id = control_task.payload.get("run_session_id")
        if isinstance(run_session_id, str) and run_session_id:
            pending_memories.append(
                (
                    run_session_id,
                    f"Coding draft generated on branch {task['head_branch']} with commit message `{execution.commit_message}`.",
                )
            )
        self.store.update_status(connection, task["task_id"], "validating")
        self._sync_control_task(task, status="validating", connection=connection)

        validation_repo_path = (
            Path(git_execution.worktree_path)
            if git_execution.worktree_path and not git_execution.is_dry_run
            else self.repo_path
        )
        validation = self.validator.run(validation_repo_path)
        if validation.status == "failed":
            self.store.update_task_payloads(
                connection,
                task["task_id"],
                status="failed",
                git_execution=git_execution,
                validation=validation,
                last_error="Local validation failed.",
            )
            self.store.append_event(
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
            self.store.append_event(
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
        self.store.append_event(
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
        self.store.append_event(
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
        self.store.update_task_payloads(
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
        self.store.append_event(
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
        self.store.append_event(
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
        self.store.update_status(connection, task["task_id"], "changes_requested")
        self._sync_control_task(task, status="changes_requested", connection=connection)
        self.store.append_event(connection, task["task_id"], "changes_requested", {})

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
        self.store.update_status(connection, task["task_id"], target_status)
        self._sync_control_task(task, status=target_status, connection=connection)
        self.store.append_event(connection, task["task_id"], action, {"status": target_status})
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
            self.store.append_event(
                connection,
                task_id,
                "worktree_cleanup_failed",
                {"error": str(exc)},
            )
            return
        self.store.append_event(
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

    def _build_plan(
        self,
        issue: SleepCodingIssue,
        run_session_id: str | None = None,
    ) -> tuple[SleepCodingPlan, TokenUsage]:
        self._sync_helpers()
        return self.drafting.build_plan(issue, run_session_id)

    def _build_heuristic_plan(self, issue: SleepCodingIssue) -> SleepCodingPlan:
        return self.drafting.build_heuristic_plan(issue)

    def _build_execution_draft(
        self,
        issue: SleepCodingIssue,
        plan: SleepCodingPlan,
        head_branch: str,
        control_task_id: str | None = None,
    ) -> tuple[SleepCodingExecutionDraft, TokenUsage]:
        self._sync_helpers()
        return self.drafting.build_execution_draft(issue, plan, head_branch, control_task_id)

    def _build_heuristic_execution_draft(
        self,
        issue: SleepCodingIssue,
        plan: SleepCodingPlan,
        head_branch: str,
    ) -> SleepCodingExecutionDraft:
        return self.drafting.build_heuristic_execution_draft(issue, plan, head_branch)

    def _build_heuristic_file_changes(
        self,
        issue: SleepCodingIssue,
    ) -> list[SleepCodingFileChange]:
        return self.drafting.build_heuristic_file_changes(issue)

    def _estimate_usage(
        self,
        *,
        step_name: str,
        input_text: str,
        output_text: str,
    ) -> TokenUsage:
        return self.drafting.estimate_usage(
            step_name=step_name,
            input_text=input_text,
            output_text=output_text,
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
        return self.drafting.render_plan_comment(plan)

    def _render_pr_comment(
        self,
        *,
        issue: SleepCodingIssue,
        pull_request: SleepCodingPullRequest,
        plan: SleepCodingPlan,
        validation: ValidationResult,
        head_branch: str,
    ) -> str:
        return self.drafting.render_pr_comment(
            issue=issue,
            pull_request=pull_request,
            plan=plan,
            validation=validation,
            head_branch=head_branch,
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
        return self.drafting.summarize_issue_for_notification(issue, plan)

    def _render_plan_preview(self, plan: SleepCodingPlan) -> list[str]:
        return self.drafting.render_plan_preview(plan)

    def _build_agent_descriptor(self) -> AgentDescriptor:
        return self.drafting.build_agent_descriptor()

    def _get_issue(
        self,
        repo: str,
        issue_number: int,
        title_override: str | None = None,
        body_override: str | None = None,
    ) -> SleepCodingIssue:
        self._sync_helpers()
        return self.github.get_issue(repo, issue_number, title_override, body_override)

    def _create_issue_comment(
        self,
        repo: str,
        issue_number: int,
        body: str,
    ) -> GitHubCommentLike:
        self._sync_helpers()
        return self.github.create_issue_comment(repo, issue_number, body)

    def _apply_labels(
        self,
        repo: str,
        issue_number: int,
        labels: list[str],
    ) -> GitHubLabelLike:
        self._sync_helpers()
        return self.github.apply_labels(repo, issue_number, labels)

    def _create_pull_request(
        self,
        repo: str,
        issue: SleepCodingIssue,
        plan: SleepCodingPlan,
        validation: ValidationResult,
        head_branch: str,
        base_branch: str,
    ) -> SleepCodingPullRequest:
        self._sync_helpers()
        return self.github.create_pull_request(
            repo=repo,
            issue=issue,
            plan=plan,
            validation=validation,
            head_branch=head_branch,
            base_branch=base_branch,
        )

    def _coerce_mapping(self, content: object) -> dict[str, Any]:
        return self.github.coerce_mapping(content)

    def _require_github_server(self, tool: str) -> str:
        return self.github.require_github_server(tool)

    def _coerce_html_url(self, payload: dict[str, Any]) -> str | None:
        return self.github.coerce_html_url(payload)

    def _get_task_row(self, connection: sqlite3.Connection, task_id: str) -> sqlite3.Row:
        return self.store.get_task_row(connection, task_id)

    def _ensure_status(self, current_status: str, allowed_statuses: set[str]) -> None:
        if current_status not in allowed_statuses:
            expected = ", ".join(sorted(allowed_statuses))
            raise ValueError(f"Action is not allowed from status={current_status}. Expected one of: {expected}")
