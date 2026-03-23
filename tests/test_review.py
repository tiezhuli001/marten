import tempfile
import unittest
from pathlib import Path
import subprocess
from unittest.mock import patch

from app.agents.code_review_agent import ReviewService, ReviewSkillRunResult, ReviewSkillService
from app.agents.ralph import SleepCodingService
from app.channel.notifications import ChannelNotificationResult
from app.core.config import Settings
from app.ledger.service import TokenLedgerService
from app.models.github_results import GitHubCommentResult
from app.models.schemas import (
    ReviewActionRequest,
    ReviewFinding,
    ReviewHumanOutput,
    ReviewMachineOutput,
    ReviewStartRequest,
    ReviewSkillOutput,
    ReviewTarget,
    SleepCodingIssue,
    SleepCodingPullRequest,
    SleepCodingTaskActionRequest,
    SleepCodingTaskRequest,
    TokenUsage,
    ValidationResult,
)
from app.runtime.mcp import InMemoryMCPServer, MCPClient


class FakeGitHubService:
    def __init__(self) -> None:
        self.issue_comments: list[str] = []
        self.pr_comments: list[str] = []
        self.labels_applied: list[tuple[int, list[str]]] = []

    def get_issue(self, repo, issue_number, title_override=None, body_override=None):
        return SleepCodingIssue(
            issue_number=issue_number,
            title=title_override or "Review integration",
            body=body_override or "Need a review integration test.",
            html_url=f"https://github.com/{repo}/issues/{issue_number}",
            is_dry_run=True,
        )

    def create_issue_comment(self, repo, issue_number, body):
        self.issue_comments.append(body)
        return GitHubCommentResult(
            html_url=f"https://github.com/{repo}/issues/{issue_number}#issuecomment-1",
            is_dry_run=True,
        )

    def create_pull_request(self, repo, issue, plan, validation, head_branch, base_branch):
        return SleepCodingPullRequest(
            title=f"[Ralph] #{issue.issue_number} {issue.title}",
            body="dry run pr",
            html_url=f"https://github.com/{repo}/pull/88",
            pr_number=88,
            state="open",
            is_dry_run=True,
        )

    def create_pull_request_comment(self, repo, pr_number, body):
        self.pr_comments.append(body)
        return GitHubCommentResult(
            html_url=f"https://github.com/{repo}/pull/{pr_number}#issuecomment-2",
            is_dry_run=True,
        )

    def apply_labels(self, repo, issue_number, labels):
        self.labels_applied.append((issue_number, labels))
        return type("GitHubLabelResultStub", (), {"labels": labels, "is_dry_run": True})()


def build_github_mcp(github: FakeGitHubService) -> MCPClient:
    client = MCPClient()
    server = InMemoryMCPServer()
    server.register_tool(
        "get_issue",
        lambda arguments: github.get_issue(arguments["repo"], arguments["issue_number"]).model_dump(mode="json"),
        server="github",
    )
    server.register_tool(
        "create_issue_comment",
        lambda arguments: {
            "html_url": github.create_issue_comment(
                arguments["repo"],
                arguments["issue_number"],
                arguments["body"],
            ).html_url,
        },
        server="github",
    )
    server.register_tool(
        "apply_labels",
        lambda arguments: {
            "labels": github.apply_labels(
                arguments["repo"],
                arguments["issue_number"],
                arguments["labels"],
            ).labels,
        },
        server="github",
    )
    server.register_tool(
        "create_pull_request",
        lambda arguments: {
            "title": arguments["title"],
            "body": arguments["body"],
            "html_url": f"https://github.com/{arguments['repo']}/pull/88",
            "number": 88,
            "state": "open",
        },
        server="github",
    )
    server.register_tool(
        "pull_request_review_write",
        lambda arguments: {
            "html_url": github.create_pull_request_comment(
                arguments["repo"],
                arguments["pr_number"],
                arguments["body"],
            ).html_url,
        },
        server="github",
    )
    client.register_adapter("github", server)
    return client


