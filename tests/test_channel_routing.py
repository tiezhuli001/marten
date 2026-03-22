import json
import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings
from app.control.routing import resolve_route


class ChannelRoutingTests(unittest.TestCase):
    def test_channel_endpoint_registry_parses_endpoints_and_delivery_policy(self) -> None:
        from app.channel.endpoints import ChannelEndpointRegistry

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            platform_json = root / "platform.json"
            platform_json.write_text(
                json.dumps(
                    {
                        "channel": {
                            "provider": "feishu",
                            "default_endpoint": "feishu-main",
                            "endpoints": {
                                "feishu-main": {
                                    "provider": "feishu",
                                    "mode": "primary",
                                    "entry_enabled": True,
                                    "delivery_enabled": True,
                                    "default_agent": "main-agent",
                                    "default_workflow": "general",
                                    "delivery_policy": {
                                        "mode": "workflow_mapped",
                                        "workflow_endpoints": {
                                            "sleep_coding": "feishu-review",
                                            "general": "same_endpoint",
                                        },
                                    },
                                },
                                "feishu-review": {
                                    "provider": "feishu",
                                    "mode": "delivery",
                                    "entry_enabled": False,
                                    "delivery_enabled": True,
                                },
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            settings = Settings(platform_config_path=str(platform_json))

            registry = ChannelEndpointRegistry(settings)
            route = registry.resolve_conversation_route(
                endpoint_id="feishu-main",
                workflow="sleep_coding",
                active_agent="ralph",
                session_id="session-1",
            )

            self.assertEqual(route.source_endpoint_id, "feishu-main")
            self.assertEqual(route.active_agent, "ralph")
            self.assertEqual(route.active_workflow, "sleep_coding")
            self.assertEqual(route.delivery_endpoint_id, "feishu-review")

    def test_endpoint_default_agent_overrides_single_entry_default(self) -> None:
        from app.channel.endpoints import EndpointBinding

        route = resolve_route(
            "请帮我处理这个需求",
            endpoint_binding=EndpointBinding(
                endpoint_id="coding-entry",
                default_agent="ralph",
                default_workflow="sleep_coding",
                delivery_policy={"mode": "same_endpoint"},
                allowed_handoffs=[],
            ),
        )

        self.assertEqual(route.intent, "sleep_coding")
        self.assertEqual(route.target_agent, "ralph")
        self.assertFalse(route.direct_mention)

    def test_unknown_endpoint_falls_back_to_main_agent_defaults(self) -> None:
        from app.channel.endpoints import ChannelEndpointRegistry

        settings = Settings(platform_config_path="/tmp/non-existent-platform.json")
        registry = ChannelEndpointRegistry(settings)

        binding = registry.resolve_binding("missing-endpoint")
        route = resolve_route("请帮我处理这个需求", endpoint_binding=binding)

        self.assertEqual(binding.endpoint_id, "default")
        self.assertEqual(route.intent, "general")
        self.assertEqual(route.target_agent, "main-agent")


if __name__ == "__main__":
    unittest.main()
