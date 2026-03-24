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
    GitExecutionResult,
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


class CapturingReviewSkillService:
    def __init__(self) -> None:
        self.contexts: list[str] = []

    def run(self, source, context: str) -> ReviewSkillRunResult:  # noqa: ANN001
        self.contexts.append(context)
        return ReviewSkillRunResult(
            output=ReviewSkillOutput(
                summary="Captured review",
                findings=[],
                repair_strategy=[],
                blocking=False,
                run_mode="dry_run",
                review_markdown="## Review\n\nCaptured",
            ),
            token_usage=TokenUsage(
                prompt_tokens=8,
                completion_tokens=4,
                total_tokens=12,
                cost_usd=0.0,
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


class RecoveringReviewAgentRuntime:
    def __init__(self) -> None:
        self.mcp = MCPClient()
        self.calls = 0

    def generate_structured_output(self, agent, **kwargs):
        self.calls += 1
        output_text = (
            "review: invalid output"
            if self.calls == 1
            else '{"summary":"Recovered review","findings":[],"repair_strategy":[],"blocking":false,"review_markdown":"## Review"}'
        )
        return type(
            "LLMResponseStub",
            (),
            {
                "output_text": output_text,
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


class ScalarRepairStrategyReviewAgentRuntime:
    def __init__(self) -> None:
        self.mcp = MCPClient()
        self.calls = 0

    def generate_structured_output(self, agent, **kwargs):
        self.calls += 1
        return type(
            "LLMResponseStub",
            (),
            {
                "output_text": (
                    '{"summary":"Blocking review","findings":[],'
                    '"repair_strategy":"Fix the branch edge case and rerun review.",'
                    '"blocking":true,"review_markdown":"## Review"}'
                ),
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
        openai_api_key="test-key",
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
        agent_runtime=FakeRalphAgentRuntime(),
        mcp_client=mcp_client,
    )
    return sleep_coding, mcp_client


class ReviewServiceTests(unittest.TestCase):
    def test_review_skill_fails_when_builtin_review_runtime_fails(self) -> None:
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

            with self.assertRaisesRegex(RuntimeError, "LLM provider is unreachable"):
                skill.run(
                    ReviewTarget(
                        task_id="task-fallback",
                        workspace_path=str(root),
                    ),
                    "dummy context",
                )

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

    def test_review_context_prioritizes_worktree_and_validation_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            sleep_coding, mcp_client = build_sleep_coding_service(settings)
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=12))
            task = sleep_coding.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )
            skill = CapturingReviewSkillService()
            review_service = ReviewService(
                settings=settings,
                sleep_coding=sleep_coding,
                skill=skill,
                mcp_client=mcp_client,
            )

            review_service.start_review(ReviewStartRequest(task_id=task.task_id), write_comment=False)

            context = skill.contexts[-1]
            self.assertIn("Changed Files Evidence:", context)
            self.assertIn("tests/generated_test.py", context)
            self.assertIn("Validation Workspace:", context)
            self.assertIn("diff", context.lower())

    def test_review_context_keeps_task_evidence_when_workspace_snapshot_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            sleep_coding, mcp_client = build_sleep_coding_service(settings)
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=13))
            task = sleep_coding.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )
            with sleep_coding._connect() as connection:
                sleep_coding.store.update_task_payloads(
                    connection,
                    task.task_id,
                    status=task.status,
                    git_execution=task.git_execution.model_copy(
                        update={
                            "is_dry_run": False,
                            "worktree_path": str(root / "fake-worktree"),
                        }
                    ),
                )
                connection.commit()
            skill = CapturingReviewSkillService()
            review_service = ReviewService(
                settings=settings,
                sleep_coding=sleep_coding,
                skill=skill,
                mcp_client=mcp_client,
            )
            review_service.context_builder.workspace_support = type(
                "WorkspaceSupportStub",
                (),
                {
                    "build_workspace_context": staticmethod(
                        lambda target: "## Diff Stat\n1 file changed\n\n## Diff\n+live marker"
                    )
                },
            )()

            review_service.start_review(ReviewStartRequest(task_id=task.task_id), write_comment=False)

            context = skill.contexts[-1]
            self.assertIn("Changed Files Evidence:", context)
            self.assertIn("tests/generated_test.py", context)
            self.assertIn("Workspace Snapshot:", context)
            self.assertIn("+live marker", context)

    def test_review_context_truncates_oversized_diff_and_workspace_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            sleep_coding, mcp_client = build_sleep_coding_service(settings)
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=14))
            task = sleep_coding.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )
            huge_diff = "diff --git a/tests/generated_test.py b/tests/generated_test.py\n" + ("+line\n" * 6000)
            many_paths = [f"generated/file_{index}.py" for index in range(20)]
            with sleep_coding._connect() as connection:
                sleep_coding.store.update_task_payloads(
                    connection,
                    task.task_id,
                    status=task.status,
                    git_execution=task.git_execution.model_copy(
                        update={
                            "is_dry_run": False,
                            "worktree_path": str(root / "fake-worktree"),
                            "changed_files": many_paths,
                            "file_changes": [
                                {"path": path, "diff_excerpt": huge_diff}
                                for path in many_paths
                            ],
                            "diff_summary": "20 files changed",
                        }
                    ),
                )
                connection.commit()
            skill = CapturingReviewSkillService()
            review_service = ReviewService(
                settings=settings,
                sleep_coding=sleep_coding,
                skill=skill,
                mcp_client=mcp_client,
            )
            review_service.context_builder.workspace_support = type(
                "WorkspaceSupportStub",
                (),
                {
                    "build_workspace_context": staticmethod(
                        lambda target: "## Diff\n" + ("+workspace-line\n" * 5000)
                    )
                },
            )()

            review_service.start_review(ReviewStartRequest(task_id=task.task_id), write_comment=False)

            context = skill.contexts[-1]
            self.assertLess(len(context), 25000)
            self.assertIn("truncated", context)
            self.assertIn("generated/file_0.py", context)
            self.assertIn("Workspace Snapshot:", context)

    def test_review_requires_execution_evidence_before_starting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            sleep_coding, mcp_client = build_sleep_coding_service(settings)
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=12))
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
            review_service = ReviewService(
                settings=settings,
                sleep_coding=sleep_coding,
                skill=FakeReviewSkillService(),
                mcp_client=mcp_client,
            )

            with self.assertRaisesRegex(ValueError, "execution evidence"):
                review_service.start_review(ReviewStartRequest(task_id=task.task_id))

    def test_review_control_task_persists_evidence_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            sleep_coding, mcp_client = build_sleep_coding_service(settings)
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=12))
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

            review = review_service.start_review(
                ReviewStartRequest(task_id=task.task_id),
                write_comment=False,
            )
            control_task = review_service.tasks.get_task(review.control_task_id)
            evidence = control_task.payload.get("review_evidence")

            self.assertIsInstance(evidence, dict)
            self.assertEqual(evidence["validation_status"], "passed")
            self.assertIn("tests/generated_test.py", evidence["changed_files"])
            self.assertTrue(evidence["diff_summary"])

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

    def test_review_allows_explicit_validation_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            sleep_coding, mcp_client = build_sleep_coding_service(settings)
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=54))
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
                payload_patch={"validation_status": "pending", "validation_gap": "manual validation pending"},
            )
            review_service = ReviewService(
                settings=settings,
                sleep_coding=sleep_coding,
                skill=FakeReviewSkillService(),
                mcp_client=mcp_client,
            )

            review = review_service.trigger_for_task(task.task_id)

            self.assertEqual(review.task_id, task.task_id)

    def test_build_review_return_payload_includes_repair_strategy_and_round(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            sleep_coding, mcp_client = build_sleep_coding_service(settings)
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=55))
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
            review_service.tasks.update_task(
                review.control_task_id,
                payload_patch={
                    "machine_output": {
                        "repair_strategy": ["fix test", "rerun validation"],
                    }
                },
            )

            payload = review_service._build_review_return_payload(review)

            self.assertEqual(payload["blocking"], review.is_blocking)
            self.assertEqual(payload["review_summary"], review.summary)
            self.assertEqual(payload["repair_strategy"], ["fix test", "rerun validation"])
            self.assertEqual(payload["review_round"], 1)

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

    def test_review_skill_runs_through_builtin_runtime_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            runtime = FlakyAgentRuntime(
                failures=0,
                output_text='{"summary":"Blocking review","findings":[{"severity":"P1","title":"Bug","detail":"Important bug","file_path":"app/main.py","line":9}],"repair_strategy":["Fix the bug"],"blocking":true,"review_markdown":"## Review"}',
            )
            skill = ReviewSkillService(
                settings,
                agent_runtime=runtime,
                mcp_client=MCPClient(),
            )

            result = skill.run(
                ReviewTarget(task_id="task-runtime-only", workspace_path=str(root)),
                "diff context",
            )

            self.assertEqual(result.output.summary, "Blocking review")
            self.assertEqual(result.output.findings[0].severity, "P1")
            self.assertTrue(result.output.blocking)
            self.assertEqual(runtime.calls, 1)
            self.assertFalse(hasattr(skill, "_parse_command_output"))

    def test_agent_runtime_fails_when_structured_review_output_is_invalid(self) -> None:
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

            with self.assertRaisesRegex(RuntimeError, "invalid structured review output"):
                skill.run(
                    ReviewTarget(task_id="task-agent-runtime"),
                    "diff context",
                )

    def test_review_skill_retries_once_after_invalid_structured_review_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs").model_copy(
                update={"openai_api_key": "test-key"}
            )
            runtime = RecoveringReviewAgentRuntime()
            skill = ReviewSkillService(
                settings,
                agent_runtime=runtime,
                mcp_client=MCPClient(),
            )

            result = skill.run(
                ReviewTarget(task_id="task-runtime-retry", workspace_path=str(root)),
                "diff context",
            )

            self.assertEqual(runtime.calls, 2)
            self.assertEqual(result.output.summary, "Recovered review")

    def test_review_skill_normalizes_scalar_repair_strategy_from_builtin_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs").model_copy(
                update={"openai_api_key": "test-key"}
            )
            runtime = ScalarRepairStrategyReviewAgentRuntime()
            skill = ReviewSkillService(
                settings,
                agent_runtime=runtime,
                mcp_client=MCPClient(),
            )

            result = skill.run(
                ReviewTarget(task_id="task-runtime-normalize", workspace_path=str(root)),
                "diff context",
            )

            self.assertEqual(runtime.calls, 1)
            self.assertEqual(
                result.output.repair_strategy,
                ["Fix the branch edge case and rerun review."],
            )
            self.assertTrue(result.output.blocking)

    def test_review_skill_does_not_repeat_runtime_retries_above_agent_runtime_layer(self) -> None:
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

            with self.assertRaisesRegex(RuntimeError, "temporary review runtime failure"):
                skill.run(
                    type(
                        "ReviewTargetStub",
                        (),
                        {"task_id": "task-1", "workspace_path": None},
                    )(),
                    "diff context",
                )

            self.assertEqual(runtime.calls, 1)

    def test_review_skill_requires_builtin_runtime_when_llm_credentials_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            models_config_path = root / "models.json"
            models_config_path.write_text("{}", encoding="utf-8")
            settings = build_settings(root / "review.db", root / "review-runs").model_copy(
                update={
                    "openai_api_key": None,
                    "minimax_api_key": None,
                    "models_config_path": str(models_config_path),
                }
            )
            skill = ReviewSkillService(settings)

            with self.assertRaisesRegex(RuntimeError, "Builtin code-review-agent runtime is unavailable"):
                skill.run(
                    ReviewTarget(task_id="task-timeout", workspace_path=str(root)),
                    "review context",
                )


if __name__ == "__main__":
    unittest.main()
