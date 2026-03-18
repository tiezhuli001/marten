import unittest

from app.core.config import Settings
from app.services.scheduler import WorkerSchedulerService


class FakeAutomationService:
    def __init__(self) -> None:
        self.calls = 0

    def process_worker_poll_async(self, payload) -> None:
        self.calls += 1


class SchedulerServiceTests(unittest.TestCase):
    def test_run_once_triggers_worker_poll(self) -> None:
        automation = FakeAutomationService()
        scheduler = WorkerSchedulerService(
            Settings(sleep_coding_scheduler_enabled=False),
            automation=automation,
        )

        scheduler.run_once()

        self.assertEqual(automation.calls, 1)


if __name__ == "__main__":
    unittest.main()
