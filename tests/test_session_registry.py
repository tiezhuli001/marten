import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings
from app.services.session_registry import SessionRegistryService


class SessionRegistryServiceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
