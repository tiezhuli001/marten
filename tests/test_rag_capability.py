import json
import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings
from app.runtime.agent_runtime import AgentDescriptor, AgentRuntime


class FakeLLMRuntime:
    def __init__(self) -> None:
        self.requests = []

    def generate(self, llm_request):
        self.requests.append(llm_request)
        return type(
            "LLMResponseStub",
            (),
            {
                "output_text": json.dumps({"message": "ok"}),
                "usage": type("UsageStub", (), {"total_tokens": 10})(),
            },
        )()


class RAGCapabilityTests(unittest.TestCase):
    def test_rag_facade_resolves_policy_and_retrieves_domain_results(self) -> None:
        from app.rag import InMemoryRetrievalProvider, RAGFacade

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            platform_json = root / "platform.json"
            platform_json.write_text(
                json.dumps(
                    {
                        "rag": {
                            "domains": {
                                "repo-docs": {
                                    "domain_type": "operational",
                                    "owner": "framework",
                                    "visibility": "shared",
                                    "provider": "memory",
                                }
                            },
                            "policies": [
                                {
                                    "agent_id": "main-agent",
                                    "workflow": "general",
                                    "domains": ["repo-docs"],
                                    "top_k": 2,
                                    "trigger_mode": "always",
                                    "merge_mode": "append",
                                    "max_tokens": 300,
                                    "dedupe": True,
                                    "citation_mode": "inline",
                                }
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )
            settings = Settings(platform_config_path=str(platform_json))
            facade = RAGFacade(settings)
            facade.register_provider(
                "memory",
                InMemoryRetrievalProvider(
                    {
                        "repo-docs": [
                            {
                                "item_ref": "doc-1",
                                "title": "Routing Spec",
                                "content": "Multi-endpoint routing uses default agent bindings.",
                                "source": "docs",
                            }
                        ]
                    }
                ),
            )

            results = facade.retrieve(
                agent_id="main-agent",
                workflow="general",
                query="如何做多 endpoint routing",
            )

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].domain_id, "repo-docs")
            self.assertEqual(results[0].title, "Routing Spec")

    def test_agent_runtime_merges_retrieval_context_when_policy_is_always(self) -> None:
        from app.rag import InMemoryRetrievalProvider, RAGFacade

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            platform_json = root / "platform.json"
            workspace = root / "agents" / "main-agent"
            workspace.mkdir(parents=True)
            (workspace / "AGENTS.md").write_text("Main agent rules.", encoding="utf-8")
            platform_json.write_text(
                json.dumps(
                    {
                        "rag": {
                            "domains": {
                                "repo-docs": {
                                    "domain_type": "operational",
                                    "owner": "framework",
                                    "visibility": "shared",
                                    "provider": "memory",
                                }
                            },
                            "policies": [
                                {
                                    "agent_id": "main-agent",
                                    "workflow": "default",
                                    "domains": ["repo-docs"],
                                    "top_k": 1,
                                    "trigger_mode": "always",
                                    "merge_mode": "append",
                                    "max_tokens": 300,
                                    "dedupe": True,
                                    "citation_mode": "inline",
                                }
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )
            settings = Settings(platform_config_path=str(platform_json))
            rag = RAGFacade(settings)
            rag.register_provider(
                "memory",
                InMemoryRetrievalProvider(
                    {
                        "repo-docs": [
                            {
                                "item_ref": "doc-1",
                                "title": "Framework Surface",
                                "content": "Builtin agents should stay reusable through the framework facade.",
                                "source": "docs",
                            }
                        ]
                    }
                ),
            )
            fake_llm = FakeLLMRuntime()
            runtime = AgentRuntime(settings=settings, llm_runtime=fake_llm, rag=rag)

            runtime.generate_structured_output(
                AgentDescriptor(
                    agent_id="main-agent",
                    workspace=workspace,
                    skill_names=[],
                    mcp_servers=[],
                    system_instruction="Draft issues.",
                    model_profile="default",
                ),
                user_prompt="总结框架 public surface",
                output_contract="Return JSON.",
            )

            system_prompt = fake_llm.requests[0].messages[0].content
            self.assertIn("Retrieved Context", system_prompt)
            self.assertIn("Framework Surface", system_prompt)
            self.assertIn("framework facade", system_prompt)


if __name__ == "__main__":
    unittest.main()
