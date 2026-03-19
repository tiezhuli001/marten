from __future__ import annotations

from app.control.events import ControlEventBus, ControlEventType
from app.models.schemas import SleepCodingTask
from app.services.task_registry import TaskRegistryService


class FollowUpControlService:
    def __init__(
        self,
        *,
        sleep_coding,
        tasks: TaskRegistryService,
        event_bus: ControlEventBus,
    ) -> None:
        self.sleep_coding = sleep_coding
        self.tasks = tasks
        self.event_bus = event_bus

    def schedule(self, task: SleepCodingTask) -> None:
        if task.status not in {"changes_requested", "in_review"}:
            return
        scheduled = self.event_bus.publish_follow_up_requested(task.task_id)
        if not scheduled:
            return
        current_task = self.sleep_coding.get_task(task.task_id)
        if current_task.background_follow_up_status != "idle":
            return
        self.mark_state(
            task.task_id,
            "queued",
            payload={"task_status": task.status},
        )

    def mark_state(
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
        legacy_event_type = f"background_follow_up_{state}"
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
        self.tasks.append_event(
            task.control_task_id,
            legacy_event_type,
            {"domain_task_id": task_id, **control_payload},
        )
        self.tasks.append_domain_event(
            task.control_task_id,
            domain_event_type,
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
