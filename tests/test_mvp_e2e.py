import tempfile
import unittest
import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.routes import (
    get_automation_service,
    get_feishu_webhook_service,
    get_gateway_control_plane_service,
    get_main_agent_service,
    get_review_service,
    get_session_registry_service,
    get_sleep_coding_service,
    get_task_registry_service,
)
from app.control.gateway import GatewayControlPlaneService
from app.control.workflow import GatewayWorkflowService
from app.main import app
from app.core.config import Settings, get_settings
from app.ledger.service import TokenLedgerService
from app.models.schemas import (
    GitExecutionResult,
    GitHubIssueDraft,
    GitHubIssueResult,
    MainAgentIntakeRequest,
    ReviewFinding,
    ReviewSkillOutput,
    SleepCodingIssue,
    SleepCodingPullRequest,
    SleepCodingTaskActionRequest,
    SleepCodingTaskRequest,
    SleepCodingWorkerPollRequest,
    TokenUsage,
    ValidationResult,
    WorkerDiscoveredIssue,
)
from app.runtime.mcp import InMemoryMCPServer, MCPClient
from app.agents.code_review_agent import ReviewService, ReviewSkillRunResult
from app.control.automation import AutomationService
from app.channel.feishu import FeishuWebhookService
from app.channel.notifications import ChannelNotificationResult
from app.agents.main_agent import MainAgentService
from app.agents.ralph import SleepCodingService
from app.control.sleep_coding_worker import SleepCodingWorkerService


def build_github_mcp(github: "FakeGitHubService") -> MCPClient:
    client = MCPClient()
    server = InMemoryMCPServer()
    server.register_tool(
        "create_issue",
        lambda arguments: github.create_issue(
            arguments["repo"],
            GitHubIssueDraft(
                title=str(arguments["title"]),
                body=str(arguments["body"]),
                labels=list(arguments.get("labels", [])),
            ),
        ).model_dump(mode="json"),
        server="github",
    )
    server.register_tool(
        "list_issues",
        lambda arguments: [
            {
                "number": issue.issue_number,
                "title": issue.title,
                "body": issue.body,
                "state": "open",
                "html_url": issue.html_url,
                "labels": [{"name": label} for label in issue.labels],
            }
            for issue in github.list_open_issues(
                repo=str(arguments["repo"]),
                labels=list(arguments.get("labels", [])),
                limit=int(arguments.get("perPage", arguments.get("limit", 20))),
            )
        ],
        server="github",
    )
    server.register_tool(
        "get_issue",
        lambda arguments: github.get_issue(
            str(arguments["repo"]),
            int(arguments["issue_number"]),
        ).model_dump(mode="json"),
        server="github",
    )
    server.register_tool(
        "create_issue_comment",
        lambda arguments: {
            "html_url": github.create_issue_comment(
                str(arguments["repo"]),
                int(arguments["issue_number"]),
                str(arguments["body"]),
            ).html_url,
            "is_dry_run": True,
        },
        server="github",
    )
    server.register_tool(
        "apply_labels",
        lambda arguments: {
            "labels": github.apply_labels(
                str(arguments["repo"]),
                int(arguments["issue_number"]),
                list(arguments["labels"]),
            ).labels,
            "is_dry_run": True,
        },
        server="github",
    )
    server.register_tool(
        "create_pull_request",
        lambda arguments: {
            "title": str(arguments["title"]),
            "body": str(arguments["body"]),
            "html_url": (
                github.create_pull_request(
                    str(arguments["repo"]),
                    next(iter(github.issues.values())),
                    {},
                    {},
                    str(arguments["head_branch"]),
                    str(arguments["base_branch"]),
                ).html_url
            ),
            "number": github.pr_counter,
            "state": "open",
            "is_dry_run": True,
        },
        server="github",
    )
    server.register_tool(
        "pull_request_review_write",
        lambda arguments: {
            "html_url": github.create_pull_request_comment(
                str(arguments["repo"]),
                int(arguments["pr_number"]),
                str(arguments["body"]),
            ).html_url,
            "is_dry_run": True,
        },
        server="github",
    )
    client.register_adapter("github", server)
    return client


class ImmediateBackgroundJobs:
    def __init__(self) -> None:
        self.active_keys: set[str] = set()

    def submit_unique(self, key: str, fn, *args: object) -> bool:  # noqa: ANN001
        if key in self.active_keys:
            return False
        self.active_keys.add(key)
        try:
            fn(*args)
        finally:
            self.active_keys.discard(key)
        return True


class FakeChannelService:
    def __init__(self) -> None:
        self.notifications: list[tuple[str, list[str], str | None]] = []

    def notify(
        self,
        title: str,
        lines: list[str],
        endpoint_id: str | None = None,
    ) -> ChannelNotificationResult:
        self.notifications.append((title, lines, endpoint_id))
        return ChannelNotificationResult(
            provider="feishu",
            delivered=False,
            is_dry_run=True,
            endpoint_id=endpoint_id,
        )


class FakeGitHubService:
    def __init__(self) -> None:
        self.issue_counter = 100
        self.pr_counter = 500
        self.issues: dict[int, SleepCodingIssue] = {}
        self.issue_comments: list[tuple[int, str]] = []
        self.pr_comments: list[tuple[int, str]] = []
        self.create_issue_calls = 0

    def create_issue(self, repo: str, draft: GitHubIssueDraft) -> GitHubIssueResult:
        self.create_issue_calls += 1
        self.issue_counter += 1
        issue = SleepCodingIssue(
            issue_number=self.issue_counter,
            title=draft.title,
            body=draft.body,
            html_url=f"https://github.com/{repo}/issues/{self.issue_counter}",
            labels=list(draft.labels),
            is_dry_run=True,
        )
        self.issues[issue.issue_number] = issue
        return GitHubIssueResult(
            issue_number=issue.issue_number,
            title=issue.title,
            body=issue.body,
            html_url=issue.html_url,
            labels=issue.labels,
            is_dry_run=True,
        )

    def list_open_issues(self, repo: str, labels: list[str] | None = None, limit: int = 20):
        issues = list(self.issues.values())
        if labels:
            required = set(labels)
            issues = [issue for issue in issues if required.issubset(set(issue.labels))]
        return [
            WorkerDiscoveredIssue(
                issue_number=issue.issue_number,
                title=issue.title,
                body=issue.body,
                state="open",
                html_url=issue.html_url,
                labels=list(issue.labels),
                is_dry_run=True,
            )
            for issue in issues[:limit]
        ]

    def get_issue(self, repo: str, issue_number: int, title_override=None, body_override=None):
        issue = self.issues.get(issue_number)
        if issue is None:
            issue = SleepCodingIssue(
                issue_number=issue_number,
                title=title_override or f"Issue #{issue_number}",
                body=body_override or "",
                html_url=f"https://github.com/{repo}/issues/{issue_number}",
                labels=["agent:ralph", "workflow:sleep-coding"],
                is_dry_run=True,
            )
            self.issues[issue_number] = issue
        return issue

    def create_issue_comment(self, repo: str, issue_number: int, body: str):
        self.issue_comments.append((issue_number, body))
        return type(
            "GitHubCommentResultStub",
            (),
            {
                "html_url": f"https://github.com/{repo}/issues/{issue_number}#issuecomment-{len(self.issue_comments)}",
                "is_dry_run": True,
            },
        )()

    def apply_labels(self, repo: str, issue_number: int, labels: list[str]):
        issue = self.issues.get(issue_number)
        if issue is not None:
            self.issues[issue_number] = issue.model_copy(update={"labels": list(labels)})
        return type(
            "GitHubLabelResultStub",
            (),
            {"labels": list(labels), "is_dry_run": True},
        )()

    def create_pull_request(self, repo, issue, plan, validation, head_branch, base_branch):
        self.pr_counter += 1
        return SleepCodingPullRequest(
            title=f"[Ralph] #{issue.issue_number} {issue.title}",
            body="dry run pr",
            html_url=f"https://github.com/{repo}/pull/{self.pr_counter}",
            pr_number=self.pr_counter,
            state="open",
            labels=["agent:ralph", "workflow:sleep-coding"],
            is_dry_run=True,
        )

    def create_pull_request_comment(self, repo: str, pr_number: int, body: str):
        self.pr_comments.append((pr_number, body))
        return type(
            "GitHubCommentResultStub",
            (),
            {
                "html_url": f"https://github.com/{repo}/pull/{pr_number}#issuecomment-{len(self.pr_comments)}",
                "is_dry_run": True,
            },
        )()