class FakeChannelService:
    def notify(
        self,
        title: str,
        lines: list[str],
        endpoint_id: str | None = None,
    ) -> ChannelNotificationResult:
        return ChannelNotificationResult(
            provider="feishu",
            delivered=False,
            is_dry_run=True,
            endpoint_id=endpoint_id,
        )


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
                summary="Review for sleep coding task",
                findings=[
                    ReviewFinding(
                        severity="P2",
                        title="Missing regression coverage",
                        detail="Add a regression assertion for the new task behavior.",
                        file_path="tests/example_test.py",
                        line=12,
                    )
                ],
                repair_strategy=["Add targeted regression coverage."],
                blocking=False,
                run_mode="dry_run",
                review_markdown="## Code Review Agent\n\nSource: sleep_coding_task\n\nContext:\n" + context,
            ),
            token_usage=TokenUsage(
                prompt_tokens=21,
                completion_tokens=9,
                total_tokens=30,
                cost_usd=0.001,
                step_name="code_review",
            ),
        )


class FakeBlockingReviewSkillService:
    def run(self, source, context: str) -> ReviewSkillRunResult:  # noqa: ANN001
        return ReviewSkillRunResult(
            output=ReviewSkillOutput(
                summary="Blocking review",
                findings=[
                    ReviewFinding(
                        severity="P1",
                        title="Blocking defect",
                        detail="Main flow still misses the repaired branch edge case.",
                        file_path="app/main.py",
                        line=9,
                    )
                ],
                repair_strategy=["Patch the branch edge case and rerun review."],
                blocking=True,
                run_mode="dry_run",
                review_markdown="## Blocking Review",
            ),
            token_usage=TokenUsage(
                prompt_tokens=18,
                completion_tokens=7,
                total_tokens=25,
                cost_usd=0.001,
                step_name="code_review",
            ),
        )


class FailingAgentRuntime:
    def __init__(self) -> None:
        self.mcp = MCPClient()

    def generate_structured_output(self, agent, **kwargs):
        raise RuntimeError("LLM provider is unreachable")


class FlakyAgentRuntime:
    def __init__(self, failures: int, output_text: str) -> None:
        self.remaining_failures = failures
        self.output_text = output_text
        self.mcp = MCPClient()
        self.calls = 0

    def generate_structured_output(self, agent, **kwargs):
        self.calls += 1
        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            raise RuntimeError("temporary review runtime failure")
        return type(
            "LLMResponseStub",
            (),
            {
                "output_text": self.output_text,
                "usage": TokenUsage(
                    prompt_tokens=22,
                    completion_tokens=8,
                    total_tokens=30,
                    provider="openai",
                    model_name="gpt-4.1-mini",
                    cost_usd=0.001,
                    step_name="code_review",
                ),
            },
        )()


class MalformedAgentRuntime:
    def __init__(self) -> None:
        self.mcp = MCPClient()

    def generate_structured_output(self, agent, **kwargs):
        return type(
            "LLMResponseStub",
            (),
            {
                "output_text": '{"path":"","repo":"marten","branch":"codex/issue-63-sleep-coding"}',
                "usage": TokenUsage(
                    prompt_tokens=18,
                    completion_tokens=6,
                    total_tokens=24,
                    provider="minimax",
                    model_name="MiniMax-M2.5",
                    cost_usd=0.0,
                    step_name="code_review",
                ),
            },
        )()


def build_settings(database_path: Path, review_runs_dir: Path) -> Settings:
    platform_config_path = database_path.parent / "platform.json"
    models_config_path = database_path.parent / "models.json"
    if not platform_config_path.exists():
        platform_config_path.write_text("{}", encoding="utf-8")
    if not models_config_path.exists():
        models_config_path.write_text("{}", encoding="utf-8")
    return Settings(
        app_env="test",
        database_url=f"sqlite:///{database_path}",
        platform_config_path=str(platform_config_path),
        models_config_path=str(models_config_path),
        review_runs_dir=str(review_runs_dir),
        github_repository="tiezhuli001/youmeng-gateway",
        langsmith_tracing=False,
        openai_api_key=None,
        minimax_api_key=None,
    )


def build_sleep_coding_service(settings: Settings, ledger: TokenLedgerService | None = None) -> tuple[SleepCodingService, MCPClient]:
    github = FakeGitHubService()
    mcp_client = build_github_mcp(github)
    sleep_coding = SleepCodingService(
        settings=settings,
        channel=FakeChannelService(),
        git_workspace=FakeGitWorkspaceService(),
        validator=FakeValidationRunner(),
        ledger=ledger or TokenLedgerService(settings),
        mcp_client=mcp_client,
    )
    return sleep_coding, mcp_client


