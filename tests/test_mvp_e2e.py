import tempfile
import unittest
import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.routes import (
    get_automation_service,
    get_feishu_webhook_service,
    get_gateway_control_plane_service,
    get_review_service,
    get_sleep_coding_service,
)
from app.control.gateway import GatewayControlPlaneService
from app.control.workflow import GatewayWorkflowService
from app.main import app
from app.core.config import Settings
from app.ledger.service import TokenLedgerService
from app.models.schemas import (
    GitHubIssueDraft,
    GitHubIssueResult,
    MainAgentIntakeRequest,
    ReviewFinding,
    ReviewSkillOutput,
    SleepCodingIssue,
    SleepCodingPullRequest,
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
        openai_api_key=None,
        minimax_api_key=None,
        feishu_verification_token="token-1",
        feishu_encrypt_key="encrypt-key",
        langsmith_tracing=False,
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

    def test_main_agent_to_worker_to_review_to_final_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "mvp-e2e.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            ledger = TokenLedgerService(settings)
            github_mcp = build_github_mcp(github)
            sleep_coding = SleepCodingService(
                settings=settings,
                channel=channel,
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner(),
                ledger=ledger,
                mcp_client=github_mcp,
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
            main_agent = MainAgentService(
                settings,
                channel=channel,
                ledger=ledger,
                mcp_client=github_mcp,
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
            sleep_coding = SleepCodingService(
                settings=settings,
                channel=channel,
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner(),
                ledger=ledger,
                mcp_client=github_mcp,
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
            sleep_coding = SleepCodingService(
                settings=settings,
                channel=channel,
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner(),
                ledger=ledger,
                mcp_client=github_mcp,
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
            main_agent = MainAgentService(
                settings,
                channel=channel,
                ledger=ledger,
                mcp_client=github_mcp,
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
            sleep_coding = SleepCodingService(
                settings=settings,
                channel=channel,
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner(),
                ledger=ledger,
                mcp_client=github_mcp,
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
            main_agent = MainAgentService(
                settings,
                channel=channel,
                ledger=ledger,
                mcp_client=github_mcp,
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


if __name__ == "__main__":
    unittest.main()
