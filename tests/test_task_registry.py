import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings
from app.control.task_registry import TaskRegistryService


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

    def test_recovery_snapshot_reconstructs_next_step_from_persisted_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(database_url=f"sqlite:///{Path(temp_dir) / 'registry.db'}")
            service = TaskRegistryService(settings)

            parent = service.create_task(
                task_type="main_agent_intake",
                agent_id="main-agent",
                status="issue_created",
                user_id="user-1",
                source="feishu",
                repo="tiezhuli001/youmeng-gateway",
                issue_number=102,
                title="Parent task",
                external_ref="github_issue:tiezhuli001/youmeng-gateway#102",
                payload={"delivery_endpoint_id": "feishu-main"},
            )
            child = service.create_task(
                task_type="sleep_coding",
                agent_id="ralph",
                status="changes_requested",
                parent_task_id=parent.task_id,
                repo="tiezhuli001/youmeng-gateway",
                issue_number=102,
                title="Child task",
                external_ref="sleep_coding_task:task-102",
                payload={
                    "owner_agent": "ralph",
                    "source_agent": "main-agent",
                    "delivery_endpoint_id": "feishu-main",
                },
            )
            service.append_event(
                child.task_id,
                "handoff_to_code_review",
                {
                    "child_task_id": "review-control-1",
                    "domain_task_id": "task-102",
                    "review_scope": {"repo": "tiezhuli001/youmeng-gateway", "pr_number": 88},
                },
            )
            service.append_event(
                child.task_id,
                "review_returned",
                {
                    "review_id": "review-1",
                    "domain_task_id": "task-102",
                    "decision": "changes_requested",
                    "next_owner_agent": "ralph",
                },
            )

            snapshot = service.build_recovery_snapshot(child.task_id)
            events = service.list_events(child.task_id)

            self.assertEqual(snapshot["task_id"], child.task_id)
            self.assertEqual(snapshot["task_type"], "sleep_coding")
            self.assertEqual(snapshot["latest_event_type"], "review_returned")
            self.assertEqual(snapshot["next_action"], "rerun_coding")
            self.assertEqual(snapshot["owner_agent"], "ralph")
            self.assertEqual(snapshot["next_owner_agent"], "ralph")
            self.assertEqual(snapshot["domain_task_id"], "task-102")
            self.assertEqual(snapshot["review_id"], "review-1")
            self.assertEqual(snapshot["delivery_endpoint_id"], "feishu-main")
            self.assertEqual(events[-1].payload["task_type"], "sleep_coding")
            self.assertEqual(events[-1].payload["task_status"], "changes_requested")


if __name__ == "__main__":
    unittest.main()
