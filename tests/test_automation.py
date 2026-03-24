import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings
from app.ledger.service import TokenLedgerService
from app.models.schemas import (
    GitExecutionResult,
    ReviewActionRequest,
    ReviewFinding,
    ReviewSkillOutput,
    ReviewRun,
    ReviewTarget,
    SleepCodingIssue,
    SleepCodingPullRequest,
    SleepCodingTaskActionRequest,
    SleepCodingTaskRequest,
    SleepCodingWorkerClaim,
    SleepCodingWorkerPollRequest,
    TokenUsage,
    ValidationResult,
)
from app.runtime.mcp import InMemoryMCPServer, MCPClient
from app.agents.code_review_agent import ReviewService, ReviewSkillRunResult
from app.control.automation import AutomationService
from app.channel.notifications import ChannelNotificationResult
from app.agents.ralph import SleepCodingService


def build_github_mcp(github: "FakeGitHubService") -> MCPClient:
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
            "is_dry_run": True,
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
            "is_dry_run": True,
        },
        server="github",
    )
    server.register_tool(
        "create_pull_request",
        lambda arguments: {
            "title": str(arguments["title"]),
            "body": str(arguments["body"]),
            "html_url": f"https://github.com/{arguments['repo']}/pull/88",
            "number": 88,
            "state": "open",
            "is_dry_run": True,
        },
        server="github",
    )
    server.register_tool(
        "pull_request_review_write",
        lambda arguments: {
            "html_url": f"https://github.com/{arguments['repo']}/pull/{arguments['pr_number']}#issuecomment-2",
            "is_dry_run": True,
        },
        server="github",
    )
    client.register_adapter("github", server)
    return client


class FakeBackgroundJobs:
    def __init__(self) -> None:
        self.keys: list[str] = []
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def submit_unique(self, key: str, fn, *args: object) -> bool:  # noqa: ANN001
        self.keys.append(key)
        self.calls.append((key, args))
        return True


class ImmediateBackgroundJobs(FakeBackgroundJobs):
    def submit_unique(self, key: str, fn, *args: object) -> bool:  # noqa: ANN001
        accepted = super().submit_unique(key, fn, *args)
        if accepted:
            fn(*args)
        return accepted


class FakeGitHubService:
    def __init__(self) -> None:
        self.pr_comments: list[str] = []

    def get_issue(self, repo, issue_number, title_override=None, body_override=None):
        return SleepCodingIssue(
            issue_number=issue_number,
            title=title_override or "Automation integration",
            body=body_override or "Need automatic review loop.",
            html_url=f"https://github.com/{repo}/issues/{issue_number}",
            labels=["agent:ralph", "workflow:sleep-coding"],
            is_dry_run=True,
        )

    def create_issue_comment(self, repo, issue_number, body):
        return type(
            "GitHubCommentResultStub",
            (),
            {
                "html_url": f"https://github.com/{repo}/issues/{issue_number}#issuecomment-1",
                "is_dry_run": True,
            },
        )()

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
        return type(
            "GitHubCommentResultStub",
            (),
            {
                "html_url": f"https://github.com/{repo}/pull/{pr_number}#issuecomment-2",
                "is_dry_run": True,
            },
        )()

    def apply_labels(self, repo, issue_number, labels):
        return type("GitHubLabelResultStub", (), {"labels": labels, "is_dry_run": True})()


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


