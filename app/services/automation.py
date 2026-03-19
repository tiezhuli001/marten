from __future__ import annotations

from app.agents.code_review_agent import ReviewService
from app.agents.ralph import SleepCodingService
from app.channel.delivery import DeliveryMessageBuilder
from app.channel.notifications import ChannelNotificationService
from app.control.review_loop import decide_review_loop_step
from app.control.events import ControlEvent, ControlEventBus, ControlEventType
from app.control.follow_up import FollowUpControlService
from app.core.config import Settings, get_settings
from app.infra.background_jobs import (
    BackgroundJobService,
    get_background_job_service,
)
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
from app.control.sleep_coding_worker import SleepCodingWorkerService
from app.services.task_registry import TaskRegistryService


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
        self.follow_up = FollowUpControlService(
            sleep_coding=self.sleep_coding,
            tasks=self.tasks,
            event_bus=self.event_bus,
        )
        self.delivery = DeliveryMessageBuilder(self.ledger)
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
        last_review: ReviewRun | None = None
        while True:
            blocking_reviews = self.review.count_blocking_reviews(current_task.task_id)
            decision = decide_review_loop_step(
                task_status=current_task.status,
                review_blocking=last_review.is_blocking if last_review is not None else None,
                blocking_reviews=blocking_reviews,
                max_repair_rounds=self.max_repair_rounds,
            )
            if decision.action == "rerun_coding":
                current_task = self._rerun_coding(current_task.task_id)
                last_review = None
                continue
            if decision.action == "run_review":
                last_review = self.review.trigger_for_task(current_task.task_id)
                continue
            if decision.action == "request_changes":
                self.review.apply_action(
                    last_review.review_id,
                    ReviewActionRequest(action="request_changes"),
                )
                current_task = self._rerun_coding(current_task.task_id)
                last_review = None
                continue
            if decision.action == "handoff":
                self.review.apply_action(
                    last_review.review_id,
                    ReviewActionRequest(action="request_changes"),
                )
                current_task = self.sleep_coding.get_task(current_task.task_id)
                self._publish_manual_handoff(current_task, last_review, decision.blocking_reviews)
                return current_task
            if decision.action == "approve_review":
                self.review.apply_action(
                    last_review.review_id,
                    ReviewActionRequest(action="approve_review"),
                )
                current_task = self.sleep_coding.get_task(current_task.task_id)
                self._publish_final_delivery(current_task, last_review)
                return current_task
            if decision.action == "deliver":
                self._publish_final_delivery(current_task)
            return current_task

    def _rerun_coding(self, task_id: str) -> SleepCodingTask:
        return self.sleep_coding.apply_action(
            task_id,
            SleepCodingTaskActionRequest(action="approve_plan"),
        )

    def _schedule_follow_up(self, task: SleepCodingTask) -> None:
        self.follow_up.schedule(task)

    def _handle_follow_up_requested(self, event: ControlEvent) -> SleepCodingTask:
        task_id = event.payload.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError(f"{ControlEventType.FOLLOW_UP_REQUESTED} requires a task_id")
        return self._run_scheduled_follow_up(task_id)

    def _run_scheduled_follow_up(self, task_id: str) -> SleepCodingTask:
        self.follow_up.mark_state(task_id, "processing")
        try:
            task = self.run_review_loop(task_id)
        except Exception as exc:
            self.follow_up.mark_state(
                task_id,
                "failed",
                error=str(exc),
            )
            raise
        self.follow_up.mark_state(
            task_id,
            "completed",
            payload={"task_status": task.status},
        )
        return task

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
        self.channel.notify(title=title, lines=lines)
        payload = {
            "review_id": review.review_id,
            "blocking_reviews": blocking_reviews,
            "task_status": task.status,
        }
        self._record_parent_result(task, event_type="child_handed_off", status="needs_attention", payload=payload)
        self._record_parent_result(task, event_type="delivery.handed_off", status="needs_attention", payload=payload)

    def _publish_final_delivery(
        self,
        task: SleepCodingTask,
        review: ReviewRun | None = None,
    ) -> None:
        title, lines = self.delivery.build_final_delivery(task, review)
        self.channel.notify(title=title, lines=lines)
        payload = {
            "task_status": task.status,
            "review_id": review.review_id if review else None,
            "pr_url": task.pull_request.html_url if task.pull_request else None,
        }
        status = "completed" if task.status == "approved" else task.status
        self._record_parent_result(task, event_type="child_completed", status=status, payload=payload)
        self._record_parent_result(task, event_type=ControlEventType.DELIVERY_COMPLETED, status=status, payload=payload)

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