class FakeGitWorkspaceService:
    def prepare_worktree(self, branch):
        from app.models.schemas import GitExecutionResult

        return GitExecutionResult(
            status="prepared",
            worktree_path=f"/tmp/{branch.replace('/', '__')}",
            output="prepared",
            is_dry_run=True,
        )

    def write_task_artifact(self, branch, task_id, issue_number, artifact_markdown, file_changes=None):
        from app.models.schemas import GitExecutionResult

        return GitExecutionResult(
            status="prepared",
            worktree_path=f"/tmp/{branch.replace('/', '__')}",
            artifact_path=f"/tmp/{branch.replace('/', '__')}/.sleep_coding/issue-{issue_number}.md",
            output=artifact_markdown,
            is_dry_run=True,
        )

    def capture_worktree_evidence(self, branch):
        from app.models.schemas import GitExecutionResult

        changed_files = [
            ".sleep_coding/issue-artifact.md",
            "tests/generated_test.py",
        ]
        return GitExecutionResult(
            status="prepared",
            worktree_path=f"/tmp/{branch.replace('/', '__')}",
            output="captured worktree evidence",
            is_dry_run=True,
            changed_files=changed_files,
            file_changes=[
                {"path": path, "diff_excerpt": f"new file: {path}"}
                for path in changed_files
            ],
            diff_summary="2 files changed in worktree.",
            diff_excerpt="new file: tests/generated_test.py",
        )

    def commit_changes(self, branch, message):
        from app.models.schemas import GitExecutionResult

        return GitExecutionResult(
            status="skipped",
            worktree_path=f"/tmp/{branch.replace('/', '__')}",
            output=message,
            is_dry_run=True,
        )

    def push_branch(self, branch):
        from app.models.schemas import GitExecutionResult

        return GitExecutionResult(
            status="skipped",
            worktree_path=f"/tmp/{branch.replace('/', '__')}",
            push_remote="origin",
            output="push skipped",
            is_dry_run=True,
        )

    def cleanup_worktree(self, branch):
        return None


class FakeValidationRunner:
    def run(self, repo_path: Path) -> ValidationResult:
        return ValidationResult(
            status="passed",
            command="python -m unittest discover -s tests",
            exit_code=0,
            output="ok",
        )


class FakeRalphAgentRuntime:
    def __init__(self) -> None:
        self.mcp = MCPClient()

    def generate_structured_output(self, agent, *, output_contract, **kwargs):
        if "artifact_markdown" in output_contract:
            output_text = (
                '{"artifact_markdown":"## Summary\\nGenerated coding draft",'
                '"commit_message":"feat: implement sleep coding task",'
                '"file_changes":[{"path":"tests/generated_test.py","content":"print(\\"ok\\")","description":"generated test"}]}'
            )
        else:
            output_text = (
                '{"summary":"LLM generated plan","scope":["Update service code","Add tests"],'
                '"validation":["python -m unittest discover -s tests"],'
                '"risks":["Issue details may still need clarification."]}'
            )
        return type(
            "LLMResponseStub",
            (),
            {
                "output_text": output_text,
                "usage": TokenUsage(
                    prompt_tokens=22,
                    completion_tokens=8,
                    total_tokens=30,
                    provider="openai",
                    model_name="gpt-4.1-mini",
                    cost_usd=0.001,
                ),
            },
        )()


class FakeMainAgentRuntime:
    def __init__(self, mcp_client: MCPClient) -> None:
        self.mcp = mcp_client

    def generate_structured_output(self, agent, **kwargs):
        output_text = (
            '{"mode":"coding_handoff","handoff":{'
            '"title":"Implement requested main-chain change",'
            '"body":"## Summary\\nDrive the request through the Ralph workflow.\\n\\nAcceptance criteria:\\n- implement the requested change\\n- add or update tests\\n",'
            '"labels":["agent:main","agent:ralph","workflow:sleep-coding"],'
            '"acceptance":["Implement the requested change.","Add or update tests for the changed behavior."],'
            '"constraints":["Keep the implementation scoped to the requested change."],'
            '"next_owner_agent":"ralph"'
            "}}"
        )
        return type(
            "LLMResponseStub",
            (),
            {
                "output_text": output_text,
                "usage": TokenUsage(
                    prompt_tokens=18,
                    completion_tokens=12,
                    total_tokens=30,
                    provider="openai",
                    model_name="gpt-4.1-mini",
                    cost_usd=0.001,
                ),
            },
        )()


class FakeReviewSkillService:
    def run(self, source, context: str) -> ReviewSkillRunResult:  # noqa: ANN001
        return ReviewSkillRunResult(
            output=ReviewSkillOutput(
                summary="Review for sleep_coding_task",
                findings=[
                    ReviewFinding(
                        severity="P2",
                        title="Minor issue only",
                        detail="No blocking findings.",
                        file_path="tests/example_test.py",
                        line=1,
                    )
                ],
                repair_strategy=["No repair loop required."],
                blocking=False,
                run_mode="dry_run",
                review_markdown=f"## Review\n\nSource: sleep_coding_task\n\n{context}",
            ),
            token_usage=TokenUsage(
                prompt_tokens=12,
                completion_tokens=6,
                total_tokens=18,
                cost_usd=0.001,
                step_name="code_review",
            ),
        )


class BlockingThenPassingReviewSkillService:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, source, context: str) -> ReviewSkillRunResult:  # noqa: ANN001
        self.calls += 1
        blocking = self.calls == 1
        return ReviewSkillRunResult(
            output=ReviewSkillOutput(
                summary="Blocking change requested" if blocking else "Approved after repair",
                findings=[
                    ReviewFinding(
                        severity="P1" if blocking else "P2",
                        title="Repair required" if blocking else "Minor note",
                        detail="First pass requests repair." if blocking else "Repair loop is complete.",
                        file_path="tests/example_test.py",
                        line=1,
                    )
                ],
                repair_strategy=["Apply the requested repair and rerun validation."],
                blocking=blocking,
                run_mode="dry_run",
                review_markdown=f"## Review\n\nSource: sleep_coding_task\n\n{context}",
            ),
            token_usage=TokenUsage(
                prompt_tokens=12,
                completion_tokens=6,
                total_tokens=18,
                cost_usd=0.001,
                step_name="code_review",
            ),
        )


