from __future__ import annotations

from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from time import sleep

from app.agents.code_review_agent import ReviewService
from app.agents.ralph import SleepCodingService
from app.channel.delivery import DeliveryMessageBuilder
from app.channel.notifications import ChannelNotificationService
from app.control.events import ControlEvent, ControlEventBus, ControlEventType
from app.control.sleep_coding_worker import SleepCodingWorkerService
from app.control.task_registry import TaskRegistryService
from app.core.config import Settings, get_settings
from app.infra.background_jobs import (
    BackgroundJobService,
    get_background_job_service,
)
from app.ledger.service import TokenLedgerService
from app.models.schemas import (
    FinalDeliveryEvidence,
    ReviewActionRequest,
    ReviewRun,
    SleepCodingTask,
    SleepCodingTaskActionRequest,
    SleepCodingWorkerPollRequest,
    SleepCodingWorkerPollResponse,
    TerminalTaskEvidence,
    TokenUsage,
)


@dataclass(frozen=True)
class ReviewLoopDecision:
    action: str
    blocking_reviews: int = 0


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
        event_bus: ControlEventBus | None = None,
        sleep_fn: Callable[[float], None] | None = None,
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
        self.event_bus = event_bus or ControlEventBus(self.background_jobs)
        self.max_repair_rounds = self.settings.resolved_review_max_repair_rounds
        self.delivery = DeliveryMessageBuilder(self.ledger)
        default_sleep_fn = (lambda seconds: None) if self.settings.app_env == "test" else sleep
        self.sleep_fn = sleep_fn or default_sleep_fn
        self.event_bus.register(ControlEventType.FOLLOW_UP_REQUESTED, self._handle_follow_up_requested)

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
            resumed = self.sleep_coding.resume_task(claim.task_id)
            self._process_task(resumed)
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
            self._schedule_follow_up(self.sleep_coding.resume_task(claim.task_id))
        return response

    def run_review_loop(self, task_id: str) -> SleepCodingTask:
        task = self.sleep_coding.get_task(task_id)
        return self._process_task(task)

    def _process_task(self, task: SleepCodingTask) -> SleepCodingTask:
        current_task = task
        last_review: ReviewRun | None = None
        while True:
            blocking_reviews = self._get_blocking_review_count(current_task)
            decision = self._decide_review_loop_step(
                task_status=current_task.status,
                review_blocking=(
                    last_review.is_blocking
                    if last_review is not None
                    else self._get_latest_review_blocking(current_task)
                ),
                latest_review_status=(
                    last_review.status
                    if last_review is not None
                    else self._get_latest_review_status(current_task)
                ),
                blocking_reviews=blocking_reviews,
            )
            if decision.action == "rerun_coding":
                current_task = self._rerun_coding(current_task.task_id)
                self._clear_latest_review_projection(current_task)
                last_review = None
                continue
            if decision.action == "run_review":
                last_review = self.review.trigger_for_task(
                    current_task.task_id,
                    write_comment=not self.settings.resolved_review_writeback_final_only,
                )
                review_round = self._get_review_round(current_task, fallback_review=last_review)
                self._publish_review_feedback(current_task, last_review, review_round)
                continue
            if decision.action == "request_changes":
                last_review = self._require_latest_review(current_task, last_review)
                self.review.apply_action(
                    last_review.review_id,
                    ReviewActionRequest(action="request_changes"),
                    write_remote=not self.settings.resolved_review_writeback_final_only,
                )
                current_task = self._rerun_coding(current_task.task_id)
                self._clear_latest_review_projection(current_task)
                last_review = None
                continue
            if decision.action == "handoff":
                last_review = self._require_latest_review(current_task, last_review)
                self.review.apply_action(
                    last_review.review_id,
                    ReviewActionRequest(action="request_changes"),
                    write_remote=not self.settings.resolved_review_writeback_final_only,
                )
                if self.settings.resolved_review_writeback_final_only:
                    last_review = self.review.publish_final_result(
                        last_review.review_id,
                        "request_changes",
                    )
                current_task = self.sleep_coding.mark_needs_attention(
                    current_task.task_id,
                    reason="Reached maximum blocking review rounds.",
                )
                self._publish_manual_handoff(current_task, last_review, decision.blocking_reviews)
                return current_task
            if decision.action == "approve_review":
                last_review = self._require_latest_review(current_task, last_review)
                self.review.apply_action(
                    last_review.review_id,
                    ReviewActionRequest(action="approve_review"),
                    write_remote=not self.settings.resolved_review_writeback_final_only,
                )
                if self.settings.resolved_review_writeback_final_only:
                    last_review = self.review.publish_final_result(
                        last_review.review_id,
                        "approve_review",
                    )
                current_task = self.sleep_coding.get_task(current_task.task_id)
                self._publish_final_delivery(current_task, last_review)
                return current_task
            if decision.action == "deliver":
                self._publish_final_delivery(current_task)
            return current_task

    def _get_blocking_review_count(self, task: SleepCodingTask) -> int:
        control_task = self._get_control_task(task)
        if control_task is not None:
            count = control_task.payload.get("blocking_review_count")
            if isinstance(count, int) and count >= 0:
                return count
        return self.review.count_blocking_reviews(task.task_id)

    def _get_latest_review_blocking(self, task: SleepCodingTask) -> bool | None:
        control_task = self._get_control_task(task)
        if control_task is not None and "latest_review_blocking" in control_task.payload:
            value = control_task.payload.get("latest_review_blocking")
            if isinstance(value, bool):
                return value
        return None

    def _get_latest_review_status(self, task: SleepCodingTask) -> str | None:
        control_task = self._get_control_task(task)
        if control_task is None:
            return None
        value = control_task.payload.get("latest_review_status")
        if isinstance(value, str) and value.strip():
            return value
        return None

    def _get_review_round(
        self,
        task: SleepCodingTask,
        *,
        fallback_review: ReviewRun | None = None,
    ) -> int:
        control_task = self._get_control_task(task)
        if control_task is not None:
            review_round = control_task.payload.get("review_round")
            if isinstance(review_round, int) and review_round >= 1:
                return review_round
        if fallback_review is not None:
            return len(self.review.list_task_reviews(task.task_id))
        return 0

    def _get_control_task(self, task: SleepCodingTask):
        if not task.control_task_id:
            return None
        return self.tasks.get_task(task.control_task_id)

    def _require_latest_review(
        self,
        task: SleepCodingTask,
        review: ReviewRun | None,
    ) -> ReviewRun:
        if review is not None:
            return review
        reviews = self.review.list_task_reviews(task.task_id)
        if not reviews:
            raise ValueError(f"Review loop expected an existing review for task {task.task_id}")
        return reviews[-1]

    def _clear_latest_review_projection(self, task: SleepCodingTask) -> None:
        control_task = self._get_control_task(task)
        if control_task is None:
            return
        self.tasks.update_task(
            control_task.task_id,
            payload_patch={
                "latest_review_id": None,
                "latest_review_blocking": None,
                "latest_review_status": None,
                "latest_review_summary": None,
            },
        )

    def _rerun_coding(self, task_id: str) -> SleepCodingTask:
        return self.sleep_coding.apply_action(
            task_id,
            SleepCodingTaskActionRequest(action="approve_plan"),
        )

    def _schedule_follow_up(self, task: SleepCodingTask) -> None:
        if task.status not in {"changes_requested", "in_review"}:
            return
        scheduled = self.event_bus.publish_follow_up_requested(task.task_id)
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

    def _handle_follow_up_requested(self, event: ControlEvent) -> SleepCodingTask:
        task_id = event.payload.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError(f"{ControlEventType.FOLLOW_UP_REQUESTED} requires a task_id")
        return self._run_scheduled_follow_up(task_id)

    def _run_scheduled_follow_up(self, task_id: str) -> SleepCodingTask:
        self._mark_follow_up_state(task_id, "processing")
        try:
            delay_seconds = self.settings.resolved_review_follow_up_delay_seconds
            if delay_seconds > 0:
                self.sleep_fn(delay_seconds)
            task = self.run_review_loop(task_id)
        except Exception as exc:
            self._mark_follow_up_state(
                task_id,
                "failed",
                error=str(exc),
            )
            return self._escalate_follow_up_failure(task_id, str(exc))
        self._mark_follow_up_state(
            task_id,
            "completed",
            payload={"task_status": task.status},
        )
        return task

    def continue_gateway_workflow(
        self,
        *,
        intent: str,
        task_id: str | None,
    ) -> dict[str, object]:
        auto_approve_plan = self.settings.resolved_sleep_coding_worker_auto_approve_plan
        if intent == "general":
            poll = self.process_worker_poll_async(
                SleepCodingWorkerPollRequest(auto_approve_plan=auto_approve_plan)
            )
            return {
                "triggered": True,
                "mode": "worker_poll",
                "auto_approve_plan": poll.auto_approve_plan,
                "claimed_count": poll.claimed_count,
                "task_ids": [task.task_id for task in poll.tasks],
            }
        if intent == "sleep_coding" and task_id:
            if not auto_approve_plan:
                return {
                    "triggered": False,
                    "mode": "task_action",
                    "reason": "awaiting_confirmation",
                    "task_id": task_id,
                }
            task = self.handle_sleep_coding_action_async(task_id, "approve_plan")
            return {
                "triggered": True,
                "mode": "task_action",
                "action": "approve_plan",
                "task_id": task.task_id,
                "status": task.status,
            }
        return {
            "triggered": False,
            "mode": "noop",
            "reason": "no_follow_up_required",
        }

    def _decide_review_loop_step(
        self,
        *,
        task_status: str,
        review_blocking: bool | None = None,
        latest_review_status: str | None = None,
        blocking_reviews: int = 0,
    ) -> ReviewLoopDecision:
        if task_status == "changes_requested":
            if blocking_reviews >= self.max_repair_rounds:
                return ReviewLoopDecision("stop", blocking_reviews=blocking_reviews)
            return ReviewLoopDecision("rerun_coding", blocking_reviews=blocking_reviews)
        if task_status == "in_review":
            if review_blocking is None:
                return ReviewLoopDecision("run_review", blocking_reviews=blocking_reviews)
            if review_blocking and blocking_reviews >= self.max_repair_rounds:
                return ReviewLoopDecision("handoff", blocking_reviews=blocking_reviews)
            if review_blocking:
                return ReviewLoopDecision("request_changes", blocking_reviews=blocking_reviews)
            return ReviewLoopDecision("approve_review", blocking_reviews=blocking_reviews)
        if task_status == "approved":
            if latest_review_status is None:
                return ReviewLoopDecision("run_review", blocking_reviews=blocking_reviews)
            if latest_review_status == "completed":
                return ReviewLoopDecision("approve_review", blocking_reviews=blocking_reviews)
            if latest_review_status == "approved":
                return ReviewLoopDecision("deliver", blocking_reviews=blocking_reviews)
            if latest_review_status == "changes_requested":
                return ReviewLoopDecision("handoff", blocking_reviews=blocking_reviews)
            return ReviewLoopDecision("stop", blocking_reviews=blocking_reviews)
        if task_status in {"failed", "cancelled", "needs_attention"}:
            return ReviewLoopDecision("deliver", blocking_reviews=blocking_reviews)
        return ReviewLoopDecision("stop", blocking_reviews=blocking_reviews)

    def _mark_follow_up_state(
        self,
        task_id: str,
        state: str,
        *,
        error: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> SleepCodingTask:
        task = self.sleep_coding.set_background_follow_up_state(
            task_id,
            state,
            error=error,
            payload=payload,
        )
        if not task.control_task_id:
            return task

        control_payload = {
            "background_follow_up_status": state,
            "background_follow_up_error": error,
            **(payload or {}),
        }
        domain_event_type = {
            "queued": ControlEventType.FOLLOW_UP_QUEUED,
            "processing": ControlEventType.FOLLOW_UP_PROCESSING,
            "completed": ControlEventType.FOLLOW_UP_COMPLETED,
            "failed": ControlEventType.FOLLOW_UP_FAILED,
        }.get(state, f"follow_up.{state}")
        self.tasks.update_task(
            task.control_task_id,
            payload_patch=control_payload,
        )
        self.tasks.append_domain_event(
            task.control_task_id,
            domain_event_type,
            {"domain_task_id": task_id, **control_payload},
        )
        control_task = self.tasks.get_task(task.control_task_id)
        if control_task.parent_task_id:
            self.tasks.append_domain_event(
                control_task.parent_task_id,
                {
                    "queued": f"child.{ControlEventType.FOLLOW_UP_QUEUED}",
                    "processing": f"child.{ControlEventType.FOLLOW_UP_PROCESSING}",
                    "completed": f"child.{ControlEventType.FOLLOW_UP_COMPLETED}",
                    "failed": f"child.{ControlEventType.FOLLOW_UP_FAILED}",
                }.get(state, f"child.follow_up.{state}"),
                {
                    "child_control_task_id": task.control_task_id,
                    "domain_task_id": task_id,
                    **control_payload,
                },
            )
        return task

    def _escalate_follow_up_failure(
        self,
        task_id: str,
        reason: str,
    ) -> SleepCodingTask:
        task = self.sleep_coding.get_task(task_id)
        if task.status not in {"approved", "failed", "cancelled", "needs_attention"}:
            task = self.sleep_coding.mark_needs_attention(
                task_id,
                reason=f"Background follow-up failed: {reason}",
            )
        payload = {
            "task_status": task.status,
            "last_error": f"Background follow-up failed: {reason}",
            "escalation_reason": "follow_up_failed",
            "terminal_evidence": self._build_terminal_evidence(
                terminal_state="needs_attention",
                task=task,
                last_error=f"Background follow-up failed: {reason}",
            ).model_dump(mode="json"),
        }
        self._record_parent_result(
            task,
            event_type="child_handed_off",
            status="needs_attention",
            payload=payload,
        )
        self._record_parent_result(
            task,
            event_type="delivery.handed_off",
            status="needs_attention",
            payload=payload,
        )
        return task

    def _publish_review_feedback(
        self,
        task: SleepCodingTask,
        review: ReviewRun,
        review_round: int,
    ) -> None:
        title, lines = self.delivery.build_review_feedback(
            task,
            review,
            review_round=review_round,
            max_repair_rounds=self.max_repair_rounds,
        )
        notification = self.channel.notify(
            title=title,
            lines=lines,
            endpoint_id=self._resolve_delivery_endpoint_id(task),
        )
        self._record_notification(task, stage=f"review_round_{review_round}", notification=notification)

    def _publish_manual_handoff(
        self,
        task: SleepCodingTask,
        review: ReviewRun,
        blocking_reviews: int,
    ) -> None:
        title, lines = self.delivery.build_manual_handoff(
            task,
            review,
            blocking_reviews=blocking_reviews,
            max_repair_rounds=self.max_repair_rounds,
        )
        notification = self.channel.notify(
            title=title,
            lines=lines,
            endpoint_id=self._resolve_delivery_endpoint_id(task),
        )
        self._record_notification(task, stage="manual_handoff", notification=notification)
        payload = {
            "review_id": review.review_id,
            "latest_review_id": review.review_id,
            "latest_review_status": review.status,
            "latest_review_summary": review.summary,
            "blocking_reviews": blocking_reviews,
            "task_status": task.status,
            "review_round": self._get_review_round(task, fallback_review=review),
            "review_summary": review.summary,
            "repair_strategy": self._extract_review_repair_strategy(task, review),
            "terminal_evidence": self._build_terminal_evidence(
                terminal_state="needs_attention",
                task=task,
                review=review,
                last_error="Reached maximum blocking review rounds.",
            ).model_dump(mode="json"),
        }
        self._record_parent_result(task, event_type="child_handed_off", status="needs_attention", payload=payload)
        self._record_parent_result(task, event_type="delivery.handed_off", status="needs_attention", payload=payload)

    def _publish_final_delivery(
        self,
        task: SleepCodingTask,
        review: ReviewRun | None = None,
    ) -> None:
        review = review or self._resolve_final_review(task)
        if not self._can_publish_final_delivery(task, review):
            return
        assert review is not None
        evidence = self._build_final_evidence(task, review)
        title, lines = self.delivery.build_final_delivery(task, review)
        notification = self.channel.notify(
            title=title,
            lines=lines,
            endpoint_id=self._resolve_delivery_endpoint_id(task),
        )
        self._record_notification(task, stage="final_delivery", notification=notification)
        payload = {
            "task_status": task.status,
            "review_id": review.review_id,
            "latest_review_id": review.review_id,
            "latest_review_status": review.status,
            "latest_review_summary": review.summary,
            "review_round": self._get_review_round(task, fallback_review=review),
            "pr_url": task.pull_request.html_url if task.pull_request else None,
            "final_evidence": evidence.model_dump(mode="json"),
            "terminal_evidence": self._build_terminal_evidence(
                terminal_state="completed",
                task=task,
                review=review,
            ).model_dump(mode="json"),
        }
        status = "completed" if task.status == "approved" else task.status
        self._record_parent_result(task, event_type="child_completed", status=status, payload=payload)
        self._record_parent_result(task, event_type=ControlEventType.DELIVERY_COMPLETED, status=status, payload=payload)

    def _resolve_final_review(self, task: SleepCodingTask) -> ReviewRun | None:
        reviews = self.review.list_task_reviews(task.task_id)
        if not reviews:
            return None
        return reviews[-1]

    def _can_publish_final_delivery(
        self,
        task: SleepCodingTask,
        review: ReviewRun | None,
    ) -> bool:
        if task.status != "approved":
            return False
        if review is None or review.is_blocking:
            return False
        return review.status in {"approved", "completed"}

    def _build_final_evidence(
        self,
        task: SleepCodingTask,
        review: ReviewRun,
    ) -> FinalDeliveryEvidence:
        if task.kickoff_request_id:
            token_usage = self.ledger.get_request_usage(task.kickoff_request_id)
        else:
            token_usage = task.token_usage
        return FinalDeliveryEvidence(
            task_status=task.status,
            validation_status=task.validation.status,
            review_status=review.status,
            review_id=review.review_id,
            review_url=review.comment_url or review.artifact_path,
            pr_url=task.pull_request.html_url if task.pull_request else None,
            token_usage=token_usage,
        )

    def _build_terminal_evidence(
        self,
        *,
        terminal_state: str,
        task: SleepCodingTask,
        review: ReviewRun | None = None,
        last_error: str | None = None,
    ) -> TerminalTaskEvidence:
        if task.kickoff_request_id:
            token_usage = self.ledger.get_request_usage(task.kickoff_request_id)
        else:
            token_usage = task.token_usage
        return TerminalTaskEvidence(
            terminal_state=terminal_state,  # type: ignore[arg-type]
            task_status=task.status,
            validation_status=task.validation.status,
            review_status=review.status if review is not None else None,
            review_id=review.review_id if review is not None else None,
            review_url=(review.comment_url or review.artifact_path) if review is not None else None,
            pr_url=task.pull_request.html_url if task.pull_request else None,
            last_error=last_error,
            token_usage=token_usage,
        )

    def _extract_review_repair_strategy(
        self,
        task: SleepCodingTask,
        review: ReviewRun,
    ) -> list[str]:
        control_task = self._get_control_task(task)
        if control_task is not None:
            strategy = control_task.payload.get("latest_repair_strategy")
            if isinstance(strategy, list):
                normalized = [str(item).strip() for item in strategy if str(item).strip()]
                if normalized:
                    return normalized
        if review.summary.strip():
            return [review.summary.strip()]
        if review.content.strip():
            return [review.content.strip()]
        return []

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
        self.tasks.append_domain_event(
            control_task.task_id,
            event_type,
            {"domain_task_id": task.task_id, **payload},
        )
        if control_task.parent_task_id:
            self.tasks.update_task(control_task.parent_task_id, status=status, payload_patch=payload)
            self.tasks.append_domain_event(
                control_task.parent_task_id,
                event_type,
                {"child_control_task_id": control_task.task_id, **payload},
            )

    def _record_notification(
        self,
        task: SleepCodingTask,
        *,
        stage: str,
        notification,
    ) -> None:
        with closing(self.sleep_coding._connect()) as connection:
            self.sleep_coding.store.append_event(
                connection,
                task.task_id,
                "channel_notified",
                {
                    "provider": notification.provider,
                    "delivered": notification.delivered,
                    "is_dry_run": notification.is_dry_run,
                    "endpoint_id": notification.endpoint_id,
                    "stage": stage,
                },
            )
            connection.commit()
        if task.control_task_id:
            payload_patch = {
                "delivery_stage": stage,
                "delivery_provider": notification.provider,
                "delivery_delivered": notification.delivered,
                "delivery_status": "delivered" if notification.delivered else "degraded",
            }
            self.tasks.update_task(
                task.control_task_id,
                payload_patch=payload_patch,
            )
            self.tasks.append_event(
                task.control_task_id,
                "channel_notified",
                {
                    "provider": notification.provider,
                    "delivered": notification.delivered,
                    "is_dry_run": notification.is_dry_run,
                    "endpoint_id": notification.endpoint_id,
                    "stage": stage,
                    "domain_task_id": task.task_id,
                },
            )
            control_task = self.tasks.get_task(task.control_task_id)
            if control_task.parent_task_id:
                self.tasks.update_task(
                    control_task.parent_task_id,
                    payload_patch=payload_patch,
                )
                self.tasks.append_event(
                    control_task.parent_task_id,
                    "child_channel_notified",
                    {
                        "child_control_task_id": task.control_task_id,
                        "provider": notification.provider,
                        "delivered": notification.delivered,
                        "is_dry_run": notification.is_dry_run,
                        "endpoint_id": notification.endpoint_id,
                        "stage": stage,
                    },
                )

    def _resolve_delivery_endpoint_id(self, task: SleepCodingTask) -> str | None:
        control_task = self._get_control_task(task)
        if control_task is None:
            return None
        endpoint_id = control_task.payload.get("delivery_endpoint_id")
        if isinstance(endpoint_id, str) and endpoint_id.strip():
            return endpoint_id
        return None
