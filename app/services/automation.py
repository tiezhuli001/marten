from __future__ import annotations

from app.core.config import Settings, get_settings
from app.ledger.service import TokenLedgerService
from app.models.schemas import (
    ReviewActionRequest,
    ReviewRun,
    SleepCodingTask,
    SleepCodingTaskActionRequest,
    SleepCodingWorkerPollRequest,
    SleepCodingWorkerPollResponse,
    TokenUsage,
)
from app.services.channel import ChannelNotificationService
from app.services.background_jobs import (
    BackgroundJobService,
    get_background_job_service,
)
from app.services.review import ReviewService
from app.services.task_registry import TaskRegistryService
from app.services.sleep_coding import SleepCodingService
from app.services.sleep_coding_worker import SleepCodingWorkerService


class AutomationService:
    def __init__(
        self,
        settings: Settings | None = None,
        sleep_coding: SleepCodingService | None = None,
        review: ReviewService | None = None,
        worker: SleepCodingWorkerService | None = None,
        channel: ChannelNotificationService | None = None,
        ledger: TokenLedgerService | None = None,
        tasks: TaskRegistryService | None = None,
        background_jobs: BackgroundJobService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.sleep_coding = sleep_coding or SleepCodingService(settings=self.settings)
        self.review = review or ReviewService(
            settings=self.settings,
            sleep_coding=self.sleep_coding,
        )
        self.worker = worker or SleepCodingWorkerService(
            settings=self.settings,
            sleep_coding=self.sleep_coding,
        )
        self.channel = channel or ChannelNotificationService(self.settings)
        self.ledger = ledger or TokenLedgerService(self.settings)
        self.tasks = tasks or TaskRegistryService(self.settings)
        self.background_jobs = background_jobs or get_background_job_service()
        self.max_repair_rounds = self.settings.resolved_review_max_repair_rounds

    def handle_sleep_coding_action(
        self,
        task_id: str,
        action: str,
    ) -> SleepCodingTask:
        task = self.sleep_coding.apply_action(
            task_id,
            SleepCodingTaskActionRequest(action=action),  # type: ignore[arg-type]
        )
        return self._process_task(task)

    def handle_sleep_coding_action_async(
        self,
        task_id: str,
        action: str,
    ) -> SleepCodingTask:
        task = self.sleep_coding.apply_action(
            task_id,
            SleepCodingTaskActionRequest(action=action),  # type: ignore[arg-type]
        )
        self._schedule_follow_up(task)
        return self.sleep_coding.get_task(task.task_id)

    def process_worker_poll(
        self,
        payload: SleepCodingWorkerPollRequest,
    ) -> SleepCodingWorkerPollResponse:
        response = self.worker.poll_once(payload)
        processed_tasks = [self._process_task(task) for task in response.tasks]
        processed_task_ids = {task.task_id for task in processed_tasks}
        for claim in response.claims:
            if not claim.task_id or claim.task_id in processed_task_ids:
                continue
            if claim.status not in {"changes_requested", "in_review"}:
                continue
            self._process_task(self.sleep_coding.get_task(claim.task_id))
        return response.model_copy(update={"tasks": processed_tasks})

    def process_worker_poll_async(
        self,
        payload: SleepCodingWorkerPollRequest,
    ) -> SleepCodingWorkerPollResponse:
        response = self.worker.poll_once(payload)
        for task in response.tasks:
            self._schedule_follow_up(task)
        seen_task_ids = {task.task_id for task in response.tasks}
        for claim in response.claims:
            if not claim.task_id or claim.task_id in seen_task_ids:
                continue
            if claim.status not in {"changes_requested", "in_review"}:
                continue
            self._schedule_follow_up(self.sleep_coding.get_task(claim.task_id))
        return response

    def run_review_loop(self, task_id: str) -> SleepCodingTask:
        task = self.sleep_coding.get_task(task_id)
        return self._process_task(task)

    def _process_task(self, task: SleepCodingTask) -> SleepCodingTask:
        current_task = task
        while current_task.status in {"changes_requested", "in_review"}:
            if current_task.status == "changes_requested":
                blocking_reviews = self.review.count_blocking_reviews(current_task.task_id)
                if blocking_reviews >= self.max_repair_rounds:
                    return current_task
                current_task = self.sleep_coding.apply_action(
                    current_task.task_id,
                    SleepCodingTaskActionRequest(action="approve_plan"),
                )
                continue
            review = self.review.trigger_for_task(current_task.task_id)
            if review.is_blocking:
                blocking_reviews = self.review.count_blocking_reviews(current_task.task_id)
                if blocking_reviews >= self.max_repair_rounds:
                    self.review.apply_action(
                        review.review_id,
                        ReviewActionRequest(action="request_changes"),
                    )
                    current_task = self.sleep_coding.get_task(current_task.task_id)
                    self._notify_manual_handoff(current_task, review, blocking_reviews)
                    return current_task
                self.review.apply_action(
                    review.review_id,
                    ReviewActionRequest(action="request_changes"),
                )
                repaired_task = self.sleep_coding.apply_action(
                    current_task.task_id,
                    SleepCodingTaskActionRequest(action="approve_plan"),
                )
                current_task = repaired_task
                continue
            self.review.apply_action(
                review.review_id,
                ReviewActionRequest(action="approve_review"),
            )
            current_task = self.sleep_coding.get_task(current_task.task_id)
            self._notify_final_delivery(current_task, review)
            return current_task

        if current_task.status in {"approved", "failed", "cancelled"}:
            self._notify_final_delivery(current_task)
        return current_task

    def _schedule_follow_up(self, task: SleepCodingTask) -> None:
        if task.status not in {"changes_requested", "in_review"}:
            return
        scheduled = self.background_jobs.submit_unique(
            f"sleep-coding-follow-up:{task.task_id}",
            self._run_scheduled_follow_up,
            task.task_id,
        )
        if not scheduled:
            return
        current_task = self.sleep_coding.get_task(task.task_id)
        if current_task.background_follow_up_status != "idle":
            return
        self._mark_follow_up_state(
            task.task_id,
            "queued",
            payload={"task_status": task.status},
        )

    def _run_scheduled_follow_up(self, task_id: str) -> SleepCodingTask:
        self._mark_follow_up_state(task_id, "processing")
        try:
            task = self.run_review_loop(task_id)
        except Exception as exc:
            self._mark_follow_up_state(
                task_id,
                "failed",
                error=str(exc),
            )
            raise
        self._mark_follow_up_state(
            task_id,
            "completed",
            payload={"task_status": task.status},
        )
        return task

    def _mark_follow_up_state(
        self,
        task_id: str,
        state: str,
        *,
        error: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        task = self.sleep_coding.set_background_follow_up_state(
            task_id,
            state,
            error=error,
            payload=payload,
        )
        if task.control_task_id:
            control_payload = {
                "background_follow_up_status": state,
                "background_follow_up_error": error,
                **(payload or {}),
            }
            self.tasks.update_task(
                task.control_task_id,
                payload_patch=control_payload,
            )
            self.tasks.append_event(
                task.control_task_id,
                f"background_follow_up_{state}",
                {"domain_task_id": task_id, **control_payload},
            )
            control_task = self.tasks.get_task(task.control_task_id)
            if control_task.parent_task_id:
                self.tasks.append_event(
                    control_task.parent_task_id,
                    f"child_background_follow_up_{state}",
                    {
                        "child_control_task_id": task.control_task_id,
                        "domain_task_id": task_id,
                        **control_payload,
                    },
                )

    def _notify_manual_handoff(
        self,
        task: SleepCodingTask,
        review: ReviewRun,
        blocking_reviews: int,
    ) -> None:
        self.channel.notify(
            title=f"[Ralph] Manual review required for Issue #{task.issue_number}",
            lines=[
                f"Task: {task.task_id}",
                f"Repo: {task.repo}",
                f"PR: {task.pull_request.html_url if task.pull_request else 'n/a'}",
                f"Review: {review.comment_url or review.artifact_path or 'n/a'}",
                f"Blocking rounds: {blocking_reviews}/{self.max_repair_rounds}",
                "Status: changes_requested",
            ],
        )
        self._record_parent_result(
            task,
            event_type="child_handed_off",
            status="needs_attention",
            payload={
                "review_id": review.review_id,
                "blocking_reviews": blocking_reviews,
                "task_status": task.status,
            },
        )

    def _notify_final_delivery(
        self,
        task: SleepCodingTask,
        review: ReviewRun | None = None,
    ) -> None:
        title = self._build_final_delivery_title(task)
        self.channel.notify(
            title=title,
            lines=[
                f"来源: Issue #{task.issue_number}",
                f"仓库: {task.repo}",
                f"分支: {task.head_branch}",
                f"{self._pull_request_label(task.pull_request.html_url if task.pull_request else None)}: {task.pull_request.html_url if task.pull_request else 'n/a'}",
                f"Code Review: {'approved' if review and not review.is_blocking else 'changes_requested' if review else 'n/a'}",
                f"Issue: {task.issue.html_url or 'n/a'}",
                f"Review: {review.comment_url or review.artifact_path or 'n/a'}" if review else "Review: n/a",
                *self._render_work_summary_lines(task, review),
                *self._render_token_usage_lines(task, review),
            ],
        )
        self._record_parent_result(
            task,
            event_type="child_completed",
            status="completed" if task.status == "approved" else task.status,
            payload={
                "task_status": task.status,
                "review_id": review.review_id if review else None,
                "pr_url": task.pull_request.html_url if task.pull_request else None,
            },
        )

    def _record_parent_result(
        self,
        task: SleepCodingTask,
        *,
        event_type: str,
        status: str,
        payload: dict[str, object],
    ) -> None:
        if not task.control_task_id:
            return
        control_task = self.tasks.get_task(task.control_task_id)
        self.tasks.update_task(control_task.task_id, status=status, payload_patch=payload)
        self.tasks.append_event(
            control_task.task_id,
            event_type,
            {"domain_task_id": task.task_id, **payload},
        )
        if control_task.parent_task_id:
            self.tasks.update_task(control_task.parent_task_id, status=status, payload_patch=payload)
            self.tasks.append_event(
                control_task.parent_task_id,
                event_type,
                {"child_control_task_id": control_task.task_id, **payload},
            )

    def _render_token_usage_lines(
        self,
        task: SleepCodingTask,
        review: ReviewRun | None,
    ) -> list[str]:
        if task.kickoff_request_id:
            total_usage = self.ledger.get_request_usage(task.kickoff_request_id)
            plan_usage = self.ledger.get_request_usage(task.kickoff_request_id, ["sleep_coding_plan"])
            execution_usage = self.ledger.get_request_usage(
                task.kickoff_request_id,
                ["sleep_coding_execution"],
            )
            review_usage = (
                review.token_usage
                if review is not None and review.token_usage.total_tokens > 0
                else self.ledger.get_request_usage(task.kickoff_request_id, ["code_review"])
            )
        else:
            total_usage = task.token_usage
            plan_usage = TokenUsage()
            execution_usage = task.token_usage
            review_usage = review.token_usage if review is not None else TokenUsage()
        return [
            "三、Token 消耗统计",
            f"输入 Token: {total_usage.prompt_tokens:,}",
            f"输出 Token: {total_usage.completion_tokens:,}",
            f"总 Token: {total_usage.total_tokens:,}",
            f"缓存读取 Token: {total_usage.cache_read_tokens:,}",
            f"缓存写入 Token: {total_usage.cache_write_tokens:,}",
            f"推理 Token: {total_usage.reasoning_tokens:,}",
            f"消息数量: {total_usage.message_count:,}",
            f"处理时间: {total_usage.duration_seconds:.2f} 秒",
            f"总成本: ${total_usage.cost_usd:.3f}",
            "阶段分布:",
            self._render_stage_usage_line("Plan", plan_usage),
            self._render_stage_usage_line("Execution", execution_usage),
            self._render_stage_usage_line("Review", review_usage),
        ]

    def _render_stage_usage_line(
        self,
        stage: str,
        usage: TokenUsage,
    ) -> str:
        return (
            f"{stage}: 输入 {usage.prompt_tokens:,} · 输出 {usage.completion_tokens:,} · "
            f"总 {usage.total_tokens:,} · 成本 ${usage.cost_usd:.3f}"
        )

    def _build_final_delivery_title(self, task: SleepCodingTask) -> str:
        summary = self._latest_commit_message(task) or task.issue.title
        return f"Ralph 任务完成：{summary}"

    def _render_work_summary_lines(
        self,
        task: SleepCodingTask,
        review: ReviewRun | None,
    ) -> list[str]:
        lines = ["工作总结:"]
        lines.append(f"需求摘要: {task.issue.title}")
        if task.plan:
            lines.append(f"计划摘要: {task.plan.summary}")
        commit_message = self._latest_commit_message(task)
        if commit_message:
            lines.append(f"提交摘要: {commit_message}")
        file_changes = self._latest_file_changes(task)
        if file_changes:
            lines.extend(
                [
                    "一、修改文件清单",
                    f"本次共修改 {len(file_changes)} 个文件。",
                    "| 文件路径 | 变更类型 | 说明 |",
                    "|---------|---------|------|",
                ]
            )
            for item in file_changes:
                path = str(item.get("path") or "n/a")
                description = str(item.get("description") or "代码变更")
                lines.append(f"| {path} | {self._infer_change_type(path, description)} | {description} |")
            lines.extend(self._render_key_change_lines(file_changes))
        lines.extend(
            [
                "四、总结",
                *self._render_conclusion_lines(task, file_changes, review),
            ]
        )
        return lines

    def _latest_commit_message(self, task: SleepCodingTask) -> str | None:
        for event in reversed(task.events):
            if event.event_type != "coding_draft_generated":
                continue
            commit_message = event.payload.get("commit_message")
            if isinstance(commit_message, str) and commit_message.strip():
                return commit_message.strip()
        return None

    def _latest_file_changes(self, task: SleepCodingTask) -> list[dict[str, object]]:
        for event in reversed(task.events):
            if event.event_type != "coding_draft_generated":
                continue
            file_changes = event.payload.get("file_changes")
            if not isinstance(file_changes, list):
                continue
            normalized: list[dict[str, object]] = []
            for item in file_changes:
                if isinstance(item, dict):
                    normalized.append(item)
            if normalized:
                return normalized
            artifact_path = event.payload.get("artifact_path")
            if isinstance(artifact_path, str) and artifact_path.strip():
                return [
                    {
                        "path": artifact_path.strip(),
                        "description": "Ralph 任务产物与执行摘要",
                    }
                ]
        return []

    def _render_key_change_lines(self, file_changes: list[dict[str, object]]) -> list[str]:
        lines = ["二、关键变更说明"]
        for index, item in enumerate(file_changes[:5], start=1):
            path = str(item.get("path") or "n/a")
            description = str(item.get("description") or "代码变更")
            lines.append(f"{index}. {path} - {description}")
        return lines

    def _render_conclusion_lines(
        self,
        task: SleepCodingTask,
        file_changes: list[dict[str, object]],
        review: ReviewRun | None,
    ) -> list[str]:
        lines = [
            f"本次工作主要完成了 {max(len(file_changes), 1)} 项改动收口。",
        ]
        for index, item in enumerate(file_changes[:3], start=1):
            description = str(item.get("description") or "代码变更")
            lines.append(f"{index}. {description}")
        if review is not None:
            lines.append(
                f"Code Review 结果：{'已通过' if not review.is_blocking else '仍有阻塞项'}。"
            )
        lines.append("Ralph 已完成任务，请过目。")
        return lines

    def _infer_change_type(self, path: str, description: str) -> str:
        normalized = f"{path} {description}".lower()
        if any(keyword in normalized for keyword in ("新增", "create", "add", "new")):
            return "新增"
        if any(keyword in normalized for keyword in ("删除", "remove", "delete")):
            return "删除"
        return "修改"

    def _pull_request_label(self, url: str | None) -> str:
        if isinstance(url, str) and "/-/merge_requests/" in url:
            return "Merge Request"
        return "Pull Request"