def build_settings(database_path: Path) -> Settings:
    models_config_path = database_path.parent / "models.json"
    if not models_config_path.exists():
        models_config_path.write_text("{}", encoding="utf-8")
    return Settings(
        app_env="test",
        database_url=f"sqlite:///{database_path}",
        review_runs_dir=str(database_path.parent / "review-runs"),
        github_repository="tiezhuli001/youmeng-gateway",
        platform_config_path=str(database_path.parent / "platform.json"),
        models_config_path=str(models_config_path),
        sleep_coding_worker_auto_approve_plan=True,
        openai_api_key="test-key",
        minimax_api_key=None,
        feishu_verification_token="token-1",
        feishu_encrypt_key="encrypt-key",
        langsmith_tracing=False,
    )


def build_sleep_coding_service(
    *,
    settings: Settings,
    channel: FakeChannelService,
    ledger: TokenLedgerService,
    github_mcp: MCPClient,
) -> SleepCodingService:
    return SleepCodingService(
        settings=settings,
        channel=channel,
        git_workspace=FakeGitWorkspaceService(),
        validator=FakeValidationRunner(),
        ledger=ledger,
        agent_runtime=FakeRalphAgentRuntime(),
        mcp_client=github_mcp,
    )


def build_main_agent_service(
    *,
    settings: Settings,
    channel: FakeChannelService,
    ledger: TokenLedgerService,
    github_mcp: MCPClient,
) -> MainAgentService:
    return MainAgentService(
        settings,
        channel=channel,
        ledger=ledger,
        mcp_client=github_mcp,
        agent_runtime=FakeMainAgentRuntime(github_mcp),
    )