class FakeWorkerPollService:
    def __init__(self) -> None:
        self.requests: list[SleepCodingWorkerPollRequest] = []

    def poll_once(self, payload: SleepCodingWorkerPollRequest) -> object:  # noqa: ANN401
        self.requests.append(payload)
        from app.models.schemas import SleepCodingWorkerPollResponse

        return SleepCodingWorkerPollResponse(
            repo=payload.repo or "n/a",
            worker_id=payload.worker_id,
            auto_approve_plan=bool(payload.auto_approve_plan),
            discovered_count=0,
            claimed_count=0,
            skipped_count=0,
            tasks=[],
            claims=[],
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


class FailingValidationRunner:
    def run(self, repo_path: Path) -> ValidationResult:
        return ValidationResult(
            status="failed",
            command="python -m unittest discover -s tests",
            exit_code=1,
            output="validation failed",
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


class FakeReviewSkillService:
    def run(self, source, context: str) -> ReviewSkillRunResult:  # noqa: ANN001
        return ReviewSkillRunResult(
            output=ReviewSkillOutput(
                summary="Review for sleep coding task",
                findings=[
                    ReviewFinding(
                        severity="P2",
                        title="Minor follow-up",
                        detail="Add one more assertion if needed.",
                        file_path="tests/generated_test.py",
                        line=1,
                    )
                ],
                repair_strategy=["Tighten the regression test if the diff expands."],
                blocking=False,
                run_mode="real_run",
                review_markdown="## Code Review Agent\n\nLooks acceptable.",
            ),
            token_usage=TokenUsage(
                prompt_tokens=18,
                completion_tokens=7,
                total_tokens=25,
                cost_usd=0.001,
                step_name="code_review",
            ),
        )


class FakeReviewService:
    def __init__(self, sleep_coding: SleepCodingService, blocking_sequence: list[bool]) -> None:
        self.sleep_coding = sleep_coding
        self.blocking_sequence = list(blocking_sequence)
        self.reviews: list[ReviewRun] = []

    def trigger_for_task(self, task_id: str, *, write_comment: bool = True) -> ReviewRun:
        task = self.sleep_coding.get_task(task_id)
        review_index = len(self.reviews) + 1
        is_blocking = self.blocking_sequence.pop(0) if self.blocking_sequence else False
        review = ReviewRun(
            review_id=f"review-{review_index}",
            target=ReviewTarget(
                task_id=task.task_id,
                repo=task.repo,
                pr_number=task.pull_request.pr_number if task.pull_request else None,
                url=task.pull_request.html_url if task.pull_request else None,
            ),
            status="completed",
            artifact_path=f"docs/review-runs/review-{review_index}.md",
            comment_url=(
                f"https://github.com/{task.repo}/pull/88#issuecomment-{review_index}"
                if write_comment
                else None
            ),
            summary="review",
            content="P1 blocking issue" if is_blocking else "P2 minor issue",
            severity_counts={"P1": 1} if is_blocking else {"P2": 1},
            is_blocking=is_blocking,
            run_mode="dry_run",
            task_id=task.task_id,
            token_usage=TokenUsage(
                prompt_tokens=8,
                completion_tokens=4,
                total_tokens=12,
                cost_usd=0.001,
                step_name="code_review",
            ),
            created_at="2026-03-16 00:00:00",
            updated_at="2026-03-16 00:00:00",
            reviewed_at="2026-03-16 00:00:00",
        )
        self.reviews.append(review)
        return review

    def count_blocking_reviews(self, task_id: str) -> int:
        return sum(1 for review in self.reviews if review.task_id == task_id and review.is_blocking)

    def list_task_reviews(self, task_id: str) -> list[ReviewRun]:
        return [review for review in self.reviews if review.task_id == task_id]

    def apply_action(
        self,
        review_id: str,
        payload: ReviewActionRequest,
        *,
        write_remote: bool = True,
    ) -> ReviewRun:
        review = next(review for review in self.reviews if review.review_id == review_id)
        review.status = "approved" if payload.action == "approve_review" else "changes_requested"
        if review.task_id:
            if payload.action == "request_changes":
                self.sleep_coding.apply_action(
                    review.task_id,
                    SleepCodingTaskActionRequest(action="request_changes"),
                )
            elif payload.action == "approve_review":
                task = self.sleep_coding.get_task(review.task_id)
                if task.status != "approved":
                    self.sleep_coding.apply_action(
                        review.task_id,
                        SleepCodingTaskActionRequest(action="approve_pr"),
                    )
        return review

    def publish_final_result(self, review_id: str, action: str) -> ReviewRun:
        review = next(review for review in self.reviews if review.review_id == review_id)
        review.comment_url = f"https://github.com/{review.target.repo}/pull/88#final-{action}"
        return review


class MissingReviewEvidenceService(FakeReviewService):
    def trigger_for_task(self, task_id: str, *, write_comment: bool = True) -> ReviewRun:
        review = super().trigger_for_task(task_id, write_comment=write_comment)
        review.comment_url = None
        review.artifact_path = None
        return review

    def publish_final_result(self, review_id: str, action: str) -> ReviewRun:
        review = next(review for review in self.reviews if review.review_id == review_id)
        review.comment_url = None
        review.artifact_path = None
        return review


def build_settings(database_path: Path) -> Settings:
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
        review_runs_dir=str(database_path.parent / "review-runs"),
        github_repository="tiezhuli001/youmeng-gateway",
        openai_api_key="test-key",
        minimax_api_key=None,
        review_max_repair_rounds=3,
        langsmith_tracing=False,
    )


def build_sleep_coding_service(
    *,
    settings: Settings,
    channel: FakeChannelService,
    github: FakeGitHubService,
    validator: FakeValidationRunner | FailingValidationRunner,
    ledger: TokenLedgerService,
) -> SleepCodingService:
    return SleepCodingService(
        settings=settings,
        channel=channel,
        git_workspace=FakeGitWorkspaceService(),
        validator=validator,
        ledger=ledger,
        agent_runtime=FakeRalphAgentRuntime(),
        mcp_client=build_github_mcp(github),
    )


class AutomationServiceTests(unittest.TestCase):
    def test_handle_control_task_action_can_approve_plan_from_control_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "automation.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            background = FakeBackgroundJobs()
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                github=github,
                validator=FakeValidationRunner(),
                ledger=TokenLedgerService(settings),
            )
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=FakeReviewService(sleep_coding, blocking_sequence=[False]),
                channel=channel,
                ledger=TokenLedgerService(settings),
                background_jobs=background,
            )
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=68))

            result = automation.handle_control_task_action(task.control_task_id, "approve_plan")

            self.assertEqual(result.control_task_id, task.control_task_id)
            self.assertEqual(result.action, "approve_plan")
            self.assertEqual(result.status, "in_review")
            self.assertEqual(result.domain_task_id, task.task_id)
            self.assertEqual(background.keys, [f"sleep-coding-follow-up:{task.task_id}"])

    def test_handle_control_task_action_can_resume_queued_parent_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "automation.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                github=github,
                validator=FakeValidationRunner(),
                ledger=TokenLedgerService(settings),
            )
            worker = FakeWorkerPollService()
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                worker=worker,  # type: ignore[arg-type]
                review=FakeReviewService(sleep_coding, blocking_sequence=[False]),
                channel=channel,
                ledger=TokenLedgerService(settings),
            )
            control_task = automation.tasks.create_task(
                task_type="main_agent_intake",
                agent_id="main-agent",
                status="issue_created",
                user_id="user-1",
                source="manual",
                repo="acme/platform-repo",
                issue_number=55,
                title="Queued intake",
                external_ref="github_issue:acme/platform-repo#55",
                payload={"queue_status": "queued"},
            )

            result = automation.handle_control_task_action(control_task.task_id, "resume")

            self.assertEqual(result.control_task_id, control_task.task_id)
            self.assertEqual(result.action, "resume")
            self.assertEqual(result.claimed_count, 0)
            self.assertEqual(worker.requests[0].repo, "acme/platform-repo")

    def test_handle_control_task_action_can_mark_task_needs_attention(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "automation.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                github=github,
                validator=FakeValidationRunner(),
                ledger=TokenLedgerService(settings),
            )
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=FakeReviewService(sleep_coding, blocking_sequence=[False]),
                channel=channel,
                ledger=TokenLedgerService(settings),
            )
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=67))

            result = automation.handle_control_task_action(
                task.control_task_id,
                "mark_needs_attention",
                reason="operator intervention",
            )

            control_task = automation.tasks.get_task(task.control_task_id)
            self.assertEqual(result.status, "needs_attention")
            self.assertEqual(control_task.status, "needs_attention")
            self.assertEqual(control_task.payload["last_error"], "operator intervention")

    def test_handle_sleep_coding_action_async_schedules_follow_up_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "automation.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            background = FakeBackgroundJobs()
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                github=github,
                validator=FakeValidationRunner(),
                ledger=TokenLedgerService(settings),
            )
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=FakeReviewService(sleep_coding, blocking_sequence=[False]),
                channel=channel,
                ledger=TokenLedgerService(settings),
                background_jobs=background,
            )
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=69))

            updated = automation.handle_sleep_coding_action_async(task.task_id, "approve_plan")

            self.assertEqual(updated.status, "in_review")
            self.assertEqual(background.keys, [f"sleep-coding-follow-up:{task.task_id}"])
            reloaded = sleep_coding.get_task(task.task_id)
            self.assertEqual(reloaded.background_follow_up_status, "queued")
            self.assertTrue(
                any(event.event_type == "follow_up.queued" for event in reloaded.events)
            )

    def test_auto_review_approves_clean_pr_and_sends_final_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "automation.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            ledger = TokenLedgerService(settings)
            ledger.record_request(
                request_id="req-automation-1",
                run_id="run-automation-1",
                user_id="user-1",
                source="manual",
                intent="sleep_coding",
                content="Run automation test",
                usage=TokenUsage(
                    prompt_tokens=5,
                    completion_tokens=2,
                    total_tokens=7,
                    cost_usd=0.001,
                    step_name="sleep_coding_plan",
                ),
            )
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                github=github,
                validator=FakeValidationRunner(),
                ledger=ledger,
            )
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=FakeReviewService(sleep_coding, blocking_sequence=[False]),
                channel=channel,
                ledger=ledger,
            )
            task = sleep_coding.start_task(
                SleepCodingTaskRequest(issue_number=70, request_id="req-automation-1")
            )

            updated = automation.handle_sleep_coding_action(task.task_id, "approve_plan")

            self.assertEqual(updated.status, "approved")
            self.assertTrue(any("任务完成" in title for title, _, _ in channel.notifications))
            final_lines = channel.notifications[-1][1]
            self.assertIn("工作总结:", final_lines)
            self.assertIn("二、关键变更说明", final_lines)
            self.assertIn("三、Token 消耗统计", final_lines)
            self.assertIn("四、总结", final_lines)
            self.assertTrue(any("需求摘要:" in line for line in final_lines))
            self.assertTrue(any("Ralph 已完成任务，请过目。" in line for line in final_lines))
            self.assertTrue(any("输入 Token:" in line for line in final_lines))
            self.assertTrue(any("总 Token:" in line for line in final_lines))
            self.assertTrue(any("阶段分布:" in line for line in final_lines))
            self.assertTrue(any(line.startswith("Plan: 输入") for line in final_lines))
            self.assertTrue(any(line.startswith("Execution: 输入") for line in final_lines))
            self.assertTrue(any(line.startswith("Review: 输入") for line in final_lines))
            self.assertTrue(any("缓存读取 Token:" in line for line in final_lines))
            self.assertTrue(any("推理 Token:" in line for line in final_lines))
            control_task = automation.tasks.get_task(updated.control_task_id)
            final_evidence = control_task.payload.get("final_evidence")
            terminal_evidence = control_task.payload.get("terminal_evidence")
            self.assertIsInstance(final_evidence, dict)
            self.assertIsInstance(terminal_evidence, dict)
            self.assertEqual(final_evidence["task_status"], "approved")
            self.assertEqual(final_evidence["validation_status"], "passed")
            self.assertEqual(final_evidence["review_status"], "approved")
            self.assertEqual(final_evidence["review_id"], "review-1")
            self.assertGreater(final_evidence["token_usage"]["total_tokens"], 0)
            self.assertEqual(terminal_evidence["terminal_state"], "completed")

    def test_auto_review_stops_after_three_blocking_rounds_and_hands_off(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "automation.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                github=github,
                validator=FakeValidationRunner(),
                ledger=TokenLedgerService(settings),
            )
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=FakeReviewService(sleep_coding, blocking_sequence=[True, True, True]),
                channel=channel,
                ledger=TokenLedgerService(settings),
            )
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=71))

            updated = automation.handle_sleep_coding_action(task.task_id, "approve_plan")

            self.assertEqual(updated.status, "needs_attention")
            self.assertTrue(
                any("Manual review required" in title for title, _, _ in channel.notifications)
            )
            self.assertFalse(
                any("任务完成" in title for title, _, _ in channel.notifications)
            )
            control_task = automation.tasks.get_task(updated.control_task_id)
            self.assertEqual(control_task.status, "needs_attention")
            self.assertEqual(control_task.payload["review_id"], "review-3")
            self.assertEqual(control_task.payload["review_round"], 3)
            self.assertIn("review", control_task.payload["review_summary"].lower())
            self.assertTrue(control_task.payload["repair_strategy"])
            self.assertEqual(control_task.payload["terminal_evidence"]["terminal_state"], "needs_attention")
            recovery = automation.tasks.build_recovery_snapshot(control_task.task_id)
            self.assertEqual(recovery["next_action"], "operator_attention")
            self.assertEqual(recovery["latest_event_type"], "needs_attention")

    def test_validation_failure_keeps_truthful_terminal_evidence_for_operator_reentry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "automation.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            ledger = TokenLedgerService(settings)
            ledger.record_request(
                request_id="req-validation-fail",
                run_id="run-validation-fail",
                user_id="user-1",
                source="manual",
                intent="sleep_coding",
                content="Run failing validation test",
                usage=TokenUsage(
                    prompt_tokens=9,
                    completion_tokens=3,
                    total_tokens=12,
                    cost_usd=0.001,
                    step_name="sleep_coding_plan",
                ),
            )
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                github=github,
                validator=FailingValidationRunner(),
                ledger=ledger,
            )
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=FakeReviewService(sleep_coding, blocking_sequence=[]),
                channel=channel,
                ledger=ledger,
            )
            task = sleep_coding.start_task(
                SleepCodingTaskRequest(issue_number=77, request_id="req-validation-fail")
            )

            updated = automation.handle_sleep_coding_action(task.task_id, "approve_plan")

            self.assertEqual(updated.status, "failed")
            self.assertFalse(any("任务完成" in title for title, _, _ in channel.notifications))
            control_task = automation.tasks.get_task(updated.control_task_id)
            terminal_evidence = control_task.payload.get("terminal_evidence")
            self.assertEqual(control_task.status, "failed")
            self.assertIsInstance(terminal_evidence, dict)
            self.assertEqual(terminal_evidence["terminal_state"], "failed")
            self.assertEqual(terminal_evidence["validation_status"], "failed")
            self.assertEqual(terminal_evidence["last_error"], "Local validation failed.")
            self.assertGreater(terminal_evidence["token_usage"]["total_tokens"], 0)

    def test_completed_task_with_dry_run_delivery_records_degraded_delivery_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "automation.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            ledger = TokenLedgerService(settings)
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                github=github,
                validator=FakeValidationRunner(),
                ledger=ledger,
            )
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=FakeReviewService(sleep_coding, blocking_sequence=[False]),
                channel=channel,
                ledger=ledger,
            )
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=78))

            updated = automation.handle_sleep_coding_action(task.task_id, "approve_plan")

            self.assertEqual(updated.status, "approved")
            control_task = automation.tasks.get_task(updated.control_task_id)
            self.assertEqual(control_task.status, "completed")
            self.assertEqual(control_task.payload["terminal_evidence"]["terminal_state"], "completed")
            self.assertEqual(control_task.payload["delivery_status"], "degraded")
            self.assertFalse(control_task.payload["delivery_delivered"])
            self.assertEqual(control_task.payload["delivery_stage"], "final_delivery")

    def test_approved_task_without_review_does_not_skip_review_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "automation.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                github=github,
                validator=FakeValidationRunner(),
                ledger=TokenLedgerService(settings),
            )
            review = FakeReviewService(sleep_coding, blocking_sequence=[False])
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=review,
                channel=channel,
                ledger=TokenLedgerService(settings),
            )
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=74))
            task = sleep_coding.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )
            task = sleep_coding.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_pr"),
            )

            updated = automation.run_review_loop(task.task_id)

            self.assertEqual(updated.status, "approved")
            self.assertEqual(len(review.reviews), 1)
            self.assertTrue(any("任务完成" in title for title, _, _ in channel.notifications))

    def test_final_delivery_requires_execution_truth(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "automation.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                github=github,
                validator=FakeValidationRunner(),
                ledger=TokenLedgerService(settings),
            )
            review = FakeReviewService(sleep_coding, blocking_sequence=[False])
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=review,
                channel=channel,
                ledger=TokenLedgerService(settings),
            )
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=79))
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

            updated = automation.run_review_loop(task.task_id)
            control_task = automation.tasks.get_task(updated.control_task_id)
            recovery = automation.tasks.build_recovery_snapshot(control_task.task_id)

            self.assertEqual(updated.status, "needs_attention")
            self.assertEqual(control_task.status, "needs_attention")
            self.assertIn("execution evidence", control_task.payload["last_error"].lower())
            self.assertEqual(recovery["next_action"], "repair_execution_evidence")
            self.assertNotIn("final_evidence", control_task.payload)
            self.assertFalse(any("任务完成" in title for title, _, _ in channel.notifications))

    def test_final_delivery_requires_review_truth(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "automation.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                github=github,
                validator=FakeValidationRunner(),
                ledger=TokenLedgerService(settings),
            )
            review = MissingReviewEvidenceService(sleep_coding, blocking_sequence=[False])
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=review,
                channel=channel,
                ledger=TokenLedgerService(settings),
            )
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=80))
            task = sleep_coding.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )

            updated = automation.run_review_loop(task.task_id)
            control_task = automation.tasks.get_task(updated.control_task_id)
            recovery = automation.tasks.build_recovery_snapshot(control_task.task_id)

            self.assertEqual(updated.status, "needs_attention")
            self.assertIn("review evidence", control_task.payload["last_error"].lower())
            self.assertEqual(recovery["next_action"], "repair_review_evidence")
            self.assertNotIn("final_evidence", control_task.payload)

    def test_real_review_service_can_force_one_blocking_pass_then_approve(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "automation.db").model_copy(
                update={"review_force_blocking_first_pass": True}
            )
            github = FakeGitHubService()
            channel = FakeChannelService()
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                github=github,
                validator=FakeValidationRunner(),
                ledger=TokenLedgerService(settings),
            )
            review = ReviewService(
                settings=settings,
                sleep_coding=sleep_coding,
                skill=FakeReviewSkillService(),
                mcp_client=build_github_mcp(github),
            )
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=review,
                channel=channel,
                ledger=TokenLedgerService(settings),
            )
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=72))

            updated = automation.handle_sleep_coding_action(task.task_id, "approve_plan")
            reviews = review.list_task_reviews(task.task_id)

            self.assertEqual(updated.status, "approved")
            self.assertEqual(len(reviews), 2)
            self.assertEqual(sum(1 for item in reviews if item.is_blocking), 1)
            self.assertTrue(any(item.status == "changes_requested" for item in reviews))
            self.assertTrue(any((not item.is_blocking) and item.status == "approved" for item in reviews))

    def test_process_worker_poll_resumes_changes_requested_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "automation.db").model_copy(
                update={"review_force_blocking_first_pass": True}
            )
            github = FakeGitHubService()
            channel = FakeChannelService()
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                github=github,
                validator=FakeValidationRunner(),
                ledger=TokenLedgerService(settings),
            )
            review = ReviewService(
                settings=settings,
                sleep_coding=sleep_coding,
                skill=FakeReviewSkillService(),
                mcp_client=build_github_mcp(github),
            )
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=73))
            first_pass = sleep_coding.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )
            initial_review = review.trigger_for_task(first_pass.task_id)
            self.assertTrue(initial_review.is_blocking)
            review.apply_action(
                initial_review.review_id,
                ReviewActionRequest(action="request_changes"),
            )

            class StubWorker:
                def poll_once(self, payload):  # noqa: ANN001
                    from app.models.schemas import SleepCodingWorkerPollResponse

                    return SleepCodingWorkerPollResponse(
                        repo=settings.github_repository,
                        worker_id="sleep-coding-worker",
                        auto_approve_plan=True,
                        discovered_count=0,
                        claimed_count=0,
                        skipped_count=0,
                        tasks=[],
                        claims=[
                            SleepCodingWorkerClaim(
                                repo=settings.github_repository,
                                issue_number=73,
                                task_id=task.task_id,
                                status="changes_requested",
                                title="resume changes requested task",
                                html_url=f"https://github.com/{settings.github_repository}/issues/73",
                                labels=["agent:ralph", "workflow:sleep-coding"],
                                worker_id="sleep-coding-worker",
                                lease_expires_at=None,
                                last_heartbeat_at=None,
                                retry_count=0,
                                next_retry_at=None,
                                last_error=None,
                                created_at="2026-03-18 00:00:00",
                                updated_at="2026-03-18 00:00:00",
                            )
                        ],
                    )

            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=review,
                worker=StubWorker(),
                channel=channel,
                ledger=TokenLedgerService(settings),
            )

            response = automation.process_worker_poll(payload=None)  # type: ignore[arg-type]
            updated = sleep_coding.get_task(task.task_id)
            reviews = review.list_task_reviews(task.task_id)

            self.assertEqual(response.claimed_count, 0)
            self.assertEqual(updated.status, "approved")
            self.assertEqual(len(reviews), 2)
            statuses = {item.status for item in reviews}
            self.assertIn("changes_requested", statuses)
            self.assertIn("approved", statuses)

    def test_process_worker_poll_async_schedules_follow_up_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "automation.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            background = FakeBackgroundJobs()
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                github=github,
                validator=FakeValidationRunner(),
                ledger=TokenLedgerService(settings),
            )
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=74))
            task = sleep_coding.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )

            class StubWorker:
                def poll_once(self, payload):  # noqa: ANN001
                    from app.models.schemas import SleepCodingWorkerPollResponse

                    return SleepCodingWorkerPollResponse(
                        repo=settings.github_repository,
                        worker_id="sleep-coding-worker",
                        auto_approve_plan=True,
                        discovered_count=0,
                        claimed_count=1,
                        skipped_count=0,
                        tasks=[sleep_coding.get_task(task.task_id)],
                        claims=[],
                    )

            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=FakeReviewService(sleep_coding, blocking_sequence=[False]),
                worker=StubWorker(),
                channel=channel,
                ledger=TokenLedgerService(settings),
                background_jobs=background,
            )

            response = automation.process_worker_poll_async(payload=None)  # type: ignore[arg-type]

            self.assertEqual(response.claimed_count, 1)
            self.assertEqual(background.keys, [f"sleep-coding-follow-up:{task.task_id}"])

    def test_background_follow_up_updates_task_and_control_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "automation.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                github=github,
                validator=FakeValidationRunner(),
                ledger=TokenLedgerService(settings),
            )
            automation = AutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=FakeReviewService(sleep_coding, blocking_sequence=[False]),
                channel=channel,
                ledger=TokenLedgerService(settings),
                background_jobs=ImmediateBackgroundJobs(),
            )
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=75))

            automation.handle_sleep_coding_action_async(task.task_id, "approve_plan")

            updated_task = sleep_coding.get_task(task.task_id)
            self.assertEqual(updated_task.status, "approved")
            self.assertEqual(updated_task.background_follow_up_status, "completed")
            event_types = [event.event_type for event in updated_task.events]
            self.assertIn("follow_up.processing", event_types)
            self.assertIn("follow_up.completed", event_types)

            control_task = automation.tasks.get_task(updated_task.control_task_id)
            self.assertEqual(control_task.payload["background_follow_up_status"], "completed")
            control_events = [
                event.event_type for event in automation.tasks.list_events(control_task.task_id)
            ]
            self.assertIn("follow_up.processing", control_events)
            self.assertIn("follow_up.completed", control_events)

    def test_background_follow_up_failure_escalates_control_task_with_recovery_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "automation.db")
            github = FakeGitHubService()
            channel = FakeChannelService()
            sleep_coding = build_sleep_coding_service(
                settings=settings,
                channel=channel,
                github=github,
                validator=FakeValidationRunner(),
                ledger=TokenLedgerService(settings),
            )

            class ExplodingAutomationService(AutomationService):
                def run_review_loop(self, task_id: str):  # type: ignore[override]
                    raise RuntimeError("simulated review follow-up timeout")

            automation = ExplodingAutomationService(
                settings=settings,
                sleep_coding=sleep_coding,
                review=FakeReviewService(sleep_coding, blocking_sequence=[False]),
                channel=channel,
                ledger=TokenLedgerService(settings),
                background_jobs=ImmediateBackgroundJobs(),
            )
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=76))

            automation.handle_sleep_coding_action_async(task.task_id, "approve_plan")

            updated_task = sleep_coding.get_task(task.task_id)
            control_task = automation.tasks.get_task(updated_task.control_task_id)
            recovery = automation.tasks.build_recovery_snapshot(control_task.task_id)
            control_events = automation.tasks.list_events(control_task.task_id)

            self.assertEqual(updated_task.background_follow_up_status, "failed")
            self.assertEqual(control_task.status, "needs_attention")
            self.assertEqual(control_task.payload["background_follow_up_status"], "failed")
            self.assertIn("simulated review follow-up timeout", control_task.payload["last_error"])
            self.assertEqual(control_task.payload["terminal_evidence"]["terminal_state"], "needs_attention")
            self.assertEqual(recovery["next_action"], "operator_attention")
            self.assertEqual(recovery["latest_event_type"], "follow_up.failed")
            self.assertTrue(
                any(event.event_type == "follow_up.failed" for event in control_events)
            )
            self.assertTrue(
                any(event.event_type == "delivery.handed_off" for event in control_events)
            )


if __name__ == "__main__":
    unittest.main()
