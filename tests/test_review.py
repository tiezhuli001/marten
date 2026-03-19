import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import Settings
from app.ledger.service import TokenLedgerService
from app.models.github_results import GitHubCommentResult
from app.models.schemas import (
    ReviewActionRequest,
    ReviewFinding,
    ReviewRunRequest,
    ReviewSkillOutput,
    ReviewSource,
    SleepCodingIssue,
    SleepCodingPullRequest,
    SleepCodingTaskActionRequest,
    SleepCodingTaskRequest,
    TokenUsage,
    ValidationResult,
)
from app.runtime.mcp import InMemoryMCPServer, MCPClient
from app.agents.code_review_agent import GitLabService, ReviewService, ReviewSkillRunResult, ReviewSkillService
from app.agents.code_review_agent.materializer import ReviewMaterializationError
from app.channel.notifications import ChannelNotificationResult
from app.agents.ralph import SleepCodingService


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
        lambda arguments: github.get_issue(
            arguments["repo"],
            arguments["issue_number"],
        ).model_dump(mode="json"),
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
    def notify(self, title: str, lines: list[str]) -> ChannelNotificationResult:
        return ChannelNotificationResult(provider="feishu", delivered=False, is_dry_run=True)


class FakeGitLabService:
    def __init__(self) -> None:
        self.comments: list[str] = []

    def create_merge_request_comment(self, project_path: str, mr_number: int, body: str) -> GitHubCommentResult:
        self.comments.append(body)
        return GitHubCommentResult(
            html_url=f"https://gitlab.com/{project_path}/-/merge_requests/{mr_number}#note_1",
            is_dry_run=True,
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
    def run(self, source: ReviewSource, context: str) -> ReviewSkillRunResult:
        return ReviewSkillRunResult(
            output=ReviewSkillOutput(
                summary=f"Review for {source.source_type}",
                findings=[
                    ReviewFinding(
                        severity="P2",
                        title="Missing regression coverage",
                        detail=f"Context reviewed for {source.source_type}",
                        file_path="tests/example_test.py",
                        line=12,
                    )
                ],
                repair_strategy=["Add targeted regression coverage."],
                blocking=False,
                run_mode="dry_run",
                review_markdown=f"## Code Review Agent\n\nSource: {source.source_type}\n\nContext:\n{context}",
            ),
            token_usage=TokenUsage(
                prompt_tokens=21,
                completion_tokens=9,
                total_tokens=30,
                cost_usd=0.001,
                step_name="code_review",
            ),
        )


class FailingAgentRuntime:
    def __init__(self) -> None:
        from app.runtime.mcp import MCPClient

        self.mcp = MCPClient()

    def generate_structured_output(self, agent, **kwargs):
        raise RuntimeError("LLM provider is unreachable")


def build_settings(database_path: Path, review_runs_dir: Path) -> Settings:
    platform_config_path = database_path.parent / "platform.json"
    if not platform_config_path.exists():
        platform_config_path.write_text("{}", encoding="utf-8")
    return Settings(
        app_env="test",
        database_url=f"sqlite:///{database_path}",
        platform_config_path=str(platform_config_path),
        review_runs_dir=str(review_runs_dir),
        github_repository="tiezhuli001/youmeng-gateway",
        langsmith_tracing=False,
        openai_api_key=None,
        minimax_api_key=None,
    )


class ReviewServiceTests(unittest.TestCase):
    def test_review_skill_raises_when_llm_call_fails(self) -> None:
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

            with patch("app.agents.code_review_agent.skill.which", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "LLM provider is unreachable"):
                    skill.run(
                        ReviewSource(source_type="local_code", local_path=str(root)),
                        "dummy context",
                    )

    def test_review_skill_command_takes_precedence_over_llm_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "platform.json").write_text(
                json.dumps(
                    {
                        "review": {
                            "skill_command": "echo",
                        }
                    }
                ),
                encoding="utf-8",
            )
            settings = Settings(
                app_env="test",
                database_url=f"sqlite:///{root / 'review.db'}",
                review_runs_dir=str(root / "review-runs"),
                platform_config_path=str(root / "platform.json"),
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

            expected = ReviewSkillRunResult(
                output=ReviewSkillOutput(
                    summary="command review",
                    findings=[],
                    repair_strategy=[],
                    blocking=False,
                    run_mode="real_run",
                    review_markdown="ok",
                ),
                token_usage=TokenUsage(total_tokens=10),
            )
            with patch.object(skill, "_run_with_command", return_value=expected) as run_with_command:
                result = skill.run(
                    ReviewSource(source_type="local_code", local_path=str(root)),
                    "dummy context",
                )

            self.assertEqual(result.output.summary, "command review")
            run_with_command.assert_called_once()

    def test_start_review_archives_local_code_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            github = FakeGitHubService()
            mcp_client = build_github_mcp(github)
            review_service = ReviewService(
                settings=settings,
                github=github,
                gitlab=FakeGitLabService(),
                sleep_coding=SleepCodingService(
                    settings=settings,
                    github=github,
                    channel=FakeChannelService(),
                    git_workspace=FakeGitWorkspaceService(),
                    validator=FakeValidationRunner(),
                    ledger=TokenLedgerService(settings),
                    mcp_client=mcp_client,
                ),
                skill=FakeReviewSkillService(),
                mcp_client=mcp_client,
            )

            review = review_service.start_review(
                ReviewRunRequest(
                    source=ReviewSource(
                        source_type="local_code",
                        local_path=str(root),
                        base_branch="main",
                        head_branch="feature/test",
                    )
                )
            )

            self.assertEqual(review.status, "completed")
            self.assertTrue(review.artifact_path.endswith(".md"))
            self.assertIn("Source: local_code", review.content)
            self.assertTrue(Path(review.artifact_path).exists())
            self.assertEqual(review.findings[0].severity, "P2")
            self.assertFalse(review.is_blocking)
            self.assertEqual(review.token_usage.total_tokens, 30)

    def test_trigger_for_sleep_coding_task_and_request_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            github = FakeGitHubService()
            mcp_client = build_github_mcp(github)
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
            sleep_coding = SleepCodingService(
                settings=settings,
                github=github,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner(),
                ledger=ledger,
                mcp_client=mcp_client,
            )
            task = sleep_coding.start_task(
                SleepCodingTaskRequest(issue_number=33, request_id="req-review-1")
            )
            task = sleep_coding.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )
            review_service = ReviewService(
                settings=settings,
                github=github,
                gitlab=FakeGitLabService(),
                sleep_coding=sleep_coding,
                skill=FakeReviewSkillService(),
                mcp_client=mcp_client,
            )

            review = review_service.trigger_for_task(task.task_id)
            updated_review = review_service.apply_action(
                review.review_id,
                ReviewActionRequest(action="request_changes"),
            )

            self.assertEqual(updated_review.status, "changes_requested")
            self.assertEqual(sleep_coding.get_task(task.task_id).status, "changes_requested")
            self.assertGreaterEqual(len(github.pr_comments), 1)
            self.assertIn("Issue Title: Review integration", review.content)
            self.assertIn("File Changes:", review.content)
            self.assertIn("## Ralph Review Decision", github.pr_comments[-1])
            self.assertIn("- Decision: Changes Requested", github.pr_comments[-1])
            self.assertIn("### Token Usage", github.pr_comments[-1])
            self.assertEqual(review.findings[0].title, "Missing regression coverage")
            self.assertEqual(review.token_usage.total_tokens, 30)
            self.assertGreater(sleep_coding.get_task(task.task_id).token_usage.total_tokens, 30)

    def test_gitlab_url_writes_comment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            gitlab = FakeGitLabService()
            github = FakeGitHubService()
            mcp_client = build_github_mcp(github)
            review_service = ReviewService(
                settings=settings,
                github=github,
                gitlab=gitlab,
                sleep_coding=SleepCodingService(
                    settings=settings,
                    github=github,
                    channel=FakeChannelService(),
                    git_workspace=FakeGitWorkspaceService(),
                    validator=FakeValidationRunner(),
                    ledger=TokenLedgerService(settings),
                    mcp_client=mcp_client,
                ),
                skill=FakeReviewSkillService(),
                mcp_client=mcp_client,
            )

            review = review_service.start_review(
                ReviewRunRequest(
                    source=ReviewSource(
                        source_type="gitlab_mr",
                        url="https://gitlab.com/group/project/-/merge_requests/12",
                    )
                )
            )

            self.assertEqual(review.source.source_type, "gitlab_mr")
            self.assertEqual(review.source.project_path, "group/project")
            self.assertEqual(len(gitlab.comments), 1)

    def test_sleep_coding_review_prefers_mcp_pull_request_review_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            github = FakeGitHubService()
            github_mcp = build_github_mcp(github)
            sleep_coding = SleepCodingService(
                settings=settings,
                github=github,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner(),
                ledger=TokenLedgerService(settings),
                mcp_client=github_mcp,
            )
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=77))
            task = sleep_coding.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )
            review_service = ReviewService(
                settings=settings,
                github=github,
                gitlab=FakeGitLabService(),
                sleep_coding=sleep_coding,
                skill=FakeReviewSkillService(),
                mcp_client=github_mcp,
            )
            mcp_client = MCPClient()
            server = InMemoryMCPServer()
            captured: list[dict[str, object]] = []
            server.register_tool(
                "pull_request_review_write",
                lambda arguments: captured.append(arguments) or {"url": "https://example.com/review/1"},
                server="github",
            )
            mcp_client.register_adapter("github", server)
            review_service.mcp_client = mcp_client
            review_service.github_server = "github"

            review = review_service.trigger_for_task(task.task_id)

            self.assertEqual(review.comment_url, "https://example.com/review/1")
            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0]["event"], "COMMENT")
            self.assertEqual(len(github.pr_comments), 0)

    def test_github_pr_review_raises_when_materialize_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            github = FakeGitHubService()
            mcp_client = build_github_mcp(github)
            review_service = ReviewService(
                settings=settings,
                github=github,
                gitlab=FakeGitLabService(),
                sleep_coding=SleepCodingService(
                    settings=settings,
                    github=github,
                    channel=FakeChannelService(),
                    git_workspace=FakeGitWorkspaceService(),
                    validator=FakeValidationRunner(),
                    ledger=TokenLedgerService(settings),
                    mcp_client=mcp_client,
                ),
                skill=FakeReviewSkillService(),
                mcp_client=mcp_client,
            )

            with patch.object(
                review_service.materializer,
                "materialize",
                side_effect=ReviewMaterializationError("cannot fetch remote review source"),
            ):
                with self.assertRaisesRegex(ReviewMaterializationError, "cannot fetch remote review source"):
                    review_service.start_review(
                        ReviewRunRequest(
                            source=ReviewSource(
                                source_type="github_pr",
                                repo="owner/repo",
                                pr_number=12,
                            )
                        )
                    )

    def test_sleep_coding_task_review_falls_back_when_materialize_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            github = FakeGitHubService()
            mcp_client = build_github_mcp(github)
            sleep_coding = SleepCodingService(
                settings=settings,
                github=github,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner(),
                ledger=TokenLedgerService(settings),
                mcp_client=mcp_client,
            )
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=55))
            task = sleep_coding.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )
            review_service = ReviewService(
                settings=settings,
                github=github,
                gitlab=FakeGitLabService(),
                sleep_coding=sleep_coding,
                skill=FakeReviewSkillService(),
                mcp_client=mcp_client,
            )

            with patch.object(
                review_service.materializer,
                "materialize",
                side_effect=ReviewMaterializationError("worktree missing"),
            ):
                review = review_service.trigger_for_task(task.task_id)

            self.assertEqual(review.status, "completed")
            self.assertIn("Issue Title: Review integration", review.content)

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

    def test_local_code_context_reports_friendly_git_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").mkdir()
            settings = build_settings(root / "review.db", root / "review-runs")
            github = FakeGitHubService()
            mcp_client = build_github_mcp(github)
            review_service = ReviewService(
                settings=settings,
                github=github,
                gitlab=FakeGitLabService(),
                sleep_coding=SleepCodingService(
                    settings=settings,
                    github=github,
                    channel=FakeChannelService(),
                    git_workspace=FakeGitWorkspaceService(),
                    validator=FakeValidationRunner(),
                    ledger=TokenLedgerService(settings),
                    mcp_client=mcp_client,
                ),
                skill=FakeReviewSkillService(),
                mcp_client=mcp_client,
            )

            context = review_service._build_local_code_context(
                ReviewSource(
                    source_type="local_code",
                    local_path=str(root),
                    base_branch="main",
                    head_branch="feature/missing",
                )
            )

            self.assertIn("Diff stat unavailable", context)
            self.assertIn("Detailed diff unavailable", context)
