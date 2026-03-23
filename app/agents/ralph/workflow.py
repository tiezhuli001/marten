from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from app.agents.ralph.progress import RalphTaskProgress
from app.models.schemas import (
    RalphCodingArtifact,
    GitExecutionResult,
    SleepCodingIssue,
    SleepCodingPlan,
    SleepCodingTask,
    SleepCodingTaskRequest,
    TokenUsage,
    ValidationResult,
)

if TYPE_CHECKING:
    from app.agents.ralph.application import SleepCodingService


class RalphTaskWorkflow:
    def __init__(self, service: SleepCodingService) -> None:
        self.service = service
        self.progress = RalphTaskProgress(service)

    def start_task(self, payload: SleepCodingTaskRequest) -> SleepCodingTask:
        repo = payload.repo or self.service.settings.resolved_github_repository
        task_id = str(uuid4())
        head_branch = payload.head_branch or f"codex/issue-{payload.issue_number}-sleep-coding"
        pending_usage: tuple[str, str, TokenUsage] | None = None
        pending_memories: list[tuple[str, str]] = []
        issue = self.service._get_issue(
            repo=repo,
            issue_number=payload.issue_number,
            title_override=payload.issue_title,
            body_override=payload.issue_body,
        )
        validation = ValidationResult(
            status="pending",
            command=self.service.settings.resolved_sleep_coding_validation_command,
        )
        git_execution = GitExecutionResult()
        parent_task = (
            self.service.tasks.get_task(payload.parent_task_id)
            if payload.parent_task_id
            else self.service.tasks.find_parent_for_issue(repo, payload.issue_number)
        )
        inherited_request_id = None
        if parent_task is not None:
            candidate_request_id = parent_task.payload.get("request_id")
            if isinstance(candidate_request_id, str) and candidate_request_id.strip():
                inherited_request_id = candidate_request_id
        kickoff_request_id = payload.request_id or inherited_request_id
        control_task = self.service.tasks.create_task(
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
                "source_endpoint_id": payload.source_endpoint_id,
                "delivery_endpoint_id": payload.delivery_endpoint_id,
            },
        )
        parent_agent_session_id = parent_task.payload.get("agent_session_id") if parent_task else None
        run_session = self.service.sessions.create_child_session(
            session_type="run_session",
            parent_session_id=parent_agent_session_id,
            agent_id="ralph",
            user_id=parent_task.user_id if parent_task else None,
            source=parent_task.source if parent_task else None,
            external_ref=f"sleep-coding-run:{task_id}",
            payload={"repo": repo, "issue_number": payload.issue_number},
        )
        control_task = self.service.tasks.update_task(
            control_task.task_id,
            payload_patch={
                "run_session_id": run_session.session_id,
                "owner_agent": "ralph",
                "source_agent": parent_task.agent_id if parent_task else "gateway",
                "source_endpoint_id": payload.source_endpoint_id,
                "delivery_endpoint_id": payload.delivery_endpoint_id,
                "handoff": {
                    "task_id": task_id,
                    "session_id": run_session.session_id,
                    "owner_agent": "ralph",
                    "source": parent_task.agent_id if parent_task else "gateway",
                    "repo": repo,
                    "issue_number": payload.issue_number,
                    "issue_title": issue.title,
                    "issue_url": issue.html_url,
                    "requirement": issue.body,
                    "acceptance": issue.body,
                    "status": "claimed",
                },
            },
        )
        with closing(self.service._connect()) as connection:
            self.service.store.insert_task(
                connection=connection,
                task_id=task_id,
                control_task_id=control_task.task_id,
                parent_task_id=control_task.parent_task_id,
                payload=payload.model_copy(update={"request_id": kickoff_request_id}),
                repo=repo,
                head_branch=head_branch,
                issue=issue,
                git_execution=git_execution,
                validation=validation,
            )
            self.service.store.append_event(connection, task_id, "task_created", {"status": "created"})
            self.service.tasks.append_event(
                control_task.task_id,
                "sleep_coding_task_created",
                {"domain_task_id": task_id, "issue_number": payload.issue_number},
                connection=connection,
            )
            if parent_task is not None:
                self.service.tasks.append_event(
                    parent_task.task_id,
                    "handoff_to_ralph",
                    {
                        "child_task_id": control_task.task_id,
                        "domain_task_id": task_id,
                        "owner_agent": "ralph",
                        "run_session_id": run_session.session_id,
                        "repo": repo,
                        "issue_number": payload.issue_number,
                    },
                    connection=connection,
                )
            self.service.store.update_status(connection, task_id, "planning")
            self.service.tasks.update_task(control_task.task_id, status="planning", connection=connection)
            plan, plan_usage = self.service._build_plan(issue, run_session.session_id)
            if kickoff_request_id:
                pending_usage = (kickoff_request_id, "sleep_coding_plan", plan_usage)
            comment_body = self.service._render_plan_comment(plan)
            comment = self.service._create_issue_comment(repo, payload.issue_number, comment_body)
            labels = sorted(set(issue.labels + self.service.sleep_coding_labels))
            label_result = self.service._apply_labels(repo, payload.issue_number, labels)
            self.service.store.update_task_payloads(
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
            self.progress.record_plan_ready(
                connection=connection,
                control_task_id=control_task.task_id,
                task_id=task_id,
                title=issue.title,
                issue_number=payload.issue_number,
                issue_url=issue.html_url or comment.html_url,
                plan_summary=plan.summary,
                issue_comment_url=comment.html_url,
                is_dry_run=comment.is_dry_run,
            )
            pending_memories.append(
                (
                    run_session.session_id,
                    f"Plan ready for Issue #{issue.issue_number}: {plan.summary}",
                )
            )
            self.service.store.append_event(
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
                title, lines = self.service.channel_builder.build_plan_ready(
                    issue_title=issue.title,
                    issue_number=payload.issue_number,
                    repo=repo,
                    head_branch=head_branch,
                    issue_url=issue.html_url,
                    plan_summary=plan.summary,
                    plan_preview=self.service._render_plan_preview(plan),
                )
                self.progress.notify(
                    connection,
                    task_id=task_id,
                    stage="plan_ready",
                    title=title,
                    lines=lines,
                )
            connection.commit()
        if pending_usage is not None:
            request_id, step_name, usage = pending_usage
            self.service._record_task_usage(
                request_id=request_id,
                step_name=step_name,
                usage=usage,
            )
            self.service._refresh_task_tokens(task_id)
        for session_id, summary in pending_memories:
            self.service.context.record_short_memory(session_id, summary)
        return self.service.get_task(task_id)

    def handle_approve_plan(
        self,
        connection: sqlite3.Connection,
        task: sqlite3.Row,
        pending_memories: list[tuple[str, str]],
    ) -> tuple[str, str, TokenUsage] | None:
        self.service._ensure_status(task["status"], {"awaiting_confirmation", "changes_requested"})
        self.service.store.update_status(connection, task["task_id"], "coding")
        self.service._sync_control_task(task, status="coding", connection=connection)
        self.service.store.append_event(connection, task["task_id"], "coding_started", {})
        git_execution = self.service.git_workspace.prepare_worktree(task["head_branch"])
        plan = SleepCodingPlan.model_validate_json(task["plan_payload"])
        issue = SleepCodingIssue.model_validate_json(task["issue_payload"])
        execution, execution_usage = self.service._build_execution_draft(
            issue,
            plan,
            task["head_branch"],
            Path(git_execution.worktree_path) if git_execution.worktree_path else None,
            task["control_task_id"],
        )
        artifact_result = self.service.git_workspace.write_task_artifact(
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
                    part for part in (git_execution.output, artifact_result.output) if part
                ),
                "is_dry_run": git_execution.is_dry_run and artifact_result.is_dry_run,
            }
        )
        self.service.store.update_task_payloads(
            connection,
            task["task_id"],
            status="coding",
            git_execution=git_execution,
        )
        self.service.store.append_event(
            connection,
            task["task_id"],
            "worktree_prepared",
            {
                "worktree_path": git_execution.worktree_path,
                "artifact_path": git_execution.artifact_path,
                "is_dry_run": git_execution.is_dry_run,
            },
        )
        self.service.store.append_event(
            connection,
            task["task_id"],
            "coding_draft_generated",
            {
                "commit_message": execution.commit_message,
                "artifact_path": git_execution.artifact_path,
                "generated_files": [change.path for change in execution.file_changes],
                "file_changes": [
                    {"path": change.path, "description": change.description}
                    for change in execution.file_changes
                ],
                "artifact": RalphCodingArtifact(
                    artifact_path=git_execution.artifact_path,
                    worktree_path=git_execution.worktree_path,
                    commit_message=execution.commit_message,
                    generated_files=[change.path for change in execution.file_changes],
                    file_changes=[
                        {"path": change.path, "description": change.description}
                        for change in execution.file_changes
                    ],
                ).model_dump(mode="json"),
            },
        )
        self.service.tasks.update_task(
            task["control_task_id"],
            payload_patch={
                "coding_artifact": RalphCodingArtifact(
                    artifact_path=git_execution.artifact_path,
                    worktree_path=git_execution.worktree_path,
                    commit_message=execution.commit_message,
                    generated_files=[change.path for change in execution.file_changes],
                    file_changes=[
                        {"path": change.path, "description": change.description}
                        for change in execution.file_changes
                    ],
                ).model_dump(mode="json"),
            },
            connection=connection,
        )
        control_task = self.service.tasks.get_task(task["control_task_id"])
        run_session_id = control_task.payload.get("run_session_id")
        if isinstance(run_session_id, str) and run_session_id:
            pending_memories.append(
                (
                    run_session_id,
                    f"Coding draft generated on branch {task['head_branch']} with commit message `{execution.commit_message}`.",
                )
            )
        self.service.store.update_status(connection, task["task_id"], "validating")
        self.service._sync_control_task(task, status="validating", connection=connection)

        validation_repo_path = (
            Path(git_execution.worktree_path)
            if git_execution.worktree_path and not git_execution.is_dry_run
            else self.service.repo_path
        )
        validation = self.service.validator.run(validation_repo_path)
        if validation.status == "failed":
            title, lines = self.service.channel_builder.build_validation_failed(
                issue_number=task["issue_number"],
                repo=task["repo"],
                task_id=task["task_id"],
                head_branch=task["head_branch"],
                validation=validation,
            )
            return self.progress.handle_validation_failure(
                connection=connection,
                task=task,
                git_execution=git_execution,
                validation=validation,
                execution_usage=execution_usage,
                title=title,
                lines=lines,
            )
        self._finalize_review_candidate(
            connection=connection,
            task=task,
            issue=issue,
            plan=plan,
            git_execution=git_execution,
            validation=validation,
        )
        if task["kickoff_request_id"]:
            return (task["kickoff_request_id"], "sleep_coding_execution", execution_usage)
        return None

    def resume_after_validation(
        self,
        connection: sqlite3.Connection,
        task: sqlite3.Row,
        pending_memories: list[tuple[str, str]],
    ) -> tuple[str, str, TokenUsage] | None:
        del pending_memories
        issue = SleepCodingIssue.model_validate_json(task["issue_payload"])
        if not task["plan_payload"]:
            raise ValueError(f"Cannot resume validated task without plan payload: {task['task_id']}")
        plan = SleepCodingPlan.model_validate_json(task["plan_payload"])
        git_execution = GitExecutionResult.model_validate_json(task["git_execution_payload"])
        validation = ValidationResult.model_validate_json(task["validation_payload"])
        if validation.status != "passed":
            raise ValueError(
                f"Resume after validation requires passed validation state, got {validation.status}"
            )
        self._finalize_review_candidate(
            connection=connection,
            task=task,
            issue=issue,
            plan=plan,
            git_execution=git_execution,
            validation=validation,
        )
        return None

    def _finalize_review_candidate(
        self,
        *,
        connection: sqlite3.Connection,
        task: sqlite3.Row,
        issue: SleepCodingIssue,
        plan: SleepCodingPlan,
        git_execution: GitExecutionResult,
        validation: ValidationResult,
    ) -> None:
        self.service.ensure_review_handoff_validation_evidence(
            task,
            validation,
            connection,
        )
        commit_result = self.service.git_workspace.commit_changes(
            branch=task["head_branch"],
            message=self._resolve_commit_message(task, connection),
        )
        self.service.store.append_event(
            connection,
            task["task_id"],
            "git_commit",
            {
                "status": commit_result.status,
                "commit_sha": commit_result.commit_sha,
                "is_dry_run": commit_result.is_dry_run,
            },
        )
        push_result = self.service.git_workspace.push_branch(task["head_branch"])
        self.service.store.append_event(
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
                "worktree_path": push_result.worktree_path
                or commit_result.worktree_path
                or git_execution.worktree_path,
                "artifact_path": git_execution.artifact_path,
                "commit_sha": push_result.commit_sha or commit_result.commit_sha,
                "output": "\n".join(
                    part
                    for part in (git_execution.output, commit_result.output, push_result.output)
                    if part
                ),
                "is_dry_run": git_execution.is_dry_run
                and commit_result.is_dry_run
                and push_result.is_dry_run,
            }
        )
        existing_pull_request = self.service._resolve_existing_pull_request(task, connection)
        pull_request = existing_pull_request or self.service._create_pull_request(
            repo=task["repo"],
            issue=issue,
            plan=plan,
            validation=validation,
            head_branch=task["head_branch"],
            base_branch=task["base_branch"],
        )
        pr_labels = self.service._apply_labels(
            task["repo"],
            pull_request.pr_number or task["issue_number"],
            self.service.sleep_coding_labels,
        )
        self.service._create_issue_comment(
            task["repo"],
            task["issue_number"],
            self.service._render_pr_comment(
                issue=issue,
                pull_request=pull_request,
                plan=plan,
                validation=validation,
                head_branch=task["head_branch"],
            ),
        )
        self.progress.publish_pull_request(
            connection=connection,
            task=task,
            git_execution=combined_git_execution,
            validation=validation,
            pull_request=pull_request,
            labels=pr_labels.labels or self.service.sleep_coding_labels,
            labels_dry_run=pr_labels.is_dry_run,
            created=existing_pull_request is None,
        )

    def _resolve_commit_message(
        self,
        task: sqlite3.Row,
        connection: sqlite3.Connection,
    ) -> str:
        events = self.service.store.list_events(connection, task["task_id"])
        for event in reversed(events):
            if event["event_type"] != "coding_draft_generated":
                continue
            try:
                payload = json.loads(event["payload"] or "{}")
            except json.JSONDecodeError:
                continue
            commit_message = payload.get("commit_message")
            if isinstance(commit_message, str) and commit_message.strip():
                return commit_message.strip()
        control_task_id = task["control_task_id"]
        if control_task_id:
            control_task = self.service.tasks.get_task(control_task_id, connection=connection)
            coding_artifact = control_task.payload.get("coding_artifact")
            if isinstance(coding_artifact, dict):
                commit_message = coding_artifact.get("commit_message")
                if isinstance(commit_message, str) and commit_message.strip():
                    return commit_message.strip()
        return f"feat: resume sleep coding task {task['task_id']}"
