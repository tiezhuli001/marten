import unittest

from app.core.config import Settings
from app.control.gateway import GatewayControlPlaneService
from app.control.routing import classify_intent, resolve_route
from app.models.schemas import (
    GatewayMessageRequest,
    GitHubIssueResult,
    MainAgentIntakeResponse,
    TokenUsage,
)


class FakeMainAgentService:
    def intake(self, payload):  # noqa: ANN001
        return MainAgentIntakeResponse(
            issue=GitHubIssueResult(
                issue_number=101,
                title="Gateway-created issue",
                body=payload.content,
                html_url="https://github.com/tiezhuli001/marten/issues/101",
                labels=["agent:ralph", "workflow:sleep-coding"],
                is_dry_run=True,
            ),
            message="Main Agent created #101: Gateway-created issue",
            token_usage=TokenUsage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                step_name="main_agent_issue_intake",
            ),
            control_task_id="control-task-101",
        )


class FakeSessionRegistryService:
    def __init__(self) -> None:
        self.payload_updates = []

    def get_or_create_session(self, **kwargs):  # noqa: ANN003
        return type("SessionStub", (), {"session_id": kwargs.get("external_ref", "session-1")})()

    def set_active_agent(self, session_id: str, agent_id: str):  # noqa: ANN001
        self.payload_updates.append((session_id, agent_id))
        return type("SessionStub", (), {"session_id": session_id, "payload": {"active_agent": agent_id}})()


class FakeLedgerService:
    def record_request(self, **kwargs):  # noqa: ANN003
        return kwargs["usage"]


class FakeTaskRegistryService:
    def __init__(self, parent_request_id: str | None = None) -> None:
        self.parent_request_id = parent_request_id

    def find_parent_for_issue(self, repo: str, issue_number: int):  # noqa: ANN001
        if self.parent_request_id is None:
            return None
        return type(
            "TaskStub",
            (),
            {
                "task_id": "parent-task-55",
                "payload": {
                    "request_id": self.parent_request_id,
                    "user_session_id": "user-session-55",
                },
            },
        )()


class FakeSleepCodingService:
    def __init__(self) -> None:
        self.requests = []

    def start_task(self, payload):  # noqa: ANN001
        self.requests.append(payload)
        return type("TaskStub", (), {"task_id": "sleep-task-55", "status": "awaiting_confirmation", "head_branch": "codex/issue-55-sleep-coding"})()


class GatewayRoutingTests(unittest.TestCase):
    def test_issue_pr_review_words_do_not_bypass_general_intake(self) -> None:
        self.assertEqual(classify_intent("请创建一个 issue 并后续补 review"), "general")
        self.assertEqual(classify_intent("这次 PR 需要补一条测试"), "general")

    def test_explicit_ralph_mention_routes_to_sleep_coding(self) -> None:
        route = resolve_route("@ralph 请帮我接手 issue #55")

        self.assertEqual(route.intent, "sleep_coding")
        self.assertEqual(route.target_agent, "ralph")
        self.assertTrue(route.direct_mention)

    def test_review_mention_is_kept_on_main_agent_entry(self) -> None:
        route = resolve_route("让 review 看一下这个需求")

        self.assertEqual(route.intent, "general")
        self.assertEqual(route.target_agent, "main-agent")
        self.assertFalse(route.direct_mention)

    def test_general_request_with_issue_word_still_creates_issue_via_main_agent(self) -> None:
        sessions = FakeSessionRegistryService()
        service = GatewayControlPlaneService(
            settings=Settings(app_env="test", database_url="sqlite:////tmp/test-gateway.db"),
            main_agent=FakeMainAgentService(),
            sessions=sessions,
            ledger=FakeLedgerService(),
        )

        response = service.run(
            GatewayMessageRequest(
                user_id="feishu:test-user",
                source="feishu",
                content="请帮我整理这个需求并创建一个 issue：补一条真实链路验证测试。",
            )
        )

        self.assertEqual(response.intent, "general")
        self.assertEqual(response.task_id, "control-task-101")
        self.assertEqual(response.token_usage.step_name, "main_agent_issue_intake")
        self.assertEqual(response.chain_request_id, response.request_id)
        self.assertIsNotNone(response.run_session_id)
        self.assertEqual(sessions.payload_updates[-1][1], "main-agent")

    def test_sleep_coding_request_inherits_chain_request_id_from_parent_issue(self) -> None:
        sleep_coding = FakeSleepCodingService()
        service = GatewayControlPlaneService(
            settings=Settings(app_env="test", database_url="sqlite:////tmp/test-gateway.db"),
            sleep_coding=sleep_coding,
            sessions=FakeSessionRegistryService(),
            ledger=FakeLedgerService(),
            tasks=FakeTaskRegistryService(parent_request_id="req-parent-55"),
        )

        response = service.run(
            GatewayMessageRequest(
                user_id="feishu:test-user",
                source="feishu",
                content="写代码 issue #55",
            )
        )

        self.assertEqual(response.intent, "sleep_coding")
        self.assertEqual(response.request_id != response.chain_request_id, True)
        self.assertEqual(response.chain_request_id, "req-parent-55")
        self.assertEqual(sleep_coding.requests[0].request_id, "req-parent-55")

    def test_explicit_ralph_mention_starts_sleep_coding_even_without_keyword(self) -> None:
        sleep_coding = FakeSleepCodingService()
        sessions = FakeSessionRegistryService()
        service = GatewayControlPlaneService(
            settings=Settings(app_env="test", database_url="sqlite:////tmp/test-gateway.db"),
            sleep_coding=sleep_coding,
            sessions=sessions,
            ledger=FakeLedgerService(),
        )

        response = service.run(
            GatewayMessageRequest(
                user_id="feishu:test-user",
                source="feishu",
                content="@ralph issue #55",
            )
        )

        self.assertEqual(response.intent, "sleep_coding")
        self.assertEqual(sleep_coding.requests[0].issue_number, 55)
        self.assertEqual(sessions.payload_updates[-1][1], "ralph")


if __name__ == "__main__":
    unittest.main()
