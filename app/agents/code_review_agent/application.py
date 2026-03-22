from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from app.agents.code_review_agent.bridge import ReviewCommentBridge
from app.agents.code_review_agent.context import ReviewContextBuilder
from app.agents.code_review_agent.target import ReviewTarget
from app.agents.code_review_agent.skill import (
    ReviewSkillRunResult,
    ReviewSkillService,
    count_findings_by_severity,
)
from app.agents.code_review_agent.store import ReviewRunStore, ReviewWorkspaceSupport
from app.control.context import ContextAssemblyService
from app.control.events import ControlEventType
from app.control.session_registry import SessionRegistryService
from app.control.task_registry import TaskRegistryService
from app.core.config import Settings, get_settings
from app.models.schemas import ReviewActionRequest, ReviewFinding, ReviewRun, ReviewSkillOutput, ReviewStartRequest, SleepCodingTaskActionRequest, TokenUsage
from app.runtime.mcp import MCPClient, build_default_mcp_client
from app.agents.ralph import SleepCodingService

class ReviewService:
    def __init__(
        self,
        settings: Settings | None = None,
        sleep_coding: SleepCodingService | None = None,
        skill: ReviewSkillService | None = None,
        mcp_client: MCPClient | None = None,
        tasks: TaskRegistryService | None = None,
        sessions: SessionRegistryService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.sleep_coding = sleep_coding or SleepCodingService(settings=self.settings)
        self.tasks = tasks or TaskRegistryService(self.settings)
        self.sessions = sessions or SessionRegistryService(self.settings)
        self.context = ContextAssemblyService(self.sessions)
        self.workspace_support = ReviewWorkspaceSupport(self.settings, self.context)
        self.mcp_client = mcp_client or self.sleep_coding.mcp_client or build_default_mcp_client(self.settings)
        self.skill = skill or ReviewSkillService(
            self.settings,
            mcp_client=self.mcp_client,
        )
        self.ledger = self.sleep_coding.ledger
        self.github_server = self.settings.mcp_github_server_name
        self.bridge = ReviewCommentBridge(
            github_server=self.github_server,
            mcp_client=self.mcp_client,
            mcp_config_name=self.settings.resolved_mcp_config_path.name,
        )
        self.store = ReviewRunStore(self.settings)
        self.context_builder = ReviewContextBuilder(
            context=self.context,
            sleep_coding=self.sleep_coding,
            workspace_support=self.workspace_support,
        )
        self.database_path = self.store.database_path
        self.review_runs_dir = self.store.review_runs_dir

    def _sync_helpers(self) -> None:
        self.bridge.mcp_client = self.mcp_client
        self.bridge.github_server = self.github_server

    def start_review(self, payload: ReviewStartRequest, *, write_comment: bool = True) -> ReviewRun:
        self._sync_helpers()
        review_id = str(uuid4())
        target = self._build_review_target(payload.task_id)
        parent_control_task = self._resolve_parent_control_task(target.task_id)
        sleep_task = self.sleep_coding.get_task(target.task_id)
        parent_run_session_id = (
            parent_control_task.payload.get("run_session_id")
            if parent_control_task
            else None
        )
        context = self.context_builder.build_context(target, parent_run_session_id)
        run_result = self.skill.run(target, context)
        structured = self._apply_blocking_override(target, run_result.output)
        review_usage = run_result.token_usage.model_copy(update={"step_name": "code_review"})
        severity_counts = count_findings_by_severity(structured.findings)
        is_blocking = (
            structured.blocking
            if structured.blocking is not None
            else any(severity_counts.get(level, 0) > 0 for level in ("P0", "P1"))
        )
        content = structured.review_markdown or structured.summary
        artifact_path = self._write_artifact(review_id, target, content)
        comment = self.bridge.write_comment(target, content) if write_comment else None
        run_session = self.sessions.create_child_session(
            session_type="run_session",
            parent_session_id=parent_run_session_id,
            agent_id="code-review-agent",
            user_id=parent_control_task.user_id if parent_control_task else None,
            source=parent_control_task.source if parent_control_task else None,
            external_ref=f"review-run:{review_id}",
            payload={"task_id": target.task_id, "blocking": is_blocking},
        )
        self.context.record_short_memory(
            run_session.session_id,
            f"Review completed for task {target.task_id}; blocking={is_blocking}; summary={structured.summary}",
        )
        control_task = self.tasks.create_task(
            task_type="code_review",
            agent_id="code-review-agent",
            status="completed",
            parent_task_id=parent_control_task.task_id if parent_control_task else None,
            repo=target.repo,
            issue_number=None,
            title=structured.summary,
            external_ref=f"review_run:{review_id}",
            payload={
                "review_id": review_id,
                "task_id": target.task_id,
                "blocking": is_blocking,
                "artifact_path": str(artifact_path),
                "comment_url": comment.html_url if comment is not None else None,
                "run_session_id": run_session.session_id,
                "owner_agent": "code-review-agent",
                "source_agent": "ralph",
                "machine_output": {
                    "blocking": is_blocking,
                    "severity_counts": severity_counts,
                    "findings": [
                        finding.model_dump(mode="json")
                        for finding in structured.findings
                    ],
                    "repair_strategy": structured.repair_strategy,
                },
                "human_output": {
                    "summary": structured.summary,
                    "review_markdown": structured.review_markdown,
                    "comment_url": comment.html_url if comment is not None else None,
                },
                "review_target": target.model_dump(mode="json"),
                "handoff": {
                    "task_id": target.task_id,
                    "session_id": run_session.session_id,
                    "owner_agent": "code-review-agent",
                    "source": "ralph",
                    "workspace_ref": target.workspace_path or target.head_branch,
                    "validation_result": (
                        sleep_task.validation.status
                        if sleep_task is not None
                        else None
                    ),
                    "review_scope": {
                        "repo": target.repo,
                        "pr_number": target.pr_number,
                        "url": target.url,
                        "base_branch": target.base_branch,
                        "head_branch": target.head_branch,
                    },
                    "status": "in_review",
                },
            },
        )
        if parent_control_task is not None:
            self.tasks.append_event(
                parent_control_task.task_id,
                "handoff_to_code_review",
                {
                    "child_task_id": control_task.task_id,
                    "review_id": review_id,
                    "owner_agent": "code-review-agent",
                    "run_session_id": run_session.session_id,
                    "review_scope": {
                        "repo": target.repo,
                        "pr_number": target.pr_number,
                        "head_branch": target.head_branch,
                    },
                },
            )

        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO review_runs (
                    review_id,
                    control_task_id,
                    parent_task_id,
                    source_payload,
                    target_payload,
                    status,
                    artifact_path,
                    comment_url,
                    summary,
                    content,
                    findings_payload,
                    severity_counts_payload,
                    is_blocking,
                    run_mode,
                    task_id,
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
                    reviewed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    review_id,
                    control_task.task_id,
                    control_task.parent_task_id,
                    target.model_dump_json(),
                    target.model_dump_json(),
                    "completed",
                    str(artifact_path),
                    comment.html_url if comment is not None else None,
                    structured.summary,
                    content,
                    json.dumps([finding.model_dump(mode="json") for finding in structured.findings], ensure_ascii=True),
                    json.dumps(severity_counts, ensure_ascii=True),
                    1 if is_blocking else 0,
                    structured.run_mode,
                    target.task_id,
                    review_usage.prompt_tokens,
                    review_usage.completion_tokens,
                    review_usage.total_tokens,
                    review_usage.cache_read_tokens,
                    review_usage.cache_write_tokens,
                    review_usage.reasoning_tokens,
                    review_usage.message_count,
                    review_usage.duration_seconds,
                    review_usage.model_name,
                    review_usage.provider,
                    review_usage.cost_usd,
                    review_usage.step_name,
                ),
            )
            connection.commit()
        self._sync_parent_review_projection(
            target.task_id,
            review_id=review_id,
            is_blocking=is_blocking,
            review_round=self.count_task_reviews(target.task_id),
            status="completed",
            summary=structured.summary,
        )
        self._record_review_usage(target, review_usage)
        self.tasks.append_event(
            control_task.task_id,
            "review_completed",
            {
                "review_id": review_id,
                "blocking": is_blocking,
                "severity_counts": severity_counts,
                "token_usage": review_usage.model_dump(mode="json"),
            },
        )
        self.tasks.append_domain_event(
            control_task.task_id,
            ControlEventType.REVIEW_COMPLETED,
            {
                "review_id": review_id,
                "blocking": is_blocking,
                "severity_counts": severity_counts,
                "token_usage": review_usage.model_dump(mode="json"),
            },
        )

        return self.get_review(review_id)

    def get_review(self, review_id: str) -> ReviewRun:
        return self.store.get_review(review_id)

    def _apply_blocking_override(
        self,
        target: ReviewTarget,
        structured: ReviewSkillOutput,
    ) -> ReviewSkillOutput:
        if (
            not self.settings.resolved_review_force_blocking_first_pass
            or not target.task_id
        ):
            return structured
        if self.count_blocking_reviews(target.task_id) > 0:
            return structured
        if structured.blocking:
            return structured
        synthetic_finding = ReviewFinding(
            severity="P1",
            title="Integration blocking checkpoint",
            detail=(
                "Forced blocking finding for integration validation. "
                "Ralph should apply one repair loop and re-run review."
            ),
            file_path=".sleep_coding/issue-checkpoint.md",
            line=1,
            suggestion="Update the generated task artifact to acknowledge the blocking review.",
        )
        findings = [synthetic_finding, *structured.findings]
        markdown = structured.review_markdown or structured.summary
        markdown += (
            "\n\n### Integration Override\n"
            "- Forced a single blocking review pass to validate Ralph repair automation.\n"
        )
        return structured.model_copy(
            update={
                "summary": "Forced blocking review for integration validation.",
                "findings": findings,
                "repair_strategy": [
                    "Apply one follow-up change and rerun the review loop.",
                    *structured.repair_strategy,
                ],
                "blocking": True,
                "review_markdown": markdown,
            }
        )

    def apply_action(
        self,
        review_id: str,
        payload: ReviewActionRequest,
        *,
        write_remote: bool = True,
    ) -> ReviewRun:
        self._sync_helpers()
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
        review_target = review.target
        if review.control_task_id:
            next_owner_agent = "ralph" if new_status == "changes_requested" else None
            self.tasks.update_task(
                review.control_task_id,
                status=new_status,
                payload_patch={
                    "review_decision": new_status,
                    "next_owner_agent": next_owner_agent,
                },
            )
            self.tasks.append_event(
                review.control_task_id,
                f"review_{new_status}",
                {"review_id": review_id, "task_id": review.task_id},
            )
            self.tasks.append_domain_event(
                review.control_task_id,
                (
                    ControlEventType.REVIEW_APPROVED
                    if new_status == "approved"
                    else ControlEventType.REVIEW_CHANGES_REQUESTED
                    if new_status == "changes_requested"
                    else f"review.{new_status}"
                ),
                {"review_id": review_id, "task_id": review.task_id},
            )
        if review.task_id:
            parent_control_task = self._resolve_parent_control_task(review.task_id)
            if parent_control_task is not None:
                self.tasks.append_event(
                    parent_control_task.task_id,
                    "review_returned",
                    {
                        "review_id": review_id,
                        "task_id": review.task_id,
                        "decision": new_status,
                        "next_owner_agent": next_owner_agent,
                    },
                )
            self._sync_parent_review_projection(
                review.task_id,
                review_id=review.review_id,
                is_blocking=review.is_blocking,
                review_round=self.count_task_reviews(review.task_id),
                status=new_status,
                summary=review.summary,
            )
            if write_remote and review_target.repo and review_target.pr_number:
                if payload.action == "request_changes":
                    self.bridge.write_pr_review(
                        review_target,
                        event="REQUEST_CHANGES",
                        body=self.bridge.render_review_decision_comment(review, payload.action),
                    )
                elif payload.action == "approve_review":
                    self.bridge.write_pr_review(
                        review_target,
                        event="APPROVE",
                        body=self.bridge.render_review_decision_comment(review, payload.action),
                    )
            if payload.action == "request_changes":
                self.sleep_coding.apply_action(
                    review.task_id,
                    SleepCodingTaskActionRequest(action="request_changes"),
                )
            elif payload.action == "approve_review":
                task = self.sleep_coding.get_task(review.task_id)
                if task.status != "approved":
                    self.sleep_coding.apply_action(
                        review.task_id,
                        SleepCodingTaskActionRequest(action="approve_pr"),
                    )
        return self.get_review(review_id)

    def trigger_for_task(self, task_id: str, *, write_comment: bool = True) -> ReviewRun:
        return self.start_review(ReviewStartRequest(task_id=task_id), write_comment=write_comment)

    def publish_final_result(self, review_id: str, action: str) -> ReviewRun:
        review = self.get_review(review_id)
        body = self.bridge.render_review_decision_comment(review, action)
        review_target = review.target
        comment = self.bridge.write_comment(
            review_target,
            body,
        )
        with closing(self._connect()) as connection:
            connection.execute(
                """
                UPDATE review_runs
                SET comment_url = ?, updated_at = CURRENT_TIMESTAMP
                WHERE review_id = ?
                """,
                (comment.html_url, review_id),
            )
            connection.commit()
        return self.get_review(review_id)

    def list_task_reviews(self, task_id: str) -> list[ReviewRun]:
        return self.store.list_task_reviews(task_id)

    def count_blocking_reviews(self, task_id: str) -> int:
        return self.store.count_blocking_reviews(task_id)

    def count_task_reviews(self, task_id: str) -> int:
        return len(self.list_task_reviews(task_id))

    def _connect(self) -> sqlite3.Connection:
        return self.store.connect()

    def _write_artifact(self, review_id: str, target: ReviewTarget, content: str) -> Path:
        return self.store.write_artifact(review_id, target, content)

    def _resolve_parent_control_task(self, task_id: str | None):
        if task_id:
            sleep_task = self.sleep_coding.get_task(task_id)
            if sleep_task.control_task_id:
                return self.tasks.get_task(sleep_task.control_task_id)
        return None

    def _build_review_target(self, task_id: str) -> ReviewTarget:
        if not task_id.strip():
            raise ValueError("MVP review requires a sleep_coding_task task_id")
        task = self.sleep_coding.get_task(task_id)
        target = ReviewTarget(
            task_id=task.task_id,
            repo=task.repo,
            pr_number=task.pull_request.pr_number if task.pull_request else None,
            url=task.pull_request.html_url if task.pull_request else None,
            base_branch=task.base_branch,
            head_branch=task.head_branch,
        )
        worktree_path = task.git_execution.worktree_path
        if not worktree_path or task.git_execution.is_dry_run:
            return target
        return ReviewTarget(
            task_id=task.task_id,
            repo=task.repo,
            pr_number=task.pull_request.pr_number if task.pull_request else None,
            url=task.pull_request.html_url if task.pull_request else target.url,
            workspace_path=worktree_path,
            base_branch=task.base_branch,
            head_branch=task.head_branch,
        )

    def _record_review_usage(self, target: ReviewTarget, usage: TokenUsage) -> None:
        sleep_task = self.sleep_coding.get_task(target.task_id)
        if not sleep_task.kickoff_request_id:
            return
        try:
            self.ledger.append_usage(
                request_id=sleep_task.kickoff_request_id,
                run_id=str(uuid4()),
                usage=usage,
                step_name=usage.step_name,
            )
        except ValueError:
            return

    def _sync_parent_review_projection(
        self,
        task_id: str,
        *,
        review_id: str,
        is_blocking: bool,
        review_round: int,
        status: str,
        summary: str,
    ) -> None:
        parent_control_task = self._resolve_parent_control_task(task_id)
        if parent_control_task is None:
            return
        blocking_count = self.count_blocking_reviews(task_id)
        self.tasks.update_task(
            parent_control_task.task_id,
            payload_patch={
                "latest_review_id": review_id,
                "latest_review_blocking": is_blocking,
                "latest_review_status": status,
                "latest_review_summary": summary,
                "review_round": review_round,
                "blocking_review_count": blocking_count,
            },
        )
