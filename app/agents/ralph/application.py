from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.control.context import ContextAssemblyService
from app.core.config import Settings, get_settings
from app.channel.ralph import RalphNotificationBuilder
from app.channel.notifications import ChannelNotificationService
from app.agents.ralph.drafting import RalphDraftingService
from app.agents.ralph.github_bridge import (
    GitHubCommentLike,
    GitHubLabelLike,
    RalphGitHubBridge,
)
from app.agents.ralph.store import SleepCodingTaskStore
from app.agents.ralph.validation import ValidationRunner
from app.agents.ralph.workflow import RalphTaskWorkflow
from app.infra.git_workspace import GitWorkspaceService
from app.ledger.service import TokenLedgerService
from app.control.events import ControlEventType
from app.models.schemas import (
    GitExecutionResult,
    SleepCodingIssue,
    SleepCodingPullRequest,
    SleepCodingTask,
    SleepCodingTaskActionRequest,
    SleepCodingTaskRequest,
    TaskAction,
    TaskStatus,
    TokenUsage,
)
from app.runtime.agent_runtime import AgentDescriptor, AgentRuntime
from app.runtime.mcp import MCPClient, build_default_mcp_client
from app.services.session_registry import SessionRegistryService
from app.services.task_registry import TaskRegistryService

class SleepCodingService:
    def __init__(
        self,
        settings: Settings | None = None,
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
        self.channel_builder = RalphNotificationBuilder()
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
        self.workflow = RalphTaskWorkflow(self)
        self.database_path = self.store.database_path
        self.sleep_coding_labels = self.settings.resolved_sleep_coding_labels

    def _sync_helpers(self) -> None:
        self.drafting.agent_runtime = self.agent_runtime
        self.github.mcp_client = self.mcp_client

    def _connect(self) -> sqlite3.Connection:
        return self.store.connect()

    def start_task(self, payload: SleepCodingTaskRequest) -> SleepCodingTask:
        return self.workflow.start_task(payload)

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
                pending_usage = self.workflow.handle_approve_plan(connection, task, pending_memories)
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
            event_type = {
                "queued": "follow_up.queued",
                "processing": "follow_up.processing",
                "completed": "follow_up.completed",
                "failed": "follow_up.failed",
            }.get(status, f"follow_up.{status}")
            self.store.append_event(
                current_connection,
                task_id,
                event_type,
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
        worktree_path: Path | None = None,
        control_task_id: str | None = None,
    ) -> tuple[SleepCodingExecutionDraft, TokenUsage]:
        self._sync_helpers()
        return self.drafting.build_execution_draft(
            issue,
            plan,
            head_branch,
            worktree_path,
            control_task_id,
        )

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
