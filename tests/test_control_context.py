import tempfile
import unittest
from pathlib import Path

from app.control.context import ContextAssemblyService
from app.core.config import Settings
from app.services.session_registry import SessionRegistryService


class ContextAssemblyServiceTests(unittest.TestCase):
    def test_build_agent_input_includes_short_memory_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(database_url=f"sqlite:///{Path(temp_dir) / 'context.db'}")
            sessions = SessionRegistryService(settings)
            context = ContextAssemblyService(sessions)

            user_session = sessions.get_or_create_session(
                session_type="user_session",
                external_ref="manual:user-1",
                user_id="user-1",
                source="manual",
                payload={"short_memory_summary": "User prefers Feishu + GitHub issue workflow."},
            )
            run_session = sessions.create_child_session(
                session_type="run_session",
                parent_session_id=user_session.session_id,
                agent_id="ralph",
                user_id="user-1",
                source="manual",
                external_ref="sleep-coding-run:task-ctx",
            )
            context.record_short_memory(run_session.session_id, "Plan ready for Issue #33.")
            context.record_short_memory(run_session.session_id, "Validation should cover webhook signature handling.")

            prompt = context.build_agent_input(
                session_id=run_session.session_id,
                current_input="Issue #33: refine the webhook intake flow.",
                heading="Current Ralph Planning Task",
            )

            self.assertIn("Short Memory:", prompt)
            self.assertIn("User prefers Feishu + GitHub issue workflow.", prompt)
            self.assertIn("Plan ready for Issue #33.", prompt)
            self.assertIn("Validation should cover webhook signature handling.", prompt)
            self.assertIn("Current Ralph Planning Task:", prompt)


if __name__ == "__main__":
    unittest.main()
