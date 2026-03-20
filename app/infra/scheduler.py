from __future__ import annotations

import threading
from time import sleep

from app.control.automation import AutomationService
from app.core.config import Settings, get_settings
from app.models.schemas import SleepCodingWorkerPollRequest


class WorkerSchedulerService:
    def __init__(
        self,
        settings: Settings | None = None,
        automation: AutomationService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._automation = automation
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def automation(self) -> AutomationService:
        if self._automation is None:
            self._automation = AutomationService(settings=self.settings)
        return self._automation

    def start(self) -> None:
        if not self.settings.resolved_sleep_coding_scheduler_enabled:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="sleep-coding-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def run_once(self) -> None:
        self.automation.process_worker_poll_async(
            SleepCodingWorkerPollRequest(
                auto_approve_plan=self.settings.resolved_sleep_coding_worker_auto_approve_plan,
            )
        )

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self.run_once()
            interval = max(self.settings.resolved_sleep_coding_worker_poll_interval_seconds, 1)
            for _ in range(interval):
                if self._stop_event.is_set():
                    return
                sleep(1)
