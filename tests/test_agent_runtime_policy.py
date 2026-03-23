import json
import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings
from app.runtime.agent_runtime import AgentDescriptor, AgentRuntime
from app.rag import InMemoryRetrievalProvider, RAGFacade


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


class AgentRuntimePolicyTests(unittest.TestCase):
    def test_system_prompt_uses_explicit_bootstrap_section(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "agents" / "main-agent"
            workspace.mkdir(parents=True)
            (workspace / "AGENTS.md").write_text("Main agent rules.", encoding="utf-8")
            fake_llm = FakeLLMRuntime()
            runtime = AgentRuntime(
                settings=Settings(),
                llm_runtime=fake_llm,
            )

            runtime.generate_structured_output(
                AgentDescriptor(
                    agent_id="main-agent",
                    workspace=workspace,
                    skill_names=[],
                    mcp_servers=[],
                    system_instruction="Draft issues.",
                    model_profile="default",
                ),
                user_prompt="Summarize the current task.",
                output_contract="Return JSON.",
            )

            system_prompt = fake_llm.requests[0].messages[0].content
            self.assertIn("Bootstrap Instructions:", system_prompt)
            self.assertIn("Workspace Instructions:", system_prompt)
            self.assertIn("Output Contract:", system_prompt)

    def test_runtime_only_retrieval_policy_keeps_docs_out_of_prompt(self) -> None:
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
                                    "injection_mode": "runtime_only",
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
                user_prompt="Summarize framework surface",
                output_contract="Return JSON.",
            )

            system_prompt = fake_llm.requests[0].messages[0].content
            self.assertIn("Retrieved Context:", system_prompt)
            self.assertIn("runtime_only", system_prompt)
            self.assertNotIn("Framework Surface", system_prompt)
            self.assertNotIn("framework facade", system_prompt)

    def test_truncation_preserves_high_priority_sections_before_low_priority_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            platform_json = root / "platform.json"
            workspace = root / "agents" / "main-agent"
            workspace.mkdir(parents=True)
            (workspace / "AGENTS.md").write_text("Main agent rules. " * 40, encoding="utf-8")
            skills_dir = workspace / "skills" / "verbose-skill"
            skills_dir.mkdir(parents=True)
            (skills_dir / "SKILL.md").write_text(
                "---\nname: verbose-skill\ndescription: verbose skill\n---\n"
                + ("Detailed instructions.\n" * 60),
                encoding="utf-8",
            )
            platform_json.write_text(
                json.dumps(
                    {
                        "agent_runtime": {
                            "context_policy": {
                                "max_chars": 600,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            settings = Settings(
                platform_config_path=str(platform_json),
                skills_root_dir=str(root / "no-shared-skills"),
            )
            fake_llm = FakeLLMRuntime()
            runtime = AgentRuntime(settings=settings, llm_runtime=fake_llm)

            runtime.generate_structured_output(
                AgentDescriptor(
                    agent_id="main-agent",
                    workspace=workspace,
                    skill_names=["verbose-skill"],
                    mcp_servers=[],
                    system_instruction="Draft issues. " * 20,
                    model_profile="default",
                ),
                user_prompt="Summarize the current task.",
                output_contract="Return JSON with title and summary.",
            )

            system_prompt = fake_llm.requests[0].messages[0].content
            self.assertIn("Bootstrap Instructions:", system_prompt)
            self.assertIn("Output Contract:", system_prompt)
            self.assertNotIn("Detailed instructions.", system_prompt)


if __name__ == "__main__":
    unittest.main()
