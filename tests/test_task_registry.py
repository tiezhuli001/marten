import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings
from app.services.task_registry import TaskRegistryService


class TaskRegistryServiceTests(unittest.TestCase):
    def test_create_child_task_and_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(database_url=f"sqlite:///{Path(temp_dir) / 'registry.db'}")
            service = TaskRegistryService(settings)

            parent = service.create_task(
                task_type="main_agent_intake",
                agent_id="main-agent",
                status="issue_created",
                user_id="user-1",
                repo="tiezhuli001/youmeng-gateway",
                issue_number=101,
                title="Parent task",
                external_ref="github_issue:tiezhuli001/youmeng-gateway#101",
            )
            child = service.create_task(
                task_type="sleep_coding",
                agent_id="ralph",
                status="planning",
                parent_task_id=parent.task_id,
                repo="tiezhuli001/youmeng-gateway",
                issue_number=101,
                title="Child task",
                external_ref="sleep_coding_task:task-1",
            )
            service.append_event(child.task_id, "plan_ready", {"summary": "Implement issue"})

            reloaded = service.get_task(child.task_id)
            events = service.list_events(child.task_id)

            self.assertEqual(reloaded.parent_task_id, parent.task_id)
            self.assertEqual(reloaded.root_task_id, parent.task_id)
            self.assertEqual(events[-1].event_type, "plan_ready")
            self.assertEqual(
                service.find_parent_for_issue("tiezhuli001/youmeng-gateway", 101).task_id,
                parent.task_id,
            )


if __name__ == "__main__":
    unittest.main()
