import json
import os
import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings
from app.models.schemas import TokenUsage
from app.runtime.agent_runtime import AgentDescriptor, AgentRuntime
from app.runtime.mcp import (
    GitHubMCPAdapter,
    MCPClient,
    InMemoryMCPServer,
    load_mcp_server_definitions,
)
from app.runtime.skills import SkillLoader


class FakeLLMRuntime:
    def __init__(self) -> None:
        self.requests = []

    def generate(self, llm_request):
        self.requests.append(llm_request)
        return type(
            "LLMResponseStub",
            (),
            {
                "output_text": json.dumps({"title": "draft"}),
                "usage": TokenUsage(total_tokens=12),
            },
        )()


class RuntimeComponentTests(unittest.TestCase):
    def test_settings_prefer_agents_and_models_json_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "custom" / "main"
            (root / "agents.json").write_text(
                json.dumps(
                    {
                        "agents": {
                            "main-agent": {
                                "workspace": str(workspace),
                                "skills": ["issue-writer", "triage"],
                                "mcp_servers": ["github", "linear"],
                                "model_profile": "default",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            (root / "models.json").write_text(
                json.dumps(
                    {
                        "profiles": {
                            "default": {
                                "provider": "minimax",
                                "model": "MiniMax-M2.5",
                            }
                        },
                        "providers": {
                            "openai": {"default_model": "gpt-4.1-mini"},
                            "minimax": {"default_model": "MiniMax-M2.5"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            settings = Settings(
                agents_config_path=str(root / "agents.json"),
                models_config_path=str(root / "models.json"),
            )

            self.assertEqual(
                settings.resolved_main_agent_workspace,
                workspace,
            )
            self.assertEqual(
                settings.resolved_main_agent_skills,
                ["issue-writer", "triage"],
            )
            self.assertEqual(
                settings.resolved_main_agent_mcp_servers,
                ["github", "linear"],
            )
            self.assertEqual(settings.resolved_llm_default_provider, "minimax")
            self.assertEqual(settings.resolved_llm_default_model, "MiniMax-M2.5")

    def test_settings_prefer_platform_json_for_worker_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "platform.json").write_text(
                json.dumps(
                    {
                        "sleep_coding": {
                            "labels": ["agent:test", "workflow:test"],
                            "git": {
                                "worktree_root": ".custom-worktrees",
                                "enable_commit": True,
                                "enable_push": True,
                                "remote_name": "upstream",
                            },
                            "worker": {
                                "poll_labels": ["agent:test", "workflow:test"],
                                "auto_approve_plan": True,
                                "poll_interval_seconds": 42,
                                "lease_seconds": 120,
                                "heartbeat_timeout_seconds": 180,
                                "max_retries": 9,
                                "retry_backoff_seconds": 7,
                                "scheduler_enabled": True,
                            }
                        },
                        "llm": {
                            "request_timeout_seconds": 12.5,
                            "request_max_attempts": 4,
                            "request_retry_base_delay_seconds": 1.5,
                        },
                        "review": {"max_repair_rounds": 5},
                        "github": {"repository": "demo/repo"},
                        "channel": {"provider": "feishu"},
                    }
                ),
                encoding="utf-8",
            )
            settings = Settings(platform_config_path=str(root / "platform.json"))

            self.assertEqual(settings.resolved_sleep_coding_labels, ["agent:test", "workflow:test"])
            self.assertEqual(settings.resolved_sleep_coding_worker_poll_labels, ["agent:test", "workflow:test"])
            self.assertTrue(settings.resolved_sleep_coding_worker_auto_approve_plan)
            self.assertEqual(settings.resolved_sleep_coding_worker_poll_interval_seconds, 42)
            self.assertEqual(settings.resolved_sleep_coding_worker_lease_seconds, 120)
            self.assertEqual(settings.resolved_sleep_coding_worker_heartbeat_timeout_seconds, 180)
            self.assertEqual(settings.resolved_sleep_coding_worker_max_retries, 9)
            self.assertEqual(settings.resolved_sleep_coding_worker_retry_backoff_seconds, 7)
            self.assertTrue(settings.resolved_sleep_coding_scheduler_enabled)
            self.assertEqual(settings.resolved_llm_request_timeout_seconds, 12.5)
            self.assertEqual(settings.resolved_llm_request_max_attempts, 4)
            self.assertEqual(settings.resolved_llm_request_retry_base_delay_seconds, 1.5)
            self.assertEqual(settings.resolved_review_max_repair_rounds, 5)
            self.assertEqual(
                settings.resolved_sleep_coding_worktree_root,
                settings.project_root / ".custom-worktrees",
            )
            self.assertTrue(settings.resolved_sleep_coding_enable_git_commit)
            self.assertTrue(settings.resolved_sleep_coding_enable_git_push)
            self.assertEqual(settings.resolved_git_remote_name, "upstream")
            self.assertEqual(settings.resolved_review_skill_name, "code-review")
            self.assertIsNone(settings.resolved_review_skill_command)
            self.assertEqual(settings.resolved_github_repository, "demo/repo")
            self.assertEqual(settings.resolved_channel_provider, "feishu")

    def test_settings_keep_platform_worker_auto_approve_as_source_of_truth(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "platform.json").write_text(
                json.dumps(
                    {
                        "sleep_coding": {
                            "worker": {
                                "auto_approve_plan": False,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            settings = Settings(
                platform_config_path=str(root / "platform.json"),
                sleep_coding_worker_auto_approve_plan=True,
            )

            self.assertFalse(settings.resolved_sleep_coding_worker_auto_approve_plan)

    def test_skill_loader_reads_workspace_skill(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skill_dir = root / "skills" / "issue-writer"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: issue-writer\ndescription: Write issues\n---\n# Instructions\nUse this skill.\n",
                encoding="utf-8",
            )
            settings = Settings(skills_root_dir=str(root / "skills"))
            loader = SkillLoader(settings)

            discovered = loader.discover()

            self.assertIn("issue-writer", discovered)
            self.assertIn("Use this skill.", discovered["issue-writer"].instructions)

    def test_mcp_client_calls_registered_tool(self) -> None:
        client = MCPClient()
        server = InMemoryMCPServer()
        server.register_tool(
            "create_issue",
            lambda arguments: {"issue_number": 1, "title": arguments["title"]},
            server="github",
        )
        client.register_adapter("github", server)

        result = client.call_tool(
            type(
                "ToolCallStub",
                (),
                {"server": "github", "tool": "create_issue", "arguments": {"title": "demo"}},
            )()
        )

        self.assertEqual(result.content["issue_number"], 1)

    def test_skill_loader_filters_ineligible_openclaw_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skill_dir = root / "skills" / "gated-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\n"
                "name: gated-skill\n"
                "description: Needs env\n"
                "metadata:\n"
                '  {"openclaw": {"requires": {"env": ["REQUIRED_TEST_ENV"]}}}\n'
                "---\n"
                "# Instructions\nUse this skill.\n",
                encoding="utf-8",
            )
            settings = Settings(skills_root_dir=str(root / "skills"))
            loader = SkillLoader(settings)
            previous = os.environ.pop("REQUIRED_TEST_ENV", None)
            try:
                discovered = loader.discover()
                self.assertNotIn("gated-skill", discovered)
                os.environ["REQUIRED_TEST_ENV"] = "1"
                discovered = loader.discover()
                self.assertIn("gated-skill", discovered)
            finally:
                if previous is None:
                    os.environ.pop("REQUIRED_TEST_ENV", None)
                else:
                    os.environ["REQUIRED_TEST_ENV"] = previous

    def test_agent_runtime_injects_skills_and_mcp_tools_into_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "agents" / "main-agent"
            (workspace / "skills" / "issue-writer").mkdir(parents=True)
            (workspace / "AGENTS.md").write_text("Main agent rules.", encoding="utf-8")
            (workspace / "TOOLS.md").write_text("Use MCP first.", encoding="utf-8")
            (workspace / "skills" / "issue-writer" / "SKILL.md").write_text(
                "---\nname: issue-writer\ndescription: Write issues\n---\n# Instructions\nUse this skill.\n",
                encoding="utf-8",
            )
            mcp_client = MCPClient()
            server = InMemoryMCPServer()
            server.register_tool(
                "create_issue",
                lambda arguments: arguments,
                description="Create GitHub issues",
                server="github",
            )
            mcp_client.register_adapter("github", server)
            fake_llm = FakeLLMRuntime()
            settings = Settings(skills_root_dir=str(root / "shared-skills"))
            runtime = AgentRuntime(
                settings=settings,
                llm_runtime=fake_llm,
                skills=SkillLoader(settings),
                mcp_client=mcp_client,
            )

            runtime.generate_structured_output(
                AgentDescriptor(
                    agent_id="main-agent",
                    workspace=workspace,
                    skill_names=["issue-writer"],
                    mcp_servers=["github"],
                    system_instruction="Draft issues.",
                    model_profile="default",
                ),
                user_prompt="Turn this into an issue",
                output_contract="Return JSON.",
            )

            system_prompt = fake_llm.requests[0].messages[0].content
            self.assertIn("Use this skill.", system_prompt)
            self.assertIn("github.create_issue", system_prompt)
            self.assertIn("Main agent rules.", system_prompt)

    def test_github_mcp_adapter_maps_aliases_to_server_tools(self) -> None:
        base = InMemoryMCPServer()
        base.register_tool(
            "issue_write",
            lambda arguments: {"html_url": "https://example.com/issues/1", "labels": arguments.get("labels", [])},
            server="github-raw",
        )
        base.register_tool(
            "issue_read",
            lambda arguments: {"number": arguments["issue_number"], "title": "Issue title", "body": "Issue body"},
            server="github-raw",
        )
        base.register_tool(
            "add_issue_comment",
            lambda arguments: {"html_url": "https://example.com/issues/1#comment"},
            server="github-raw",
        )
        base.register_tool(
            "create_pull_request",
            lambda arguments: {"number": 9, "title": arguments["title"], "html_url": "https://example.com/pull/9"},
            server="github-raw",
        )
        base.register_tool(
            "create_branch",
            lambda arguments: {"ref": f"refs/heads/{arguments['branch']}"},
            server="github-raw",
        )
        base.register_tool(
            "push_files",
            lambda arguments: {"sha": "abc123", "message": arguments["message"]},
            server="github-raw",
        )
        base.register_tool(
            "pull_request_review_write",
            lambda arguments: {"url": f"https://example.com/pull/{arguments['pullNumber']}#review"},
            server="github-raw",
        )
        adapter = GitHubMCPAdapter(server="github", base_adapter=base)

        tools = {tool.name for tool in adapter.list_tools()}
        result = adapter.call_tool(
            "create_issue",
            {
                "repo": "owner/repo",
                "title": "Demo",
                "body": "Body",
                "labels": ["agent:ralph"],
            },
        )

        self.assertIn("create_issue", tools)
        self.assertIn("apply_labels", tools)
        self.assertIn("create_branch", tools)
        self.assertIn("push_files", tools)
        self.assertIn("pull_request_review_write", tools)
        self.assertEqual(result.content["labels"], ["agent:ralph"])

        branch = adapter.call_tool(
            "create_branch",
            {"repo": "owner/repo", "branch": "feature/demo", "from_branch": "main"},
        )
        pushed = adapter.call_tool(
            "push_files",
            {
                "repo": "owner/repo",
                "branch": "feature/demo",
                "files": [{"path": "README.md", "content": "demo"}],
                "message": "demo commit",
            },
        )
        review = adapter.call_tool(
            "pull_request_review_write",
            {
                "repo": "owner/repo",
                "pr_number": 9,
                "method": "create",
                "event": "COMMENT",
                "body": "looks good",
            },
        )

        self.assertEqual(branch.content["ref"], "refs/heads/feature/demo")
        self.assertEqual(pushed.content["sha"], "abc123")
        self.assertEqual(review.content["url"], "https://example.com/pull/9#review")

    def test_mcp_server_definitions_load_from_mcp_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "mcp.json"
            previous = os.environ.get("TEST_GITHUB_TOKEN")
            os.environ["TEST_GITHUB_TOKEN"] = "secret-token"
            config_path.write_text(
                json.dumps(
                    {
                        "servers": {
                            "github": {
                                "transport": "stdio",
                                "command": "npx",
                                "args": ["-y", "github-mcp-server", "stdio"],
                                "env": {
                                    "GITHUB_PERSONAL_ACCESS_TOKEN": "${TEST_GITHUB_TOKEN}"
                                },
                                "adapter": "github",
                                "timeout_seconds": 45,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            try:
                settings = Settings(
                    mcp_config_path=str(config_path),
                    mcp_github_enabled=False,
                )
                definitions = load_mcp_server_definitions(settings)
            finally:
                if previous is None:
                    os.environ.pop("TEST_GITHUB_TOKEN", None)
                else:
                    os.environ["TEST_GITHUB_TOKEN"] = previous

            self.assertEqual(len(definitions), 1)
            self.assertEqual(definitions[0].server_name, "github")
            self.assertEqual(definitions[0].adapter, "github")
            self.assertEqual(
                definitions[0].env["GITHUB_PERSONAL_ACCESS_TOKEN"],
                "secret-token",
            )
            self.assertEqual(definitions[0].timeout_seconds, 45)

    def test_mcp_server_definitions_require_mcp_json(self) -> None:
        settings = Settings(
            mcp_config_path="/tmp/non-existent-mcp.json",
            mcp_github_enabled=True,
            mcp_github_command="npx",
            mcp_github_args="-y github-mcp-server stdio",
            mcp_github_env="GITHUB_PERSONAL_ACCESS_TOKEN=legacy-token",
        )

        definitions = load_mcp_server_definitions(settings)

        self.assertEqual(definitions, [])


if __name__ == "__main__":
    unittest.main()
