import json
import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings
from app.ledger.service import TokenLedgerService
from app.models.schemas import (
    GitHubIssueDraft,
    GitHubIssueResult,
    MainAgentIntakeRequest,
    TokenUsage,
)
from app.agents.main_agent import MainAgentService
from app.runtime.mcp import MCPClient, InMemoryMCPServer


class FakeGitHubService:
    def __init__(self) -> None:
        self.drafts: list[GitHubIssueDraft] = []

    def create_issue(self, repo: str, draft: GitHubIssueDraft) -> GitHubIssueResult:
        self.drafts.append(draft)
        return GitHubIssueResult(
            issue_number=101,
            title=draft.title,
            body=draft.body,
            html_url=f"https://github.com/{repo}/issues/101",
            labels=draft.labels,
            is_dry_run=False,
        )


def build_github_mcp(issue_number: int = 101) -> MCPClient:
    client = MCPClient()
    server = InMemoryMCPServer()
    server.register_tool(
        "create_issue",
        lambda arguments: {
            "issue_number": issue_number,
            "title": arguments["title"],
            "body": arguments["body"],
            "html_url": f"https://github.com/{arguments['repo']}/issues/{issue_number}",
            "labels": arguments.get("labels", []),
        },
        server="github",
    )
    client.register_adapter("github", server)
    return client


class FakeChannelService:
    def __init__(self) -> None:
        self.notifications: list[tuple[str, list[str]]] = []

    def notify(self, title: str, lines: list[str]):
        self.notifications.append((title, lines))
        return type(
            "ChannelNotificationResultStub",
            (),
            {"provider": "feishu", "delivered": False, "is_dry_run": True},
        )()


class FakeAgentRuntime:
    def __init__(self, content: str, mcp_client: MCPClient | None = None) -> None:
        self.content = content
        self.mcp = mcp_client or MCPClient()

    def generate_structured_output(self, agent, **kwargs):
        return type(
            "LLMResponseStub",
            (),
            {
                "output_text": self.content,
                "usage": TokenUsage(
                    prompt_tokens=90,
                    completion_tokens=30,
                    total_tokens=120,
                    provider="openai",
                    model_name="gpt-4.1-mini",
                    cost_usd=0.000084,
                ),
            },
        )()


class FailingAgentRuntime(FakeAgentRuntime):
    def __init__(self) -> None:
        super().__init__(content="{}")

    def generate_structured_output(self, agent, **kwargs):
        raise RuntimeError("LLM provider is unreachable")


def build_settings(database_path: Path, **kwargs) -> Settings:
    kwargs.setdefault("openai_api_key", None)
    kwargs.setdefault("minimax_api_key", None)
    return Settings(
        app_env="test",
        database_url=f"sqlite:///{database_path}",
        github_repository="tiezhuli001/youmeng-gateway",
        **kwargs,
    )


