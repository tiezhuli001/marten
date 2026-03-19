import unittest
import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/youmeng-gateway-test-api.db")
os.environ.setdefault("REVIEW_RUNS_DIR", "/tmp/youmeng-gateway-test-review-runs")
os.environ.setdefault("CHANNEL_WEBHOOK_URL", "")

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.api.routes import (
    get_automation_service,
    get_feishu_webhook_service,
    get_gateway_control_plane_service,
    get_integration_diagnostics_service,
    get_main_agent_service,
    get_review_service,
    get_session_registry_service,
    get_sleep_coding_service,
    get_sleep_coding_worker_service,
    get_task_registry_service,
    get_token_ledger_service,
    get_worker_scheduler_service,
)
from app.models.schemas import (
    ControlTask,
    ControlTaskEvent,
    DailyTokenSummary,
    MainAgentIntakeResponse,
    ReviewActionRequest,
    ReviewRun,
    ReviewRunRequest,
    ReviewSource,
    TokenReportResponse,
    TokenWindowSummary,
)


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        get_settings.cache_clear()
        get_gateway_control_plane_service.cache_clear()
        get_sleep_coding_service.cache_clear()
        get_automation_service.cache_clear()
        get_feishu_webhook_service.cache_clear()
        get_main_agent_service.cache_clear()
        get_review_service.cache_clear()
        get_sleep_coding_worker_service.cache_clear()
        get_task_registry_service.cache_clear()
        get_session_registry_service.cache_clear()
        get_token_ledger_service.cache_clear()
        get_worker_scheduler_service.cache_clear()
        get_integration_diagnostics_service.cache_clear()
        self.client = TestClient(app)

        class FakeReviewService:
            def start_review(self, payload: ReviewRunRequest) -> ReviewRun:
                return ReviewRun(
                    review_id="review-1",
                    source=payload.source,
                    status="completed",
                    artifact_path="docs/review-runs/local-review-review-1.md",
                    comment_url=payload.source.url,
                    summary="Review complete",
                    content="## Code Review Agent",
                    run_mode="dry_run",
                    task_id=payload.source.task_id,
                    created_at="2026-03-16 00:00:00",
                    updated_at="2026-03-16 00:00:00",
                    reviewed_at="2026-03-16 00:00:00",
                )

            def get_review(self, review_id: str) -> ReviewRun:
                return self.start_review(
                    ReviewRunRequest(source=ReviewSource(source_type="local_code", local_path="."))
                )

            def apply_action(self, review_id: str, payload: ReviewActionRequest) -> ReviewRun:
                review = self.get_review(review_id)
                return review.model_copy(
                    update={"status": "approved" if payload.action == "approve_review" else "changes_requested"}
                )

            def trigger_for_task(self, task_id: str) -> ReviewRun:
                return self.start_review(
                    ReviewRunRequest(
                        source=ReviewSource(source_type="sleep_coding_task", task_id=task_id)
                    )
                )

        app.dependency_overrides[get_review_service] = lambda: FakeReviewService()

        class FakeTokenLedgerService:
            def get_window_report(self, window: str) -> TokenReportResponse:
                return TokenReportResponse(
                    summary_text=f"window={window}",
                    window_summary=TokenWindowSummary(
                        window=window,  # type: ignore[arg-type]
                        start_date="2026-03-10",
                        end_date="2026-03-16",
                        request_count=2,
                        workflow_run_count=2,
                        prompt_tokens=20,
                        completion_tokens=10,
                        total_tokens=30,
                        estimated_cost_usd=0.5,
                    ),
                )

            def get_daily_summary(self, summary_date: str) -> DailyTokenSummary:
                return DailyTokenSummary(
                    summary_date=summary_date,
                    request_count=1,
                    workflow_run_count=1,
                    prompt_tokens=10,
                    completion_tokens=5,
                    total_tokens=15,
                    estimated_cost_usd=0.2,
                    top_intent="stats_query",
                    top_step_name="stats_query_handler",
                    summary_text=f"daily={summary_date}",
                )

            def generate_daily_summary(self, summary_date: str) -> DailyTokenSummary:
                return self.get_daily_summary(summary_date)

            def generate_yesterday_summary(self) -> DailyTokenSummary:
                return self.get_daily_summary("2026-03-15")

        app.dependency_overrides[get_token_ledger_service] = lambda: FakeTokenLedgerService()

        class FakeFeishuWebhookService:
            def handle_event(self, raw_body: bytes, headers):
                return {
                    "code": 0,
                    "msg": "ok",
                    "gateway_response": {
                        "request_id": "req-feishu-1",
                        "intent": "general",
                        "message": "processed",
                        "token_usage": {"total_tokens": 18},
                    },
                }

        app.dependency_overrides[get_feishu_webhook_service] = lambda: FakeFeishuWebhookService()

        class FakeMainAgentService:
            def intake(self, payload) -> MainAgentIntakeResponse:
                return MainAgentIntakeResponse.model_validate(
                    {
                        "issue": {
                            "issue_number": 101,
                        "title": "Support Feishu requirement intake",
                        "body": "Implement the main agent intake path.",
                            "html_url": "https://github.com/tiezhuli001/youmeng-gateway/issues/101",
                            "labels": [
                                "agent:main",
                                "agent:ralph",
                                "workflow:intake",
                                "workflow:sleep-coding",
                            ],
                            "is_dry_run": True,
                        },
                        "message": "Main Agent created #101: Support Feishu requirement intake",
                        "token_usage": {
                            "prompt_tokens": 90,
                            "completion_tokens": 30,
                            "total_tokens": 120,
                            "provider": "openai",
                            "model_name": "gpt-4.1-mini",
                            "cost_usd": 0.000084,
                            "step_name": "main_agent_issue_intake",
                        },
                    }
                )

        app.dependency_overrides[get_main_agent_service] = lambda: FakeMainAgentService()

        class FakeGatewayControlPlaneService:
            def run(self, payload):
                if "统计最近7天 token 消耗" in payload.content:
                    return {
                        "request_id": "req-gateway-1",
                        "intent": "stats_query",
                        "message": "最近 7 天 token 消耗如下",
                        "token_usage": {
                            "prompt_tokens": 10,
                            "completion_tokens": 5,
                            "total_tokens": 15,
                            "cost_usd": 0.001,
                            "step_name": "stats_query_handler",
                        },
                        "task_id": None,
                    }
                if "issue 42" in payload.content and "review" not in payload.content:
                    return {
                        "request_id": "req-gateway-2",
                        "intent": "sleep_coding",
                        "message": "Sleep coding task queued. Status=awaiting_confirmation",
                        "token_usage": {
                            "prompt_tokens": 20,
                            "completion_tokens": 8,
                            "total_tokens": 28,
                            "cost_usd": 0.002,
                            "step_name": "sleep_coding_handler",
                        },
                        "task_id": "task-worker-1",
                    }
                return {
                    "request_id": "req-gateway-3",
                    "intent": "sleep_coding",
                    "message": "Provide an issue number or issue URL for sleep coding.",
                    "token_usage": {
                        "prompt_tokens": 12,
                        "completion_tokens": 4,
                        "total_tokens": 16,
                        "cost_usd": 0.001,
                        "step_name": "sleep_coding_handler",
                    },
                    "task_id": None,
                }

        app.dependency_overrides[get_gateway_control_plane_service] = (
            lambda: FakeGatewayControlPlaneService()
        )

        class FakeSleepCodingService:
            def start_task(self, payload):
                return {
                    "task_id": "task-42",
                    "issue_number": payload.issue_number,
                    "repo": payload.repo or "tiezhuli001/youmeng-gateway",
                    "base_branch": "main",
                    "head_branch": f"codex/issue-{payload.issue_number}-sleep-coding",
                    "status": "awaiting_confirmation",
                    "issue": {
                        "issue_number": payload.issue_number,
                        "title": payload.issue_title or "Implement sleep coding API",
                        "body": payload.issue_body or "Need the task creation and review endpoints.",
                        "state": "open",
                        "html_url": (
                            f"https://github.com/tiezhuli001/youmeng-gateway/issues/{payload.issue_number}"
                        ),
                        "labels": ["agent:ralph", "workflow:sleep-coding"],
                        "is_dry_run": True,
                    },
                    "plan": {
                        "summary": f"Implement Issue #{payload.issue_number}: Implement sleep coding API",
                        "scope": ["scope"],
                        "validation": ["validation"],
                        "risks": ["risk"],
                    },
                    "git_execution": {"status": "pending", "output": "", "is_dry_run": True},
                    "validation": {
                        "status": "pending",
                        "command": "python -m unittest discover -s tests",
                        "output": "",
                    },
                    "pull_request": None,
                    "events": [],
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "last_error": None,
                    "kickoff_request_id": None,
                    "created_at": "2026-03-16 00:00:00",
                    "updated_at": "2026-03-16 00:00:00",
                }

            def get_task(self, task_id: str):
                return FakeAutomationService().handle_sleep_coding_action(task_id, "approve_pr")

        app.dependency_overrides[get_sleep_coding_service] = lambda: FakeSleepCodingService()

        class FakeSleepCodingWorkerService:
            def poll_once(self, payload):
                return {
                    "repo": "tiezhuli001/youmeng-gateway",
                    "worker_id": payload.worker_id,
                    "auto_approve_plan": bool(payload.auto_approve_plan),
                    "discovered_count": 1,
                    "claimed_count": 1,
                    "skipped_count": 0,
                    "tasks": [
                        {
                            "task_id": "task-worker-1",
                            "issue_number": 101,
                            "repo": "tiezhuli001/youmeng-gateway",
                            "base_branch": "main",
                            "head_branch": "codex/issue-101-sleep-coding",
                            "status": "awaiting_confirmation",
                            "issue": {
                                "issue_number": 101,
                                "title": "Support Feishu requirement intake",
                                "body": "Implement the main agent intake path.",
                                "state": "open",
                                "html_url": "https://github.com/tiezhuli001/youmeng-gateway/issues/101",
                                "labels": ["agent:ralph", "workflow:sleep-coding"],
                                "is_dry_run": True,
                            },
                            "plan": {
                                "summary": "Implement Issue #101: Support Feishu requirement intake",
                                "scope": ["scope"],
                                "validation": ["validation"],
                                "risks": ["risk"],
                            },
                            "git_execution": {
                                "status": "pending",
                                "output": "",
                                "is_dry_run": True,
                            },
                            "validation": {
                                "status": "pending",
                                "command": "python -m unittest discover -s tests",
                                "output": "",
                            },
                            "pull_request": None,
                            "events": [],
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "total_tokens": 0,
                            "last_error": None,
                            "kickoff_request_id": None,
                            "created_at": "2026-03-16 00:00:00",
                            "updated_at": "2026-03-16 00:00:00",
                        }
                    ],
                    "claims": [
                        {
                            "issue_number": 101,
                            "repo": "tiezhuli001/youmeng-gateway",
                            "task_id": "task-worker-1",
                            "status": "awaiting_confirmation",
                            "title": "Support Feishu requirement intake",
                            "html_url": "https://github.com/tiezhuli001/youmeng-gateway/issues/101",
                            "labels": ["agent:ralph", "workflow:sleep-coding"],
                            "created_at": "2026-03-16 00:00:00",
                            "updated_at": "2026-03-16 00:00:00",
                        }
                    ],
                }

            def list_claims(self, repo=None):
                return [
                    {
                        "issue_number": 101,
                        "repo": repo or "tiezhuli001/youmeng-gateway",
                        "task_id": "task-worker-1",
                        "status": "awaiting_confirmation",
                        "title": "Support Feishu requirement intake",
                        "html_url": "https://github.com/tiezhuli001/youmeng-gateway/issues/101",
                        "labels": ["agent:ralph", "workflow:sleep-coding"],
                        "created_at": "2026-03-16 00:00:00",
                        "updated_at": "2026-03-16 00:00:00",
                    }
                ]

        app.dependency_overrides[get_sleep_coding_worker_service] = lambda: FakeSleepCodingWorkerService()

        class FakeAutomationService:
            def handle_sleep_coding_action(self, task_id: str, action: str):
                return {
                    "task_id": task_id,
                    "issue_number": 42,
                    "repo": "tiezhuli001/youmeng-gateway",
                    "base_branch": "main",
                    "head_branch": "codex/issue-42-sleep-coding",
                    "status": "approved" if action == "approve_pr" else "approved",
                    "issue": {
                        "issue_number": 42,
                        "title": "Implement sleep coding API",
                        "body": "Need the task creation and review endpoints.",
                        "state": "open",
                        "html_url": "https://github.com/tiezhuli001/youmeng-gateway/issues/42",
                        "labels": ["agent:ralph", "workflow:sleep-coding"],
                        "is_dry_run": True,
                    },
                    "plan": {
                        "summary": "Implement Issue #42: Implement sleep coding API",
                        "scope": ["scope"],
                        "validation": ["validation"],
                        "risks": ["risk"],
                    },
                    "git_execution": {"status": "skipped", "output": "", "is_dry_run": True},
                    "validation": {
                        "status": "passed",
                        "command": "python -m unittest discover -s tests",
                        "output": "ok",
                    },
                    "pull_request": {
                        "title": "[Ralph] #42 Implement sleep coding API",
                        "body": "body",
                        "html_url": "https://github.com/tiezhuli001/youmeng-gateway/pull/88",
                        "pr_number": 88,
                        "state": "open",
                        "labels": ["agent:ralph", "workflow:sleep-coding"],
                        "is_dry_run": True,
                    },
                    "events": [],
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "last_error": None,
                    "kickoff_request_id": None,
                    "created_at": "2026-03-16 00:00:00",
                    "updated_at": "2026-03-16 00:00:00",
                }

            def handle_sleep_coding_action_async(self, task_id: str, action: str):
                return self.handle_sleep_coding_action(task_id, action)

            def process_worker_poll(self, payload):
                return FakeSleepCodingWorkerService().poll_once(payload)

            def process_worker_poll_async(self, payload):
                return self.process_worker_poll(payload)

        app.dependency_overrides[get_automation_service] = lambda: FakeAutomationService()

        class FakeTaskRegistryService:
            def get_task(self, task_id: str) -> ControlTask:
                return ControlTask.model_validate(
                    {
                        "task_id": task_id,
                        "task_type": "main_agent_intake",
                        "agent_id": "main-agent",
                        "status": "issue_created",
                        "parent_task_id": None,
                        "root_task_id": None,
                        "user_id": "user-1",
                        "source": "manual",
                        "repo": "tiezhuli001/youmeng-gateway",
                        "issue_number": 101,
                        "title": "Support Feishu requirement intake",
                        "external_ref": "github_issue:tiezhuli001/youmeng-gateway#101",
                        "payload": {"issue_url": "https://github.com/tiezhuli001/youmeng-gateway/issues/101"},
                        "created_at": "2026-03-16 00:00:00",
                        "updated_at": "2026-03-16 00:00:00",
                    }
                )

            def list_events(self, task_id: str) -> list[ControlTaskEvent]:
                return [
                    ControlTaskEvent(
                        event_id=1,
                        task_id=task_id,
                        event_type="task_created",
                        payload={"status": "issue_created"},
                        created_at="2026-03-16 00:00:00",
                    )
                ]

        app.dependency_overrides[get_task_registry_service] = lambda: FakeTaskRegistryService()

        class FakeWorkerSchedulerService:
            def __init__(self) -> None:
                self.runs = 0

            def run_once(self):
                self.runs += 1

        app.dependency_overrides[get_worker_scheduler_service] = lambda: FakeWorkerSchedulerService()

        class FakeIntegrationDiagnosticsService:
            def get_report(self):
                return {
                    "github_mcp": {"status": "not_configured"},
                    "review_skill": {"status": "ok", "mode": "runtime_llm"},
                    "feishu": {"status": "partial", "inbound": True, "outbound": False},
                }

        app.dependency_overrides[get_integration_diagnostics_service] = lambda: FakeIntegrationDiagnosticsService()

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        get_gateway_control_plane_service.cache_clear()
        get_sleep_coding_service.cache_clear()
        get_automation_service.cache_clear()
        get_feishu_webhook_service.cache_clear()
        get_main_agent_service.cache_clear()
        get_review_service.cache_clear()
        get_sleep_coding_worker_service.cache_clear()
        get_task_registry_service.cache_clear()
        get_session_registry_service.cache_clear()
        get_token_ledger_service.cache_clear()
        get_worker_scheduler_service.cache_clear()
        get_integration_diagnostics_service.cache_clear()

    def test_health_endpoint(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_integration_diagnostics_endpoint(self) -> None:
        response = self.client.get("/diagnostics/integrations")

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["github_mcp"]["status"], "not_configured")
        self.assertEqual(payload["review_skill"]["status"], "ok")

    def test_gateway_message_endpoint(self) -> None:
        response = self.client.post(
            "/gateway/message",
            json={
                "user_id": "user-1",
                "content": "帮我统计最近7天 token 消耗",
                "source": "manual",
            },
        )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["intent"], "stats_query")
        self.assertIn("token_usage", payload)

    def test_sleep_coding_task_endpoint(self) -> None:
        response = self.client.post(
            "/tasks/sleep-coding",
            json={
                "issue_number": 42,
                "repo": "tiezhuli001/youmeng-gateway",
                "issue_title": "Implement sleep coding API",
                "issue_body": "Need the task creation and review endpoints.",
            },
        )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "awaiting_confirmation")
        self.assertEqual(payload["issue_number"], 42)
        self.assertIn("agent:ralph", payload["issue"]["labels"])

    def test_gateway_message_creates_sleep_coding_task_when_issue_number_is_present(self) -> None:
        response = self.client.post(
            "/gateway/message",
            json={
                "user_id": "user-1",
                "content": "请处理 issue 42 并准备 pr",
                "source": "manual",
            },
        )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["intent"], "sleep_coding")
        self.assertIn("Status=awaiting_confirmation", payload["message"])

    def test_gateway_message_requires_issue_context_for_numeric_tokens(self) -> None:
        response = self.client.post(
            "/gateway/message",
            json={
                "user_id": "user-1",
                "content": "请帮我 review 42 这个需求",
                "source": "manual",
            },
        )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["intent"], "sleep_coding")
        self.assertIn("Provide an issue number", payload["message"])

    def test_create_review_endpoint(self) -> None:
        response = self.client.post(
            "/reviews",
            json={
                "source": {
                    "source_type": "local_code",
                    "local_path": ".",
                }
            },
        )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["source"]["source_type"], "local_code")

    def test_trigger_sleep_coding_review_endpoint(self) -> None:
        response = self.client.post("/tasks/sleep-coding/task-1/review")

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["source"]["source_type"], "sleep_coding_task")
        self.assertEqual(payload["task_id"], "task-1")

    def test_get_token_report_endpoint(self) -> None:
        response = self.client.get("/reports/tokens?window=7d")

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["window_summary"]["window"], "7d")
        self.assertEqual(payload["summary_text"], "window=7d")

    def test_generate_daily_token_summary_endpoint(self) -> None:
        response = self.client.post("/reports/tokens/daily/generate?date=2026-03-15")

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["summary_date"], "2026-03-15")
        self.assertEqual(payload["total_tokens"], 15)

    def test_get_daily_token_summary_endpoint(self) -> None:
        response = self.client.get("/reports/tokens/daily/2026-03-15")

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["summary_text"], "daily=2026-03-15")

    def test_get_token_report_rejects_unsupported_window(self) -> None:
        class InvalidWindowLedgerService:
            def get_window_report(self, window: str):
                raise ValueError(f"Unsupported token window: {window}")

        app.dependency_overrides[get_token_ledger_service] = lambda: InvalidWindowLedgerService()

        response = self.client.get("/reports/tokens?window=90d")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported token window", response.json()["detail"])

    def test_main_agent_intake_endpoint(self) -> None:
        response = self.client.post(
            "/main-agent/intake",
            json={
                "user_id": "user-1",
                "content": "把飞书需求转成 GitHub issue",
                "source": "manual",
            },
        )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["issue"]["issue_number"], 101)
        self.assertEqual(payload["token_usage"]["step_name"], "main_agent_issue_intake")

    def test_get_control_task_endpoint(self) -> None:
        response = self.client.get("/control/tasks/task-parent-1")

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["task_id"], "task-parent-1")
        self.assertEqual(payload["task_type"], "main_agent_intake")

    def test_list_control_task_events_endpoint(self) -> None:
        response = self.client.get("/control/tasks/task-parent-1/events")

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload[0]["event_type"], "task_created")

    def test_sleep_coding_worker_poll_endpoint(self) -> None:
        response = self.client.post(
            "/workers/sleep-coding/poll",
            json={
                "worker_id": "sleep-coding-worker",
                "auto_approve_plan": False,
                "limit": 20,
            },
        )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["discovered_count"], 1)
        self.assertEqual(payload["claimed_count"], 1)
        self.assertEqual(payload["tasks"][0]["task_id"], "task-worker-1")

    def test_sleep_coding_worker_claims_endpoint(self) -> None:
        response = self.client.get("/workers/sleep-coding/claims")

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload[0]["issue_number"], 101)

    def test_sleep_coding_worker_run_once_endpoint(self) -> None:
        response = self.client.post("/workers/sleep-coding/run-once")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_feishu_webhook_endpoint(self) -> None:
        response = self.client.post(
            "/webhooks/feishu/events",
            json={"type": "event_callback"},
            headers={"X-Lark-Request-Timestamp": "1700000000"},
        )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["code"], 0)
        self.assertEqual(payload["gateway_response"]["request_id"], "req-feishu-1")

    def test_feishu_webhook_returns_unauthorized_for_bad_signature(self) -> None:
        class InvalidSignatureService:
            def handle_event(self, raw_body: bytes, headers):
                raise PermissionError("Invalid Feishu signature")

        app.dependency_overrides[get_feishu_webhook_service] = lambda: InvalidSignatureService()

        response = self.client.post("/webhooks/feishu/events", json={"type": "event_callback"})

        self.assertEqual(response.status_code, 401)
        self.assertIn("Invalid Feishu signature", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
