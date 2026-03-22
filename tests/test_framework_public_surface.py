import json
import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings


class FrameworkPublicSurfaceTests(unittest.TestCase):
    def test_framework_facade_exposes_builtin_agent_descriptors(self) -> None:
        from app.framework import MartenFramework

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            agents_json = root / "agents.json"
            agents_json.write_text(
                json.dumps(
                    {
                        "agents": {
                            "ralph": {
                                "workspace": str(root / "agents" / "custom-ralph"),
                                "skills": ["coding-planner", "coding-executor", "repo-rag"],
                                "mcp_servers": ["github", "filesystem"],
                                "model_profile": "coding",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            settings = Settings(agents_config_path=str(agents_json))

            framework = MartenFramework(settings)
            builtin = framework.builtin_agents()
            descriptor = framework.resolve_agent_descriptor("ralph")

            self.assertEqual(sorted(builtin.keys()), ["code-review-agent", "main-agent", "ralph"])
            self.assertEqual(builtin["ralph"].agent_id, "ralph")
            self.assertEqual(builtin["ralph"].public_id, "ralph")
            self.assertEqual(builtin["ralph"].runtime_policy["execution_policy"], "sleep-coding")
            self.assertEqual(descriptor.agent_id, "ralph")
            self.assertEqual(descriptor.workspace, root / "agents" / "custom-ralph")
            self.assertEqual(descriptor.skill_names, ["coding-planner", "coding-executor", "repo-rag"])
            self.assertEqual(descriptor.mcp_servers, ["github", "filesystem"])

    def test_framework_facade_exposes_stable_config_surface(self) -> None:
        from app.framework import MartenFramework

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            platform_json = root / "platform.json"
            models_json = root / "models.json"
            platform_json.write_text(
                json.dumps(
                    {
                        "github": {"repository": "demo/repo"},
                        "channel": {"provider": "feishu"},
                    }
                ),
                encoding="utf-8",
            )
            models_json.write_text(
                json.dumps(
                    {
                        "profiles": {"default": {"model": "openai/gpt-5-mini"}},
                        "providers": {
                            "openai": {
                                "protocol": "openai",
                                "api_key": "test-key",
                                "api_base": "https://api.openai.com/v1",
                                "default_model": "gpt-5-mini",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            settings = Settings(
                platform_config_path=str(platform_json),
                models_config_path=str(models_json),
            )

            framework = MartenFramework(settings)
            config_surface = framework.config_surface()

            self.assertEqual(config_surface["github_repository"], "demo/repo")
            self.assertEqual(config_surface["channel_provider"], "feishu")
            self.assertEqual(config_surface["default_model_profile"], ("openai", "gpt-5-mini"))
            self.assertEqual(config_surface["builtin_agent_ids"], ["main-agent", "ralph", "code-review-agent"])


if __name__ == "__main__":
    unittest.main()