class MainAgentServiceTests(unittest.TestCase):
    def test_intake_records_request_usage_and_persists_request_id_on_control_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "main-agent.db")
            mcp_client = build_github_mcp()
            service = MainAgentService(
                settings,
                channel=FakeChannelService(),
                agent_runtime=FakeAgentRuntime(
                    json.dumps(
                        {
                            "title": "Record issue intake token",
                            "body": "Verify request usage recording.",
                            "labels": [
                                "agent:main",
                                "agent:ralph",
                                "workflow:intake",
                                "workflow:sleep-coding",
                            ],
                        }
                    ),
                    mcp_client=mcp_client,
                ),
                mcp_client=mcp_client,
            )

            response = service.intake(
                MainAgentIntakeRequest(
                    user_id="user-1",
                    content="记录 issue intake token",
                )
            )

            control_task = service.tasks.get_task(response.control_task_id)
            request_id = control_task.payload.get("request_id")

            self.assertIsInstance(request_id, str)
            usage = TokenLedgerService(settings).get_request_usage(request_id)
            self.assertEqual(usage.total_tokens, response.token_usage.total_tokens)
            self.assertEqual(usage.step_name, "main_agent_issue_intake")

    def test_intake_uses_heuristic_draft_without_llm_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            mcp_client = build_github_mcp()
            channel = FakeChannelService()
            service = MainAgentService(
                build_settings(Path(temp_dir) / "main-agent.db"),
                channel=channel,
                mcp_client=mcp_client,
            )
            response = service.intake(
                MainAgentIntakeRequest(
                    user_id="user-1",
                    content="需要支持从飞书接收需求并创建 GitHub issue",
                )
            )

            self.assertEqual(response.issue.issue_number, 101)
            self.assertIn("[Main Agent]", response.issue.title)
            self.assertIn("workflow:intake", response.issue.labels)
            self.assertIn("workflow:sleep-coding", response.issue.labels)
            self.assertIn("agent:ralph", response.issue.labels)
            self.assertGreater(response.token_usage.total_tokens, 0)
            self.assertEqual(response.token_usage.step_name, "main_agent_issue_intake")
            self.assertEqual(len(channel.notifications), 1)
            title, lines = channel.notifications[0]
            self.assertIn("Ralph 任务开始", title)
            self.assertTrue(any(line.startswith("任务摘要:") for line in lines))
            self.assertTrue(any(line.startswith("状态: ") for line in lines))

    def test_intake_uses_skill_runtime_draft_when_provider_is_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            mcp_client = build_github_mcp()
            service = MainAgentService(
                build_settings(Path(temp_dir) / "main-agent.db", openai_api_key="test-key"),
                channel=FakeChannelService(),
                agent_runtime=FakeAgentRuntime(
                    json.dumps(
                        {
                            "title": "Support Feishu requirement intake",
                            "body": "Implement the main agent intake path.",
                            "labels": [
                                "agent:main",
                                "agent:ralph",
                                "workflow:intake",
                                "workflow:sleep-coding",
                            ],
                        }
                    ),
                    mcp_client=mcp_client,
                ),
                mcp_client=mcp_client,
            )

            response = service.intake(
                MainAgentIntakeRequest(
                    user_id="user-1",
                    content="把飞书需求转成 issue",
                )
            )

            self.assertEqual(response.issue.title, "Support Feishu requirement intake")
            self.assertEqual(
                response.issue.labels,
                ["agent:main", "agent:ralph", "workflow:intake", "workflow:sleep-coding"],
            )
            self.assertEqual(response.token_usage.total_tokens, 120)
            self.assertEqual(response.token_usage.step_name, "main_agent_issue_intake")

    def test_intake_prefers_mcp_create_issue_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            github = FakeGitHubService()
            mcp_client = build_github_mcp(issue_number=202)
            service = MainAgentService(
                build_settings(Path(temp_dir) / "main-agent.db", openai_api_key="test-key"),
                github=github,
                channel=FakeChannelService(),
                agent_runtime=FakeAgentRuntime(
                    json.dumps(
                        {
                            "title": "Support MCP issue creation",
                            "body": "Create issue through MCP.",
                            "labels": ["agent:ralph", "workflow:sleep-coding"],
                        }
                    ),
                    mcp_client=mcp_client,
                ),
                mcp_client=mcp_client,
            )

            response = service.intake(
                MainAgentIntakeRequest(user_id="user-1", content="走 MCP 创建 issue")
            )

            self.assertEqual(response.issue.issue_number, 202)
            self.assertEqual(len(github.drafts), 0)

    def test_intake_raises_when_llm_call_fails_with_provider_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            mcp_client = build_github_mcp()
            service = MainAgentService(
                Settings(
                    app_env="development",
                    database_url=f"sqlite:///{Path(temp_dir) / 'main-agent.db'}",
                    github_repository="tiezhuli001/youmeng-gateway",
                    minimax_api_key="test-key",
                ),
                channel=FakeChannelService(),
                agent_runtime=FailingAgentRuntime(),
                mcp_client=mcp_client,
            )
            service.agent_runtime.mcp = mcp_client

            with self.assertRaisesRegex(RuntimeError, "LLM provider is unreachable"):
                service.intake(
                    MainAgentIntakeRequest(
                        user_id="user-1",
                        content="模型异常时必须显式失败",
                    )
                )


if __name__ == "__main__":
    unittest.main()
