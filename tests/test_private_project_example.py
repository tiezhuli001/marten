import unittest
from pathlib import Path

from app.channel.endpoints import ChannelEndpointRegistry
from app.core.config import Settings
from app.framework import MartenFramework
from app.rag import RAGFacade


class PrivateProjectExampleTests(unittest.TestCase):
    def test_private_project_example_reuses_framework_surface(self) -> None:
        root = Path(__file__).resolve().parents[1] / "examples" / "private_agent_suite"
        settings = Settings(
            agents_config_path=str(root / "agents.json"),
            platform_config_path=str(root / "platform.json"),
        )

        framework = MartenFramework(settings)
        registry = ChannelEndpointRegistry(settings)
        rag = RAGFacade(settings)

        builtin = framework.builtin_agents()
        coding_descriptor = framework.resolve_agent_descriptor("ralph")
        endpoint_binding = registry.resolve_binding("private-coding")
        private_policy = rag.resolve_policy(agent_id="main-agent", workflow="default")
        private_domain = rag.resolve_domain("private-sop")

        self.assertIn("main-agent", builtin)
        self.assertIn("ralph", builtin)
        self.assertEqual(coding_descriptor.agent_id, "ralph")
        self.assertEqual(endpoint_binding.default_agent, "ralph")
        self.assertEqual(endpoint_binding.default_workflow, "sleep_coding")
        self.assertIsNotNone(private_policy)
        self.assertEqual(private_policy.domains, ["private-sop"])
        self.assertIsNotNone(private_domain)
        self.assertEqual(private_domain.domain_type, "private")


if __name__ == "__main__":
    unittest.main()
