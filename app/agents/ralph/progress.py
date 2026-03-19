from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from app.control.events import ControlEventType
from app.models.schemas import GitExecutionResult, SleepCodingPullRequest, TokenUsage, ValidationResult

if TYPE_CHECKING:
    from app.agents.ralph.application import SleepCodingService


class RalphTaskProgress:
    def __init__(self, service: SleepCodingService) -> None:
        self.service = service

    def record_plan_ready(
        self,
        *,
        connection: sqlite3.Connection,
        control_task_id: str,
        task_id: str,
        title: str,
        issue_number: int,
        issue_url: str | None,
        plan_summary: str,
        issue_comment_url: str | None,
        is_dry_run: bool,
    ) -> None:
        self.service.store.append_event(
            connection,
            task_id,
            "plan_generated",
            {
                "summary": plan_summary,
                "issue_comment_url": issue_comment_url,
                "is_dry_run": is_dry_run,
            },
        )
        self.service.tasks.update_task(
            control_task_id,
            status="awaiting_confirmation",
            title=title,
            issue_number=issue_number,
            payload_patch={"plan_summary": plan_summary, "issue_url": issue_url},
            connection=connection,
        )
        event_payload = {"domain_task_id": task_id, "plan_summary": plan_summary}
        self.service.tasks.append_event(
            control_task_id,
            "plan_ready",
            event_payload,
            connection=connection,
        )
        self.service.tasks.append_domain_event(
            control_task_id,
            ControlEventType.PLAN_READY,
            event_payload,
            connection=connection,
        )

    def record_validation_failure(
        self,
        *,
        connection: sqlite3.Connection,
        task: sqlite3.Row,
        git_execution: GitExecutionResult,
        validation: ValidationResult,
    ) -> None:
        self.service.store.update_task_payloads(
            connection,
            task["task_id"],
            status="failed",
            git_execution=git_execution,
            validation=validation,
            last_error="Local validation failed.",
        )
        self.service.store.append_event(
            connection,
            task["task_id"],
            "validation_failed",
            {"exit_code": validation.exit_code},
        )
        self.service._sync_control_task(
            task,
            status="failed",
            payload_patch={
                "validation_status": validation.status,
                "last_error": "Local validation failed.",
            },
            connection=connection,
        )

    def notify(
        self,
        connection: sqlite3.Connection,
        *,
        task_id: str,
        stage: str,
        title: str,
        lines: list[str],
    ) -> None:
        notification = self.service.channel.notify(title=title, lines=lines)
        self.service.store.append_event(
            connection,
            task_id,
            "channel_notified",
            {
                "provider": notification.provider,
                "delivered": notification.delivered,
                "is_dry_run": notification.is_dry_run,
                "stage": stage,
            },
        )

    def publish_pull_request(
        self,
        *,
        connection: sqlite3.Connection,
        task: sqlite3.Row,
        git_execution: GitExecutionResult,
        validation: ValidationResult,
        pull_request: SleepCodingPullRequest,
        labels: list[str],
        labels_dry_run: bool,
        created: bool,
    ) -> None:
        self.service.store.update_task_payloads(
            connection,
            task["task_id"],
            status="in_review",
            git_execution=git_execution,
            validation=validation,
            pull_request=pull_request.model_copy(update={"labels": labels}),
            last_error=None,
        )
        self.service.store.append_event(
            connection,
            task["task_id"],
            "pr_opened" if created else "pr_updated",
            {
                "pr_url": pull_request.html_url,
                "pr_number": pull_request.pr_number,
                "is_dry_run": pull_request.is_dry_run,
            },
        )
        self.service._sync_control_task(
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
            self.service.tasks.update_task(
                task["control_task_id"],
                external_ref=f"github_pr:{task['repo']}#{pull_request.pr_number}",
                connection=connection,
            )
        self.service.store.append_event(
            connection,
            task["task_id"],
            "labels_synced",
            {
                "target": "pull_request",
                "labels": labels,
                "is_dry_run": labels_dry_run,
            },
        )

    def handle_validation_failure(
        self,
        *,
        connection: sqlite3.Connection,
        task: sqlite3.Row,
        git_execution: GitExecutionResult,
        validation: ValidationResult,
        execution_usage: TokenUsage,
        title: str,
        lines: list[str],
    ) -> tuple[str, str, TokenUsage] | None:
        self.record_validation_failure(
            connection=connection,
            task=task,
            git_execution=git_execution,
            validation=validation,
        )
        self.notify(
            connection,
            task_id=task["task_id"],
            stage="validation_failed",
            title=title,
            lines=lines,
        )
        self.service._cleanup_worktree(connection, task["task_id"], task["head_branch"])
        self.service._sync_task_tokens(connection, task)
        if task["kickoff_request_id"]:
            return (task["kickoff_request_id"], "sleep_coding_execution", execution_usage)
        return None
