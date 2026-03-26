import tempfile
import unittest
from pathlib import Path

from app.control.context import SessionMemoryStore
from app.core.config import Settings
from app.control.session_registry import SessionRegistryService


class SessionRegistryServiceTests(unittest.TestCase):
    def test_can_record_and_lookup_inbound_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(database_url=f"sqlite:///{Path(temp_dir) / 'sessions.db'}")
            service = SessionRegistryService(settings)

            recorded = service.record_inbound_receipt(
                "feishu:chat:oc_123:message:om_123",
                {
                    "request_id": "req-1",
                    "chain_request_id": "chain-1",
                    "intent": "general",
                    "message": "processed",
                    "token_usage": {"total_tokens": 1},
                },
            )
            fetched = service.find_inbound_receipt("feishu:chat:oc_123:message:om_123")

            self.assertEqual(recorded["request_id"], "req-1")
            self.assertEqual(fetched["chain_request_id"], "chain-1")

    def test_user_agent_and_run_sessions_can_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(database_url=f"sqlite:///{Path(temp_dir) / 'sessions.db'}")
            service = SessionRegistryService(settings)

            user_session = service.get_or_create_session(
                session_type="user_session",
                external_ref="manual:user-1",
                user_id="user-1",
                source="manual",
            )
            agent_session = service.get_or_create_session(
                session_type="agent_session",
                external_ref="main-agent:manual:user-1",
                agent_id="main-agent",
                user_id="user-1",
                source="manual",
                parent_session_id=user_session.session_id,
            )
            run_session = service.create_child_session(
                session_type="run_session",
                parent_session_id=agent_session.session_id,
                agent_id="ralph",
                user_id="user-1",
                source="manual",
                external_ref="sleep-coding-run:task-1",
            )

            self.assertEqual(agent_session.parent_session_id, user_session.session_id)
            self.assertEqual(run_session.parent_session_id, agent_session.session_id)
            self.assertEqual(service.get_session(run_session.session_id).agent_id, "ralph")

    def test_update_session_payload_and_list_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(database_url=f"sqlite:///{Path(temp_dir) / 'sessions.db'}")
            service = SessionRegistryService(settings)

            user_session = service.get_or_create_session(
                session_type="user_session",
                external_ref="manual:user-2",
                user_id="user-2",
                source="manual",
                payload={"short_memory_summary": "User asked for GitHub issue intake."},
            )
            agent_session = service.get_or_create_session(
                session_type="agent_session",
                external_ref="main-agent:manual:user-2",
                agent_id="main-agent",
                user_id="user-2",
                source="manual",
                parent_session_id=user_session.session_id,
            )

            updated = service.update_session_payload(
                agent_session.session_id,
                {"short_memory_summary": "Latest intake created Issue #101."},
            )
            chain = service.list_session_chain(agent_session.session_id)

            self.assertEqual(updated.payload["short_memory_summary"], "Latest intake created Issue #101.")
            self.assertEqual([item.session_id for item in chain], [user_session.session_id, agent_session.session_id])

    def test_session_memory_store_persists_recent_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(database_url=f"sqlite:///{Path(temp_dir) / 'sessions.db'}")
            service = SessionRegistryService(settings)
            memory = SessionMemoryStore(service)

            session = service.get_or_create_session(
                session_type="user_session",
                external_ref="manual:user-3",
                user_id="user-3",
                source="manual",
            )
            memory.append(session.session_id, "First note")
            memory.append(session.session_id, "Second note")
            updated = service.get_session(session.session_id)
            artifact_path = settings.project_root / "artifacts" / "memory" / "sessions" / f"{session.session_id}.md"

            self.assertEqual(updated.payload["short_memory_summary"], "Second note")
            self.assertEqual(updated.payload["short_memory_entries"], ["First note", "Second note"])
            self.assertEqual(memory.list(session.session_id), ["First note", "Second note"])
            self.assertTrue(artifact_path.exists())
            self.assertIn("Second note", artifact_path.read_text(encoding="utf-8"))

    def test_set_active_agent_updates_user_facing_owner_without_creating_new_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(database_url=f"sqlite:///{Path(temp_dir) / 'sessions.db'}")
            service = SessionRegistryService(settings)

            session = service.get_or_create_session(
                session_type="user_session",
                external_ref="manual:user-4",
                user_id="user-4",
                source="manual",
            )
            updated = service.set_active_agent(session.session_id, "ralph")

            self.assertEqual(updated.session_id, session.session_id)
            self.assertEqual(updated.payload["active_agent"], "ralph")

    def test_execution_lane_persists_active_and_queued_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(database_url=f"sqlite:///{Path(temp_dir) / 'sessions.db'}")
            service = SessionRegistryService(settings)

            first = service.acquire_execution_lane("task-1")
            second = service.acquire_execution_lane("task-2")
            released = service.release_execution_lane("task-1")
            snapshot = service.get_execution_lane()

            self.assertEqual(first.disposition, "accepted")
            self.assertEqual(first.snapshot.active_task_id, "task-1")
            self.assertEqual(second.disposition, "queued")
            self.assertEqual(second.snapshot.active_task_id, "task-1")
            self.assertEqual(second.snapshot.queued_task_ids, ["task-2"])
            self.assertEqual(released.disposition, "released")
            self.assertEqual(released.snapshot.active_task_id, "task-2")
            self.assertEqual(snapshot.active_task_id, "task-2")
            self.assertEqual(snapshot.queued_task_ids, [])

    def test_release_non_active_task_removes_only_queued_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(database_url=f"sqlite:///{Path(temp_dir) / 'sessions.db'}")
            service = SessionRegistryService(settings)

            service.acquire_execution_lane("task-1")
            service.acquire_execution_lane("task-2")
            service.acquire_execution_lane("task-3")

            released = service.release_execution_lane("task-2")
            snapshot = service.get_execution_lane()

            self.assertEqual(released.disposition, "released")
            self.assertEqual(released.snapshot.active_task_id, "task-1")
            self.assertEqual(released.snapshot.queued_task_ids, ["task-3"])
            self.assertEqual(snapshot.active_task_id, "task-1")
            self.assertEqual(snapshot.queued_task_ids, ["task-3"])

    def test_acquire_same_queued_task_id_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(database_url=f"sqlite:///{Path(temp_dir) / 'sessions.db'}")
            service = SessionRegistryService(settings)

            service.acquire_execution_lane("task-1")
            first_queue = service.acquire_execution_lane("task-2")
            second_queue = service.acquire_execution_lane("task-2")
            snapshot = service.get_execution_lane()

            self.assertEqual(first_queue.disposition, "queued")
            self.assertEqual(second_queue.disposition, "queued")
            self.assertEqual(first_queue.snapshot.queued_task_ids, ["task-2"])
            self.assertEqual(second_queue.snapshot.queued_task_ids, ["task-2"])
            self.assertEqual(snapshot.active_task_id, "task-1")
            self.assertEqual(snapshot.queued_task_ids, ["task-2"])


if __name__ == "__main__":
    unittest.main()