class ReviewServiceTests(unittest.TestCase):
    def test_review_skill_falls_back_when_llm_call_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = Settings(
                app_env="development",
                database_url=f"sqlite:///{root / 'review.db'}",
                review_runs_dir=str(root / "review-runs"),
                github_repository="tiezhuli001/youmeng-gateway",
                minimax_api_key="test-key",
                openai_api_key=None,
                langsmith_tracing=False,
            )
            skill = ReviewSkillService(
                settings=settings,
                agent_runtime=FailingAgentRuntime(),
                mcp_client=MCPClient(),
            )

            result = skill.run(
                ReviewTarget(
                    task_id="task-fallback",
                    workspace_path=str(root),
                ),
                "dummy context",
            )

            self.assertEqual(result.output.run_mode, "real_run")
            self.assertFalse(result.output.blocking)
            self.assertIn("LLM provider is unreachable", result.output.review_markdown)

    def test_trigger_for_task_records_review_and_comment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            ledger = TokenLedgerService(settings)
            ledger.record_request(
                request_id="req-review-1",
                run_id="run-review-1",
                user_id="user-1",
                source="manual",
                intent="sleep_coding",
                content="Review task token aggregation",
                usage=TokenUsage(
                    prompt_tokens=4,
                    completion_tokens=2,
                    total_tokens=6,
                    cost_usd=0.001,
                    step_name="sleep_coding_plan",
                ),
            )
            sleep_coding, mcp_client = build_sleep_coding_service(settings, ledger=ledger)
            task = sleep_coding.start_task(
                SleepCodingTaskRequest(issue_number=33, request_id="req-review-1")
            )
            task = sleep_coding.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )
            review_service = ReviewService(
                settings=settings,
                sleep_coding=sleep_coding,
                skill=FakeReviewSkillService(),
                mcp_client=mcp_client,
            )

            review = review_service.trigger_for_task(task.task_id)

            self.assertEqual(review.target.task_id, task.task_id)
            self.assertEqual(review.status, "completed")
            self.assertEqual(review.task_id, task.task_id)
            self.assertEqual(review.findings[0].title, "Missing regression coverage")
            self.assertTrue(review.comment_url)
            self.assertEqual(review.token_usage.total_tokens, 30)
            self.assertGreater(sleep_coding.get_task(task.task_id).token_usage.total_tokens, 30)
            control_task = review_service.tasks.get_task(review.control_task_id)
            machine_output = control_task.payload.get("machine_output")
            human_output = control_task.payload.get("human_output")
            machine = ReviewMachineOutput.model_validate(machine_output)
            human = ReviewHumanOutput.model_validate(human_output)
            self.assertEqual(machine.blocking, False)
            self.assertIn("P2", machine.severity_counts)
            self.assertIn("summary", human.model_dump(mode="json"))
            self.assertIn("review_markdown", human.model_dump(mode="json"))

    def test_apply_action_updates_sleep_coding_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            sleep_coding, mcp_client = build_sleep_coding_service(settings)
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=44))
            task = sleep_coding.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )
            review_service = ReviewService(
                settings=settings,
                sleep_coding=sleep_coding,
                skill=FakeReviewSkillService(),
                mcp_client=mcp_client,
            )

            review = review_service.trigger_for_task(task.task_id)
            updated_review = review_service.apply_action(
                review.review_id,
                ReviewActionRequest(action="request_changes"),
            )
            review_task = review_service.tasks.get_task(updated_review.control_task_id)
            sleep_control_task = review_service.tasks.get_task(task.control_task_id)

            self.assertEqual(updated_review.status, "changes_requested")
            self.assertEqual(sleep_coding.get_task(task.task_id).status, "changes_requested")
            self.assertEqual(review_task.payload["review_decision"], "changes_requested")
            self.assertEqual(review_task.payload["next_owner_agent"], "ralph")
            review_returned = next(
                event
                for event in review_service.tasks.list_events(sleep_control_task.task_id)
                if event.event_type == "review_returned"
                and event.payload.get("next_owner_agent") == "ralph"
            )
            self.assertIn("blocking", review_returned.payload)
            self.assertEqual(review_returned.payload["review_round"], 1)
            self.assertIn("Review for sleep coding task", review_returned.payload["review_summary"])
            self.assertTrue(review_returned.payload["repair_strategy"])

    def test_count_blocking_reviews_tracks_task_reviews(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            sleep_coding, mcp_client = build_sleep_coding_service(settings)
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=52))
            task = sleep_coding.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )
            review_service = ReviewService(
                settings=settings,
                sleep_coding=sleep_coding,
                skill=FakeBlockingReviewSkillService(),
                mcp_client=mcp_client,
            )

            review = review_service.trigger_for_task(task.task_id)

            self.assertTrue(review.is_blocking)
            self.assertEqual(review_service.count_blocking_reviews(task.task_id), 1)

    def test_review_requires_validation_evidence_before_starting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            sleep_coding, mcp_client = build_sleep_coding_service(settings)
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=53))
            task = sleep_coding.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )
            with sleep_coding._connect() as connection:
                sleep_coding.store.update_task_payloads(
                    connection,
                    task.task_id,
                    status="in_review",
                    validation=ValidationResult(status="pending"),
                )
                connection.commit()
            sleep_coding.tasks.update_task(
                task.control_task_id,
                payload_patch={"validation_status": "pending", "validation_gap": None},
            )
            review_service = ReviewService(
                settings=settings,
                sleep_coding=sleep_coding,
                skill=FakeReviewSkillService(),
                mcp_client=mcp_client,
            )

            with self.assertRaisesRegex(ValueError, "validation evidence"):
                review_service.trigger_for_task(task.task_id)

    def test_start_review_requires_sleep_coding_task_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            sleep_coding, mcp_client = build_sleep_coding_service(settings)
            review_service = ReviewService(
                settings=settings,
                sleep_coding=sleep_coding,
                skill=FakeReviewSkillService(),
                mcp_client=mcp_client,
            )

            with self.assertRaisesRegex(ValueError, "task_id"):
                review_service.start_review(ReviewStartRequest(task_id=""))

    def test_command_output_json_is_parsed_into_structured_findings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            skill = ReviewSkillService(settings)

            structured = skill._parse_command_output(
                '{"summary":"Blocking review","findings":[{"severity":"P1","title":"Bug","detail":"Important bug","file_path":"app/main.py","line":9}],"repair_strategy":["Fix the bug"],"blocking":true,"review_markdown":"## Review"}'
            )

            self.assertEqual(structured.summary, "Blocking review")
            self.assertEqual(structured.findings[0].severity, "P1")
            self.assertTrue(structured.blocking)

    def test_command_output_requires_strict_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            skill = ReviewSkillService(settings)

            with self.assertRaisesRegex(RuntimeError, "strict JSON"):
                skill._parse_command_output("### Summary\nthis is not json")

    def test_agent_runtime_falls_back_when_structured_review_output_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs").model_copy(
                update={"openai_api_key": "test-key"}
            )
            skill = ReviewSkillService(
                settings,
                agent_runtime=MalformedAgentRuntime(),
                mcp_client=MCPClient(),
            )

            result = skill.run(
                ReviewTarget(task_id="task-agent-runtime"),
                "diff context",
            )

            self.assertEqual(result.output.run_mode, "real_run")
            self.assertFalse(result.output.blocking)
            self.assertIn("non-contract output", result.output.summary)

    def test_review_skill_retries_runtime_failures_before_succeeding(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs").model_copy(
                update={"openai_api_key": "test-key", "llm_request_max_attempts": 3}
            )
            runtime = FlakyAgentRuntime(
                failures=2,
                output_text='{"summary":"Recovered review","findings":[],"repair_strategy":[],"blocking":false,"review_markdown":"## Review"}',
            )
            skill = ReviewSkillService(
                settings,
                agent_runtime=runtime,
                mcp_client=MCPClient(),
            )

            result = skill.run(
                type(
                    "ReviewTargetStub",
                    (),
                    {"task_id": "task-1", "workspace_path": None},
                )(),
                "diff context",
            )

            self.assertEqual(runtime.calls, 3)
            self.assertEqual(result.output.summary, "Recovered review")
            self.assertEqual(result.output.run_mode, "real_run")

    def test_review_skill_command_timeout_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs").model_copy(
                update={"review_command_timeout_seconds": 11}
            )
            skill = ReviewSkillService(settings)

            with self.assertRaisesRegex(RuntimeError, "timed out after 11.0s"):
                with patch(
                    "app.agents.code_review_agent.skill.subprocess.run",
                    side_effect=subprocess.TimeoutExpired(cmd=["reviewer"], timeout=11),
                ):
                    skill._run_with_command(
                        ["reviewer"],
                        ReviewTarget(task_id="task-timeout", workspace_path=str(root)),
                        "review context",
                    )


if __name__ == "__main__":
    unittest.main()
