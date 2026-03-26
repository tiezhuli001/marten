import json
import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings
from app.framework import MartenFramework

class FrameworkPublicSurfaceTests(unittest.TestCase):
    def test_framework_facade_manual_smoke_surface_stays_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name, payload in {
                "agents.json": {},
                "platform.json": {"github": {"repository": "demo/repo"}, "channel": {"provider": "feishu"}},
                "models.json": {
                    "profiles": {"default": {"model": "openai/gpt-5-mini"}},
                    "providers": {
                        "openai": {
                            "protocol": "openai",
                            "api_key": "test-key",
                            "api_base": "https://api.openai.com/v1",
                            "default_model": "gpt-5-mini",
                        }
                    },
                },
            }.items():
                (root / name).write_text(json.dumps(payload), encoding="utf-8")
            framework = MartenFramework(Settings(
                agents_config_path=str(root / "agents.json"),
                platform_config_path=str(root / "platform.json"),
                models_config_path=str(root / "models.json"),
                app_env="test",
                database_url=f"sqlite:///{root / 'framework.db'}",
            ))

            self.assertIn("ralph", framework.builtin_agents())
            self.assertEqual(framework.config_surface()["github_repository"], "demo/repo")
            self.assertEqual(framework.resolve_agent_descriptor("ralph").agent_id, "ralph")
            self.assertEqual(framework.runtime().__class__.__name__, "AgentRuntime")

if __name__ == "__main__":
    unittest.main()
