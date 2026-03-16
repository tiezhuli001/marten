import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings
from app.ledger.service import TokenLedgerService
from app.models.schemas import (
    ReviewActionRequest,
    ReviewRunRequest,
    ReviewSource,
    SleepCodingIssue,
    SleepCodingPullRequest,
    SleepCodingTaskActionRequest,
    SleepCodingTaskRequest,
    ValidationResult,
)
from app.services.channel import ChannelNotificationResult
from app.services.github import GitHubCommentResult
from app.services.gitlab import GitLabService
from app.services.review import ReviewService
from app.services.sleep_coding import SleepCodingService


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
            title=f"[Sleep Coding] #{issue.issue_number} {issue.title}",
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

    def write_task_artifact(self, branch, task_id, issue_number, plan_summary):
        from app.models.schemas import GitExecutionResult

        return GitExecutionResult(
            status="prepared",
            worktree_path=f"/tmp/{branch.replace('/', '__')}",
            artifact_path=f"/tmp/{branch.replace('/', '__')}/.sleep_coding/issue-{issue_number}.md",
            output=plan_summary,
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
    def run(self, source: ReviewSource, context: str) -> tuple[str, str]:
        return (
            f"Review for {source.source_type}",
            f"## Code Review Agent\n\nSource: {source.source_type}\n\nContext:\n{context}",
        )


def build_settings(database_path: Path, review_runs_dir: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{database_path}",
        review_runs_dir=str(review_runs_dir),
        github_repository="tiezhuli001/youmeng-gateway",
        langsmith_tracing=False,
    )


class ReviewServiceTests(unittest.TestCase):
    def test_start_review_archives_local_code_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            review_service = ReviewService(
                settings=settings,
                github=FakeGitHubService(),
                gitlab=FakeGitLabService(),
                sleep_coding=SleepCodingService(
                    settings=settings,
                    github=FakeGitHubService(),
                    channel=FakeChannelService(),
                    git_workspace=FakeGitWorkspaceService(),
                    validator=FakeValidationRunner(),
                    ledger=TokenLedgerService(settings),
                ),
                skill=FakeReviewSkillService(),
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

    def test_trigger_for_sleep_coding_task_and_request_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            github = FakeGitHubService()
            sleep_coding = SleepCodingService(
                settings=settings,
                github=github,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner(),
                ledger=TokenLedgerService(settings),
            )
            task = sleep_coding.start_task(SleepCodingTaskRequest(issue_number=33))
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
            )

            review = review_service.trigger_for_task(task.task_id)
            updated_review = review_service.apply_action(
                review.review_id,
                ReviewActionRequest(action="request_changes"),
            )

            self.assertEqual(updated_review.status, "changes_requested")
            self.assertEqual(sleep_coding.get_task(task.task_id).status, "changes_requested")
            self.assertEqual(len(github.pr_comments), 1)

    def test_gitlab_url_writes_comment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "review.db", root / "review-runs")
            gitlab = FakeGitLabService()
            review_service = ReviewService(
                settings=settings,
                github=FakeGitHubService(),
                gitlab=gitlab,
                sleep_coding=SleepCodingService(
                    settings=settings,
                    github=FakeGitHubService(),
                    channel=FakeChannelService(),
                    git_workspace=FakeGitWorkspaceService(),
                    validator=FakeValidationRunner(),
                    ledger=TokenLedgerService(settings),
                ),
                skill=FakeReviewSkillService(),
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