class MVPE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        from app.core.config import get_settings

        get_settings.cache_clear()
        get_gateway_control_plane_service.cache_clear()
        get_automation_service.cache_clear()
        get_feishu_webhook_service.cache_clear()
        get_review_service.cache_clear()
        get_sleep_coding_service.cache_clear()

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        from app.core.config import get_settings

        get_settings.cache_clear()
        get_gateway_control_plane_service.cache_clear()
        get_automation_service.cache_clear()
        get_feishu_webhook_service.cache_clear()
        get_review_service.cache_clear()
        get_sleep_coding_service.cache_clear()

    def test_public_api_exposes_typed_main_chain_schema_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "mvp-api-surface.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            ledger = TokenLedgerService(settings)
            github_mcp = build_github_mcp(github)
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                ledger=ledger,
                github_mcp=github_mcp,
            )
            worker = SleepCodingWorkerService(
                settings=settings,
                sleep_coding=sleep_coding,
                mcp_client=github_mcp,
            )
            review = ReviewService(
                settings=settings,
                sleep_coding=sleep_coding,
                skill=FakeReviewSkillService(),
                mcp_client=github_mcp,
            )
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=review,
                worker=worker,
                channel=channel,
                ledger=ledger,
                background_jobs=ImmediateBackgroundJobs(),
            )
            main_agent = build_main_agent_service(
                settings=settings,
                channel=channel,
                ledger=ledger,
                github_mcp=github_mcp,
            )
            control_plane = GatewayControlPlaneService(
                settings=settings,
                ledger=ledger,
                main_agent=main_agent,
                sleep_coding=sleep_coding,
            )

            app.dependency_overrides[get_gateway_control_plane_service] = lambda: control_plane
            app.dependency_overrides[get_automation_service] = lambda: automation
            app.dependency_overrides[get_main_agent_service] = lambda: main_agent
            app.dependency_overrides[get_sleep_coding_service] = lambda: sleep_coding
            app.dependency_overrides[get_review_service] = lambda: review
            app.dependency_overrides[get_task_registry_service] = lambda: main_agent.tasks

            with TestClient(app) as client:
                intake_response = client.post(
                    "/main-agent/intake",
                    json={
                        "user_id": "user-1",
                        "content": "请创建一个 issue，并进入开发流程：补一条主链路 API schema 回归测试。",
                        "source": "manual",
                    },
                )
                self.assertEqual(intake_response.status_code, 200)
                intake_payload = intake_response.json()

                self.assertEqual(intake_payload["mode"], "coding_handoff")
                self.assertEqual(intake_payload["handoff"]["next_owner_agent"], "ralph")
                self.assertIn("acceptance", intake_payload["handoff"])
                self.assertIn("constraints", intake_payload["handoff"])

                parent_task_response = client.get(f"/control/tasks/{intake_payload['control_task_id']}")
                self.assertEqual(parent_task_response.status_code, 200)
                parent_task_payload = parent_task_response.json()

                self.assertEqual(parent_task_payload["handoff"]["next_owner_agent"], "ralph")
                self.assertEqual(parent_task_payload["handoff"]["title"], intake_payload["handoff"]["title"])

                poll_response = client.post(
                    "/workers/sleep-coding/poll",
                    json={"auto_approve_plan": True},
                )
                self.assertEqual(poll_response.status_code, 200)
                poll_payload = poll_response.json()
                task_id = poll_payload["tasks"][0]["task_id"]
                task = sleep_coding.get_task(task_id)
                reviews = review.list_task_reviews(task_id)

                sleep_task_response = client.get(f"/control/tasks/{task.control_task_id}")
                self.assertEqual(sleep_task_response.status_code, 200)
                sleep_task_payload = sleep_task_response.json()

                self.assertIn("coding_artifact", sleep_task_payload)
                self.assertIn("review_handoff", sleep_task_payload)
                self.assertIn("commit_message", sleep_task_payload["coding_artifact"])
                self.assertEqual(
                    sleep_task_payload["review_handoff"]["next_owner_agent"],
                    "code-review-agent",
                )
                self.assertEqual(sleep_task_payload["review_handoff"]["task_id"], task.task_id)

                review_task_response = client.get(f"/control/tasks/{reviews[0].control_task_id}")
                self.assertEqual(review_task_response.status_code, 200)
                review_task_payload = review_task_response.json()

                self.assertIn("machine_output", review_task_payload)
                self.assertIn("human_output", review_task_payload)
                self.assertIn("blocking", review_task_payload["machine_output"])
                self.assertIn("severity_counts", review_task_payload["machine_output"])
                self.assertIn("summary", review_task_payload["human_output"])
                self.assertIn("review_markdown", review_task_payload["human_output"])

    def test_main_agent_to_worker_to_review_to_final_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "mvp-e2e.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            ledger = TokenLedgerService(settings)
            github_mcp = build_github_mcp(github)
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                ledger=ledger,
                github_mcp=github_mcp,
            )
            worker = SleepCodingWorkerService(
                settings=settings,
                sleep_coding=sleep_coding,
                mcp_client=github_mcp,
            )
            review = ReviewService(
                settings=settings,
                sleep_coding=sleep_coding,
                skill=FakeReviewSkillService(),
                mcp_client=github_mcp,
            )
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=review,
                worker=worker,
                channel=channel,
                ledger=ledger,
                background_jobs=ImmediateBackgroundJobs(),
            )
            main_agent = build_main_agent_service(
                settings=settings,
                channel=channel,
                ledger=ledger,
                github_mcp=github_mcp,
            )

            intake = main_agent.intake(
                MainAgentIntakeRequest(
                    user_id="user-1",
                    content="把这个需求转成 issue 并进入 sleep coding 闭环",
                    source="manual",
                )
            )
            poll = automation.process_worker_poll_async(
                SleepCodingWorkerPollRequest(auto_approve_plan=True)
            )

            self.assertEqual(poll.claimed_count, 1)
            task_id = poll.tasks[0].task_id
            task = sleep_coding.get_task(task_id)
            reviews = review.list_task_reviews(task_id)
            parent_task = main_agent.tasks.get_task(intake.control_task_id)
            parent_events = main_agent.tasks.list_events(parent_task.task_id)
            child_task = main_agent.tasks.get_task(task.control_task_id)
            child_events = main_agent.tasks.list_events(child_task.task_id)
            review_task = main_agent.tasks.get_task(reviews[0].control_task_id)
            review_events = main_agent.tasks.list_events(review_task.task_id)
            user_session = main_agent.sessions.get_session(parent_task.payload["user_session_id"])

            self.assertEqual(task.status, "approved")
            self.assertEqual(task.background_follow_up_status, "completed")
            self.assertEqual(task.kickoff_request_id, parent_task.payload["request_id"])
            self.assertEqual(len(reviews), 1)
            self.assertEqual(reviews[0].status, "approved")
            self.assertEqual(child_task.payload["owner_agent"], "ralph")
            self.assertEqual(child_task.payload["source_agent"], "main-agent")
            self.assertEqual(child_task.payload["handoff"]["owner_agent"], "ralph")
            self.assertEqual(child_task.payload["handoff"]["status"], "claimed")
            self.assertEqual(review_task.payload["owner_agent"], "code-review-agent")
            self.assertEqual(review_task.payload["source_agent"], "ralph")
            self.assertEqual(review_task.payload["handoff"]["owner_agent"], "code-review-agent")
            self.assertEqual(review_task.payload["handoff"]["status"], "in_review")
            self.assertEqual(review_task.payload["review_decision"], "approved")
            self.assertIsNone(review_task.payload["next_owner_agent"])
            self.assertEqual(parent_task.payload["final_evidence"]["task_status"], "approved")
            self.assertEqual(parent_task.payload["final_evidence"]["review_status"], "approved")
            self.assertEqual(parent_task.payload["final_evidence"]["validation_status"], "passed")
            self.assertEqual(user_session.payload["active_agent"], "main-agent")
            self.assertGreater(task.token_usage.total_tokens, 0)
            self.assertTrue(any("Review round 1" in title for title, _, _ in channel.notifications))
            issue_notifications = [
                lines for title, lines, _ in channel.notifications if "Ralph 任务开始" in title
            ]
            self.assertTrue(issue_notifications)
            self.assertTrue(any(any(line.startswith("任务摘要:") for line in lines) for lines in issue_notifications))
            self.assertTrue(any("任务完成" in title for title, _, _ in channel.notifications))
            self.assertTrue(github.pr_comments)
            self.assertIn("## Ralph Review Decision", github.pr_comments[-1][1])
            self.assertIn("- Decision: Approved", github.pr_comments[-1][1])
            self.assertTrue(any(event.event_type == "child_completed" for event in parent_events))
            self.assertTrue(
                any(event.event_type == "child.follow_up.completed" for event in parent_events)
            )
            self.assertTrue(any(event.event_type == "handoff_to_ralph" for event in parent_events))
            self.assertTrue(
                any(event.event_type == "follow_up.completed" for event in child_events)
            )
            self.assertTrue(any(event.event_type == "handoff_to_code_review" for event in child_events))
            self.assertTrue(any(event.event_type == "review_returned" for event in child_events))
            self.assertTrue(any(event.event_type == "review_approved" for event in review_events))

    def test_main_agent_intake_request_repo_round_trips_through_public_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "mvp-e2e-request-repo.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            ledger = TokenLedgerService(settings)
            github_mcp = build_github_mcp(github)
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                ledger=ledger,
                github_mcp=github_mcp,
            )
            worker = SleepCodingWorkerService(
                settings=settings,
                sleep_coding=sleep_coding,
                mcp_client=github_mcp,
            )
            review = ReviewService(
                settings=settings,
                sleep_coding=sleep_coding,
                skill=FakeReviewSkillService(),
                mcp_client=github_mcp,
            )
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=review,
                worker=worker,
                channel=channel,
                ledger=ledger,
                background_jobs=ImmediateBackgroundJobs(),
            )
            main_agent = build_main_agent_service(
                settings=settings,
                channel=channel,
                ledger=ledger,
                github_mcp=github_mcp,
            )
            control_plane = GatewayControlPlaneService(
                settings=settings,
                ledger=ledger,
                main_agent=main_agent,
                sleep_coding=sleep_coding,
            )

            app.dependency_overrides[get_settings] = lambda: settings
            app.dependency_overrides[get_gateway_control_plane_service] = lambda: control_plane
            app.dependency_overrides[get_automation_service] = lambda: automation
            app.dependency_overrides[get_main_agent_service] = lambda: main_agent
            app.dependency_overrides[get_sleep_coding_service] = lambda: sleep_coding
            app.dependency_overrides[get_review_service] = lambda: review
            app.dependency_overrides[get_task_registry_service] = lambda: main_agent.tasks

            with TestClient(app) as client:
                intake_response = client.post(
                    "/main-agent/intake",
                    json={
                        "user_id": "user-1",
                        "content": "请修复 repo continuity，并进入开发流程。",
                        "source": "manual",
                        "repo": "acme/platform-repo",
                    },
                )
                self.assertEqual(intake_response.status_code, 200)
                intake_payload = intake_response.json()
                self.assertEqual(intake_payload["handoff"]["repo"], "acme/platform-repo")
                self.assertEqual(
                    intake_payload["issue"]["html_url"],
                    "https://github.com/acme/platform-repo/issues/101",
                )

                parent_task_response = client.get(f"/control/tasks/{intake_payload['control_task_id']}")
                self.assertEqual(parent_task_response.status_code, 200)
                parent_task_payload = parent_task_response.json()
                self.assertEqual(parent_task_payload["repo"], "acme/platform-repo")
                self.assertEqual(parent_task_payload["handoff"]["repo"], "acme/platform-repo")

    def test_gateway_api_reports_queued_state_when_single_flight_lane_is_busy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "mvp-e2e-single-flight.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            ledger = TokenLedgerService(settings)
            github_mcp = build_github_mcp(github)
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                ledger=ledger,
                github_mcp=github_mcp,
            )
            main_agent = build_main_agent_service(
                settings=settings,
                channel=channel,
                ledger=ledger,
                github_mcp=github_mcp,
            )
            control_plane = GatewayControlPlaneService(
                settings=settings,
                ledger=ledger,
                main_agent=main_agent,
                sleep_coding=sleep_coding,
            )

            app.dependency_overrides[get_settings] = lambda: settings
            app.dependency_overrides[get_gateway_control_plane_service] = lambda: control_plane
            app.dependency_overrides[get_main_agent_service] = lambda: main_agent
            app.dependency_overrides[get_sleep_coding_service] = lambda: sleep_coding
            app.dependency_overrides[get_task_registry_service] = lambda: main_agent.tasks

            with TestClient(app) as client:
                first = client.post(
                    "/gateway/message",
                    json={
                        "user_id": "user-1",
                        "content": "请实现第一个 coding 请求。",
                        "source": "manual",
                    },
                )
                self.assertEqual(first.status_code, 200)
                first_payload = first.json()
                self.assertEqual(first_payload["workflow_state"], "accepted")

                second = client.post(
                    "/gateway/message",
                    json={
                        "user_id": "user-2",
                        "content": "请实现第二个 coding 请求。",
                        "source": "manual",
                    },
                )
                self.assertEqual(second.status_code, 200)
                second_payload = second.json()
                self.assertEqual(second_payload["workflow_state"], "queued")
                self.assertEqual(second_payload["active_task_id"], first_payload["task_id"])

                queued_task = client.get(f"/control/tasks/{second_payload['task_id']}")
                self.assertEqual(queued_task.status_code, 200)
                queued_payload = queued_task.json()
                self.assertEqual(queued_payload["payload"]["queue_status"], "queued")
                self.assertEqual(queued_payload["payload"]["active_task_id"], first_payload["task_id"])

    def test_custom_repo_continues_from_intake_to_worker_review_and_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "mvp-e2e-custom-repo.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            ledger = TokenLedgerService(settings)
            github_mcp = build_github_mcp(github)
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                ledger=ledger,
                github_mcp=github_mcp,
            )
            worker = SleepCodingWorkerService(
                settings=settings,
                sleep_coding=sleep_coding,
                mcp_client=github_mcp,
            )
            review = ReviewService(
                settings=settings,
                sleep_coding=sleep_coding,
                skill=FakeReviewSkillService(),
                mcp_client=github_mcp,
            )
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=review,
                worker=worker,
                channel=channel,
                ledger=ledger,
                background_jobs=ImmediateBackgroundJobs(),
            )
            main_agent = build_main_agent_service(
                settings=settings,
                channel=channel,
                ledger=ledger,
                github_mcp=github_mcp,
            )

            intake = main_agent.intake(
                MainAgentIntakeRequest(
                    user_id="user-1",
                    content="请修复 custom repo continuity，并进入开发流程。",
                    source="manual",
                    repo="acme/platform-repo",
                )
            )

            poll = automation.process_worker_poll_async(
                SleepCodingWorkerPollRequest(auto_approve_plan=True)
            )

            self.assertEqual(poll.claimed_count, 1)
            task = poll.tasks[0]
            reviews = review.list_task_reviews(task.task_id)
            parent_task = main_agent.tasks.get_task(intake.control_task_id)
            final_title, final_lines, _ = channel.notifications[-1]

            self.assertEqual(task.repo, "acme/platform-repo")
            self.assertEqual(task.issue.html_url, "https://github.com/acme/platform-repo/issues/101")
            self.assertIsNotNone(task.pull_request)
            self.assertTrue(task.pull_request.html_url.startswith("https://github.com/acme/platform-repo/pull/"))
            self.assertEqual(reviews[0].target.repo, "acme/platform-repo")
            self.assertEqual(parent_task.repo, "acme/platform-repo")
            self.assertIn("任务完成", final_title)
            self.assertIn("仓库: acme/platform-repo", final_lines)

    def test_operator_state_endpoint_reports_active_and_queued_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "mvp-e2e-operator-state.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            ledger = TokenLedgerService(settings)
            github_mcp = build_github_mcp(github)
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                ledger=ledger,
                github_mcp=github_mcp,
            )
            main_agent = build_main_agent_service(
                settings=settings,
                channel=channel,
                ledger=ledger,
                github_mcp=github_mcp,
            )
            control_plane = GatewayControlPlaneService(
                settings=settings,
                ledger=ledger,
                main_agent=main_agent,
                sleep_coding=sleep_coding,
            )

            app.dependency_overrides[get_gateway_control_plane_service] = lambda: control_plane
            app.dependency_overrides[get_task_registry_service] = lambda: main_agent.tasks
            app.dependency_overrides[get_session_registry_service] = lambda: control_plane.sessions

            try:
                with TestClient(app) as client:
                    first = client.post(
                        "/gateway/message",
                        json={
                            "user_id": "user-1",
                            "content": "请实现第一个 coding 请求。",
                            "source": "manual",
                        },
                    )
                    second = client.post(
                        "/gateway/message",
                        json={
                            "user_id": "user-2",
                            "content": "请实现第二个 coding 请求。",
                            "source": "manual",
                        },
                    )
                    self.assertEqual(first.status_code, 200)
                    self.assertEqual(second.status_code, 200)
                    operator_state = client.get("/control/operator/state")
            finally:
                app.dependency_overrides.pop(get_gateway_control_plane_service, None)
                app.dependency_overrides.pop(get_task_registry_service, None)
                app.dependency_overrides.pop(get_session_registry_service, None)

            self.assertEqual(operator_state.status_code, 200)
            payload = operator_state.json()
            self.assertEqual(payload["lane"]["active_task_id"], first.json()["task_id"])
            self.assertEqual(payload["lane"]["queued_task_ids"], [second.json()["task_id"]])
            self.assertEqual(payload["active_task"]["task_id"], first.json()["task_id"])
            self.assertEqual(payload["queued_tasks"][0]["task_id"], second.json()["task_id"])

    def test_pipeline_stops_when_execution_truth_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "mvp-e2e-missing-truth.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            ledger = TokenLedgerService(settings)
            github_mcp = build_github_mcp(github)
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                ledger=ledger,
                github_mcp=github_mcp,
            )
            review = ReviewService(
                settings=settings,
                sleep_coding=sleep_coding,
                skill=FakeReviewSkillService(),
                mcp_client=github_mcp,
            )
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=review,
                channel=channel,
                ledger=ledger,
                background_jobs=ImmediateBackgroundJobs(),
            )

            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=57))
            task = sleep_coding.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )
            with sleep_coding._connect() as connection:
                sleep_coding.store.update_task_payloads(
                    connection,
                    task.task_id,
                    status="in_review",
                    git_execution=GitExecutionResult(
                        status="prepared",
                        worktree_path=task.git_execution.worktree_path,
                        artifact_path=task.git_execution.artifact_path,
                        output="artifact ready",
                        is_dry_run=True,
                        changed_files=[],
                        file_changes=[],
                        diff_summary="",
                        diff_excerpt="",
                    ),
                )
                connection.commit()

            with self.assertRaisesRegex(ValueError, "execution evidence"):
                automation.run_review_loop(task.task_id)

            control_task = sleep_coding.tasks.get_task(task.control_task_id)
            self.assertEqual(control_task.status, "in_review")
            self.assertNotIn("final_evidence", control_task.payload)
            self.assertFalse(any("任务完成" in title for title, _, _ in channel.notifications))

    def test_existing_issue_to_worker_to_review_to_final_delivery_without_duplicate_issue_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "mvp-e2e-existing-issue.db")
            github = FakeGitHubService()
            github.issues[56] = SleepCodingIssue(
                issue_number=56,
                title="Implement local-first review loop",
                body=(
                    "Use the existing GitHub issue as the source of truth.\n\n"
                    "Acceptance criteria:\n"
                    "- worker polls the issue once\n"
                    "- Ralph codes in a local worktree\n"
                    "- review runs locally before final writeback\n"
                ),
                html_url="https://github.com/tiezhuli001/youmeng-gateway/issues/56",
                labels=["agent:ralph", "workflow:sleep-coding"],
                is_dry_run=True,
            )
            channel = FakeChannelService()
            ledger = TokenLedgerService(settings)
            github_mcp = build_github_mcp(github)
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                ledger=ledger,
                github_mcp=github_mcp,
            )
            worker = SleepCodingWorkerService(
                settings=settings,
                sleep_coding=sleep_coding,
                mcp_client=github_mcp,
            )
            review = ReviewService(
                settings=settings,
                sleep_coding=sleep_coding,
                skill=FakeReviewSkillService(),
                mcp_client=github_mcp,
            )
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=review,
                worker=worker,
                channel=channel,
                ledger=ledger,
                background_jobs=ImmediateBackgroundJobs(),
            )

            poll = automation.process_worker_poll_async(
                SleepCodingWorkerPollRequest(auto_approve_plan=True)
            )

            self.assertEqual(poll.claimed_count, 1)
            self.assertEqual(len(github.issues), 1)
            self.assertEqual(github.create_issue_calls, 0)

            task_id = poll.tasks[0].task_id
            task = sleep_coding.get_task(task_id)
            reviews = review.list_task_reviews(task_id)

            self.assertEqual(task.issue_number, 56)
            self.assertEqual(task.status, "approved")
            self.assertEqual(task.background_follow_up_status, "completed")
            self.assertEqual(len(reviews), 1)
            self.assertEqual(reviews[0].status, "approved")
            self.assertTrue(any("Review round 1" in title for title, _, _ in channel.notifications))
            self.assertTrue(github.pr_comments)
            self.assertIn("## Ralph Review Decision", github.pr_comments[-1][1])
            self.assertTrue(any("任务完成" in title for title, _, _ in channel.notifications))

    def test_main_chain_handles_review_changes_requested_then_repair_resume_to_final_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "mvp-e2e-repair-loop.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            ledger = TokenLedgerService(settings)
            github_mcp = build_github_mcp(github)
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                ledger=ledger,
                github_mcp=github_mcp,
            )
            worker = SleepCodingWorkerService(
                settings=settings,
                sleep_coding=sleep_coding,
                mcp_client=github_mcp,
            )
            review_skill = BlockingThenPassingReviewSkillService()
            review = ReviewService(
                settings=settings,
                sleep_coding=sleep_coding,
                skill=review_skill,
                mcp_client=github_mcp,
            )
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=review,
                worker=worker,
                channel=channel,
                ledger=ledger,
                background_jobs=ImmediateBackgroundJobs(),
            )
            main_agent = build_main_agent_service(
                settings=settings,
                channel=channel,
                ledger=ledger,
                github_mcp=github_mcp,
            )

            intake = main_agent.intake(
                MainAgentIntakeRequest(
                    user_id="user-repair",
                    content="把这个需求转成 issue 并跑完整 repair loop",
                    source="manual",
                )
            )
            poll = automation.process_worker_poll_async(
                SleepCodingWorkerPollRequest(auto_approve_plan=True)
            )

            self.assertEqual(poll.claimed_count, 1)
            task_id = poll.tasks[0].task_id
            task = sleep_coding.get_task(task_id)
            reviews = review.list_task_reviews(task_id)
            parent_task = main_agent.tasks.get_task(intake.control_task_id)
            parent_events = main_agent.tasks.list_events(parent_task.task_id)
            child_task = main_agent.tasks.get_task(task.control_task_id)
            child_events = main_agent.tasks.list_events(child_task.task_id)

            self.assertEqual(task.status, "approved")
            self.assertEqual(task.background_follow_up_status, "completed")
            self.assertEqual(len(reviews), 2)
            self.assertEqual({item.status for item in reviews}, {"changes_requested", "approved"})
            self.assertEqual(review_skill.calls, 2)
            self.assertEqual(parent_task.status, "completed")
            self.assertEqual(parent_task.payload["latest_review_status"], "approved")
            self.assertEqual(parent_task.payload["review_round"], 2)
            self.assertEqual(parent_task.payload["delivery_status"], "degraded")
            self.assertFalse(parent_task.payload["delivery_delivered"])
            self.assertEqual(parent_task.payload["final_evidence"]["review_status"], "approved")
            self.assertEqual(parent_task.payload["terminal_evidence"]["terminal_state"], "completed")
            self.assertTrue(any(event.event_type == "review_returned" for event in child_events))
            self.assertTrue(any(event.event_type == "child_completed" for event in parent_events))
            self.assertTrue(any("Review round 1" in title for title, _, _ in channel.notifications))
            self.assertTrue(any("Review round 2" in title for title, _, _ in channel.notifications))
            self.assertTrue(any("任务完成" in title for title, _, _ in channel.notifications))

    def test_gateway_api_to_worker_to_final_delivery_keeps_single_request_usage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "platform.json").write_text(
                (
                    '{'
                    '"github":{"repository":"tiezhuli001/youmeng-gateway"},'
                    '"channel":{"provider":"feishu"},'
                    '"sleep_coding":{"worker":{"auto_approve_plan":true,"scheduler_enabled":false}}'
                    '}'
                ),
                encoding="utf-8",
            )
            settings = build_settings(Path(temp_dir) / "mvp-e2e-api.db")
            os.environ["APP_ENV"] = settings.app_env
            os.environ["DATABASE_URL"] = settings.database_url
            os.environ["REVIEW_RUNS_DIR"] = settings.review_runs_dir
            os.environ["PLATFORM_CONFIG_PATH"] = settings.platform_config_path
            github = FakeGitHubService()
            channel = FakeChannelService()
            ledger = TokenLedgerService(settings)
            github_mcp = build_github_mcp(github)
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                ledger=ledger,
                github_mcp=github_mcp,
            )
            worker = SleepCodingWorkerService(
                settings=settings,
                sleep_coding=sleep_coding,
                mcp_client=github_mcp,
            )
            review = ReviewService(
                settings=settings,
                sleep_coding=sleep_coding,
                skill=FakeReviewSkillService(),
                mcp_client=github_mcp,
            )
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=review,
                worker=worker,
                channel=channel,
                ledger=ledger,
                background_jobs=ImmediateBackgroundJobs(),
            )
            main_agent = build_main_agent_service(
                settings=settings,
                channel=channel,
                ledger=ledger,
                github_mcp=github_mcp,
            )
            control_plane = GatewayControlPlaneService(
                settings=settings,
                ledger=ledger,
                main_agent=main_agent,
                sleep_coding=sleep_coding,
            )

            app.dependency_overrides[get_gateway_control_plane_service] = lambda: control_plane
            app.dependency_overrides[get_automation_service] = lambda: automation
            app.dependency_overrides[get_sleep_coding_service] = lambda: sleep_coding
            app.dependency_overrides[get_review_service] = lambda: review

            with TestClient(app) as client:
                gateway_response = client.post(
                    "/gateway/message",
                    json={
                        "user_id": "user-1",
                        "content": "请把这个需求整理清楚，并进入开发流程",
                        "source": "manual",
                    },
                )
                self.assertEqual(gateway_response.status_code, 200)
                gateway_payload = gateway_response.json()

                poll_response = client.post(
                    "/workers/sleep-coding/poll",
                    json={"auto_approve_plan": True},
                )
                self.assertEqual(poll_response.status_code, 200)
                poll_payload = poll_response.json()
                task_response = client.get(f"/tasks/sleep-coding/{poll_payload['tasks'][0]['task_id']}")
                self.assertEqual(task_response.status_code, 200)
                task_payload = task_response.json()

            self.assertEqual(poll_payload["claimed_count"], 1)
            task_id = poll_payload["tasks"][0]["task_id"]
            task = sleep_coding.get_task(task_id)
            reviews = review.list_task_reviews(task_id)

            self.assertEqual(task.status, "approved")
            self.assertEqual(task.kickoff_request_id, gateway_payload["request_id"])
            self.assertEqual(gateway_payload["token_usage"]["step_name"], "main_agent_issue_intake")
            self.assertEqual(len(reviews), 1)
            self.assertEqual(reviews[0].status, "approved")

            total_usage = ledger.get_request_usage(task.kickoff_request_id)
            plan_usage = ledger.get_request_usage(task.kickoff_request_id, ["sleep_coding_plan"])
            execution_usage = ledger.get_request_usage(task.kickoff_request_id, ["sleep_coding_execution"])
            review_usage = ledger.get_request_usage(task.kickoff_request_id, ["code_review"])

            self.assertEqual(total_usage.total_tokens, task.token_usage.total_tokens)
            self.assertEqual(task_payload["token_usage"]["total_tokens"], total_usage.total_tokens)
            self.assertIsNone(task_payload["token_usage"]["step_name"])
            self.assertEqual(task_payload["kickoff_request_id"], gateway_payload["request_id"])
            self.assertEqual(
                total_usage.total_tokens,
                gateway_payload["token_usage"]["total_tokens"]
                + plan_usage.total_tokens
                + execution_usage.total_tokens
                + review_usage.total_tokens,
            )
            self.assertAlmostEqual(
                total_usage.cost_usd,
                gateway_payload["token_usage"]["cost_usd"]
                + plan_usage.cost_usd
                + execution_usage.cost_usd
                + review_usage.cost_usd,
                places=5,
            )

            review_response = client.get(f"/reviews/{reviews[0].review_id}")
            self.assertEqual(review_response.status_code, 200)
            review_payload = review_response.json()
            self.assertEqual(review_payload["token_usage"]["total_tokens"], review_usage.total_tokens)
            self.assertEqual(review_payload["token_usage"]["step_name"], "code_review")

            final_title, final_lines, _ = channel.notifications[-1]
            self.assertIn("任务完成", final_title)
            self.assertTrue(any("Ralph 任务开始" in title for title, _, _ in channel.notifications))
            self.assertTrue(any("Ralph 执行计划" in title for title, _, _ in channel.notifications))
            self.assertTrue(any("Review round 1" in title for title, _, _ in channel.notifications))
            self.assertNotIn(
                "ready for confirmation",
                "\n".join(title for title, _, _ in channel.notifications),
            )
            self.assertIn("工作总结:", final_lines)
            self.assertIn("一、修改文件清单", final_lines)
            self.assertIn("二、关键变更说明", final_lines)
            self.assertIn("四、总结", final_lines)
            self.assertIn(f"输入 Token: {total_usage.prompt_tokens:,}", final_lines)
            self.assertIn(f"输出 Token: {total_usage.completion_tokens:,}", final_lines)
            self.assertIn(f"总 Token: {total_usage.total_tokens:,}", final_lines)
            self.assertIn(f"缓存读取 Token: {total_usage.cache_read_tokens:,}", final_lines)
            self.assertIn(f"推理 Token: {total_usage.reasoning_tokens:,}", final_lines)
            self.assertIn(f"总成本: ${total_usage.cost_usd:.3f}", final_lines)
            self.assertIn(
                f"Plan: 输入 {plan_usage.prompt_tokens:,} · 输出 {plan_usage.completion_tokens:,} · 总 {plan_usage.total_tokens:,} · 成本 ${plan_usage.cost_usd:.3f}",
                final_lines,
            )
            self.assertIn(
                f"Execution: 输入 {execution_usage.prompt_tokens:,} · 输出 {execution_usage.completion_tokens:,} · 总 {execution_usage.total_tokens:,} · 成本 ${execution_usage.cost_usd:.3f}",
                final_lines,
            )
            self.assertIn(
                f"Review: 输入 {review_usage.prompt_tokens:,} · 输出 {review_usage.completion_tokens:,} · 总 {review_usage.total_tokens:,} · 成本 ${review_usage.cost_usd:.3f}",
                final_lines,
            )
            self.assertTrue(github.pr_comments)
            self.assertIn("## Ralph Review Decision", github.pr_comments[-1][1])
            self.assertIn("- Decision: Approved", github.pr_comments[-1][1])
            self.assertIn("### Token Usage", github.pr_comments[-1][1])

    def test_direct_write_endpoints_are_removed_from_public_api(self) -> None:
        with TestClient(app) as client:
            self.assertEqual(client.post("/tasks/sleep-coding", json={"issue_number": 1}).status_code, 404)
            self.assertEqual(
                client.post("/tasks/sleep-coding/task-1/actions", json={"action": "approve_plan"}).status_code,
                404,
            )
            self.assertEqual(client.post("/reviews", json={"task_id": "task-1"}).status_code, 404)
            self.assertEqual(
                client.post("/reviews/review-1/actions", json={"action": "approve_review"}).status_code,
                404,
            )
            self.assertEqual(client.post("/tasks/sleep-coding/task-1/review").status_code, 404)

    def test_feishu_inbound_to_final_delivery_runs_full_mvp_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "platform.json").write_text(
                (
                    '{'
                    '"github":{"repository":"tiezhuli001/youmeng-gateway"},'
                    '"channel":{"provider":"feishu"},'
                    '"sleep_coding":{"worker":{"auto_approve_plan":true,"scheduler_enabled":false}}'
                    '}'
                ),
                encoding="utf-8",
            )
            settings = build_settings(Path(temp_dir) / "mvp-e2e-feishu.db")
            os.environ["APP_ENV"] = settings.app_env
            os.environ["DATABASE_URL"] = settings.database_url
            os.environ["REVIEW_RUNS_DIR"] = settings.review_runs_dir
            os.environ["PLATFORM_CONFIG_PATH"] = settings.platform_config_path
            github = FakeGitHubService()
            channel = FakeChannelService()
            ledger = TokenLedgerService(settings)
            github_mcp = build_github_mcp(github)
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                ledger=ledger,
                github_mcp=github_mcp,
            )
            worker = SleepCodingWorkerService(
                settings=settings,
                sleep_coding=sleep_coding,
                mcp_client=github_mcp,
            )
            review = ReviewService(
                settings=settings,
                sleep_coding=sleep_coding,
                skill=FakeReviewSkillService(),
                mcp_client=github_mcp,
            )
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=review,
                worker=worker,
                channel=channel,
                ledger=ledger,
                background_jobs=ImmediateBackgroundJobs(),
            )
            main_agent = build_main_agent_service(
                settings=settings,
                channel=channel,
                ledger=ledger,
                github_mcp=github_mcp,
            )
            control_plane = GatewayControlPlaneService(
                settings=settings,
                ledger=ledger,
                main_agent=main_agent,
                sleep_coding=sleep_coding,
            )
            feishu = FeishuWebhookService(
                settings,
                workflow=GatewayWorkflowService(
                    settings,
                    control_plane=control_plane,
                    automation=automation,
                ),
            )

            app.dependency_overrides[get_gateway_control_plane_service] = lambda: control_plane
            app.dependency_overrides[get_automation_service] = lambda: automation
            app.dependency_overrides[get_sleep_coding_service] = lambda: sleep_coding
            app.dependency_overrides[get_review_service] = lambda: review
            app.dependency_overrides[get_feishu_webhook_service] = lambda: feishu

            payload = {
                "schema": "2.0",
                "header": {"event_type": "im.message.receive_v1"},
                "event": {
                    "sender": {"sender_id": {"open_id": "ou_123"}},
                    "message": {
                        "message_id": "om_123",
                        "chat_id": "oc_123",
                        "message_type": "text",
                        "content": '{"text":"请把这个需求整理清楚，并进入开发流程"}',
                    },
                },
                "token": "token-1",
            }
            raw_body = __import__("json").dumps(payload).encode("utf-8")
            signature = __import__("hashlib").sha256(
                b"1700000000nonce-1encrypt-key" + raw_body
            ).hexdigest()

            with TestClient(app) as client:
                response = client.post(
                    "/webhooks/feishu/events",
                    content=raw_body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Lark-Request-Timestamp": "1700000000",
                        "X-Lark-Request-Nonce": "nonce-1",
                        "X-Lark-Signature": signature,
                    },
                )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["automation_follow_up"]["triggered"])
            self.assertEqual(payload["automation_follow_up"]["mode"], "worker_poll")
            self.assertEqual(payload["automation_follow_up"]["claimed_count"], 1)

            self.assertFalse(
                any("ready for confirmation" in title for title, _, _ in channel.notifications)
            )
            self.assertTrue(any("Ralph 任务开始" in title for title, _, _ in channel.notifications))
            self.assertTrue(any("Ralph 执行计划" in title for title, _, _ in channel.notifications))
            self.assertTrue(any("Review round 1" in title for title, _, _ in channel.notifications))
            self.assertTrue(any("任务完成" in title for title, _, _ in channel.notifications))
            final_title, final_lines, _ = channel.notifications[-1]
            self.assertIn("任务完成", final_title)
            self.assertIn("工作总结:", final_lines)
            self.assertIn("二、关键变更说明", final_lines)
            self.assertIn("三、Token 消耗统计", final_lines)
            self.assertIn("四、总结", final_lines)
            self.assertTrue(any(line.startswith("输入 Token:") for line in final_lines))

            task_id = payload["automation_follow_up"]["task_ids"][0]
            task = sleep_coding.get_task(task_id)
            self.assertEqual(task.status, "approved")
            self.assertEqual(task.background_follow_up_status, "completed")
            self.assertGreater(task.token_usage.total_tokens, 0)
            self.assertTrue(github.pr_comments)
            self.assertIn("## Ralph Review Decision", github.pr_comments[-1][1])

    def test_feishu_stats_then_coding_reuses_session_and_chat_endpoint_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "platform.json").write_text(
                (
                    '{'
                    '"github":{"repository":"tiezhuli001/youmeng-gateway"},'
                    '"channel":{"provider":"feishu","default_endpoint":"fallback-entry","endpoints":{'
                    '"fallback-entry":{"provider":"feishu","mode":"primary","entry_enabled":true,"delivery_enabled":true},'
                    '"chat-entry":{"provider":"feishu","mode":"primary","entry_enabled":true,"delivery_enabled":true,'
                    '"external_refs":["feishu:chat:oc_123"],'
                    '"delivery_policy":{"mode":"fixed_endpoint","endpoint_id":"feishu-delivery"}},'
                    '"feishu-delivery":{"provider":"feishu","mode":"delivery","entry_enabled":false,"delivery_enabled":true}'
                    '}},'
                    '"sleep_coding":{"worker":{"auto_approve_plan":true,"scheduler_enabled":false}}'
                    '}'
                ),
                encoding="utf-8",
            )
            settings = build_settings(Path(temp_dir) / "mvp-e2e-feishu-session.db")
            os.environ["APP_ENV"] = settings.app_env
            os.environ["DATABASE_URL"] = settings.database_url
            os.environ["REVIEW_RUNS_DIR"] = settings.review_runs_dir
            os.environ["PLATFORM_CONFIG_PATH"] = settings.platform_config_path
            github = FakeGitHubService()
            channel = FakeChannelService()
            ledger = TokenLedgerService(settings)
            github_mcp = build_github_mcp(github)
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                ledger=ledger,
                github_mcp=github_mcp,
            )
            worker = SleepCodingWorkerService(
                settings=settings,
                sleep_coding=sleep_coding,
                mcp_client=github_mcp,
            )
            review = ReviewService(
                settings=settings,
                sleep_coding=sleep_coding,
                skill=FakeReviewSkillService(),
                mcp_client=github_mcp,
            )
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=review,
                worker=worker,
                channel=channel,
                ledger=ledger,
                background_jobs=ImmediateBackgroundJobs(),
            )
            main_agent = build_main_agent_service(
                settings=settings,
                channel=channel,
                ledger=ledger,
                github_mcp=github_mcp,
            )
            control_plane = GatewayControlPlaneService(
                settings=settings,
                ledger=ledger,
                main_agent=main_agent,
                sleep_coding=sleep_coding,
            )
            feishu = FeishuWebhookService(
                settings,
                workflow=GatewayWorkflowService(
                    settings,
                    control_plane=control_plane,
                    automation=automation,
                ),
            )

            app.dependency_overrides[get_gateway_control_plane_service] = lambda: control_plane
            app.dependency_overrides[get_automation_service] = lambda: automation
            app.dependency_overrides[get_sleep_coding_service] = lambda: sleep_coding
            app.dependency_overrides[get_review_service] = lambda: review
            app.dependency_overrides[get_feishu_webhook_service] = lambda: feishu

            def _signed_post(client: TestClient, text: str, message_id: str) -> dict[str, object]:
                payload = {
                    "schema": "2.0",
                    "header": {"event_type": "im.message.receive_v1"},
                    "event": {
                        "sender": {"sender_id": {"open_id": "ou_123"}},
                        "message": {
                            "message_id": message_id,
                            "chat_id": "oc_123",
                            "message_type": "text",
                            "content": __import__("json").dumps({"text": text}),
                        },
                    },
                    "token": "token-1",
                }
                raw_body = __import__("json").dumps(payload).encode("utf-8")
                signature = __import__("hashlib").sha256(
                    b"1700000000nonce-1encrypt-key" + raw_body
                ).hexdigest()
                response = client.post(
                    "/webhooks/feishu/events",
                    content=raw_body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Lark-Request-Timestamp": "1700000000",
                        "X-Lark-Request-Nonce": "nonce-1",
                        "X-Lark-Signature": signature,
                    },
                )
                self.assertEqual(response.status_code, 200)
                return response.json()

            with TestClient(app) as client:
                stats_payload = _signed_post(client, "今天 token 用量怎么样？", "om_stats")
                coding_payload = _signed_post(client, "请把这个需求整理清楚，并进入开发流程", "om_coding")

            task = main_agent.tasks.get_task(coding_payload["gateway_response"]["task_id"])
            user_session = main_agent.sessions.get_session(task.payload["user_session_id"])

            self.assertEqual(stats_payload["gateway_response"]["workflow_state"], "completed")
            self.assertEqual(coding_payload["gateway_response"]["workflow_state"], "accepted")
            self.assertEqual(task.payload["source_endpoint_id"], "chat-entry")
            self.assertEqual(task.payload["delivery_endpoint_id"], "feishu-delivery")
            self.assertEqual(user_session.payload["last_task_id"], task.task_id)
            self.assertEqual(user_session.payload["last_workflow_state"], "accepted")


if __name__ == "__main__":
    unittest.main()
