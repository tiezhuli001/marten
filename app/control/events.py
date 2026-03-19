from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from app.infra.background_jobs import (
    BackgroundJobService,
    get_background_job_service,
)


class ControlEventType:
    ISSUE_CREATED = "issue.created"
    TASK_CLAIMED = "task.claimed"
    PLAN_READY = "plan.ready"
    REVIEW_COMPLETED = "review.completed"
    REVIEW_APPROVED = "review.approved"
    REVIEW_CHANGES_REQUESTED = "review.changes_requested"
    DELIVERY_COMPLETED = "delivery.completed"
    FOLLOW_UP_REQUESTED = "sleep_coding.follow_up.requested"
    FOLLOW_UP_QUEUED = "follow_up.queued"
    FOLLOW_UP_PROCESSING = "follow_up.processing"
    FOLLOW_UP_COMPLETED = "follow_up.completed"
    FOLLOW_UP_FAILED = "follow_up.failed"


@dataclass(frozen=True)
class ControlEvent:
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    key: str | None = None


class ControlEventBus:
    def __init__(
        self,
        background_jobs: BackgroundJobService | None = None,
    ) -> None:
        self.background_jobs = background_jobs or get_background_job_service()
        self._handlers: dict[str, list[Callable[[ControlEvent], object]]] = {}

    def register(
        self,
        event_type: str,
        handler: Callable[[ControlEvent], object],
    ) -> None:
        handlers = self._handlers.setdefault(event_type, [])
        handlers.append(handler)

    def publish(self, event: ControlEvent) -> bool:
        handlers = self._handlers.get(event.event_type, [])
        if not handlers:
            return False
        accepted = False
        for index, handler in enumerate(handlers):
            key = event.key or f"{event.event_type}:{index}"
            scheduled = self.background_jobs.submit_unique(key, handler, event)
            accepted = scheduled or accepted
        return accepted

    def publish_follow_up_requested(self, task_id: str) -> bool:
        return self.publish(
            ControlEvent(
                event_type=ControlEventType.FOLLOW_UP_REQUESTED,
                key=f"sleep-coding-follow-up:{task_id}",
                payload={"task_id": task_id},
            )
        )
