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


def build_settings(root: Path, rag_payload: dict[str, object]) -> Settings:
    platform_json = root / "platform.json"
    platform_json.write_text(json.dumps({"rag": rag_payload}), encoding="utf-8")
    return Settings(platform_config_path=str(platform_json))

class RAGCapabilityTests(unittest.TestCase):
    def test_rag_facade_retrieves_and_dedupes_results(self) -> None:
        from app.rag import InMemoryRetrievalProvider, RAGFacade

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(
                root,
                {
                    "domains": {
                        "repo-docs": {"domain_type": "operational", "owner": "framework", "visibility": "shared", "provider": "memory"},
                        "review-docs": {"domain_type": "operational", "owner": "framework", "visibility": "shared", "provider": "memory"},
                    },
                    "policies": [
                        {
                            "agent_id": "main-agent",
                            "workflow": "general",
                            "domains": ["repo-docs", "review-docs"],
                            "top_k": 3,
                            "trigger_mode": "always",
                            "merge_mode": "append",
                            "max_tokens": 300,
                            "dedupe": True,
                            "citation_mode": "inline",
                        }
                    ],
                },
            )
            facade = RAGFacade(settings)
            facade.register_provider(
                "memory",
                InMemoryRetrievalProvider(
                    {
                        "repo-docs": [
                            {
                                "item_ref": "doc-1",
                                "title": "Routing Spec",
                                "content": "Route to the default agent when no explicit target exists.",
                                "source": "docs",
                            }
                        ],
                        "review-docs": [
                            {
                                "item_ref": "doc-1",
                                "title": "Routing Spec Duplicate",
                                "content": "This duplicate should be deduped.",
                                "source": "docs",
                            },
                            {
                                "item_ref": "doc-2",
                                "title": "Review Loop",
                                "content": "Blocking reviews rerun coding until the loop stops.",
                                "source": "docs",
                            },
                        ],
                    }
                ),
            )

            response = facade.retrieve_response(
                agent_id="main-agent",
                workflow="general",
                query="route requests and explain review loop",
            )

            self.assertEqual(response.provider, "memory")
            self.assertEqual([item.item_ref for item in response.results], ["doc-1", "doc-2"])
            self.assertEqual(response.debug["domains"], ["repo-docs", "review-docs"])
    def test_agent_runtime_merges_retrieval_context_when_policy_is_always(self) -> None:
        from app.rag import InMemoryRetrievalProvider, RAGFacade

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "agents" / "main-agent"
            workspace.mkdir(parents=True)
            (workspace / "AGENTS.md").write_text("Main agent rules.", encoding="utf-8")
            settings = build_settings(
                root,
                {
                    "domains": {
                        "repo-docs": {"domain_type": "operational", "owner": "framework", "visibility": "shared", "provider": "memory"}
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
                },
            )
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
                user_prompt="总结 framework public surface",
                output_contract="Return JSON.",
            )

            system_prompt = fake_llm.requests[0].messages[0].content
            self.assertIn("Retrieved Context", system_prompt)
            self.assertIn("Framework Surface", system_prompt)

if __name__ == "__main__":
    unittest.main()
