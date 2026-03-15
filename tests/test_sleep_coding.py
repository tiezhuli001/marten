import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings
from app.ledger.service import TokenLedgerService
from app.models.schemas import (
    GitExecutionResult,
    SleepCodingIssue,
    SleepCodingPullRequest,
    SleepCodingTaskActionRequest,
    SleepCodingTaskRequest,
    ValidationResult,
)
from app.services.channel import ChannelNotificationResult
from app.services.git_workspace import GitWorkspaceService
from app.services.github import GitHubCommentResult
from app.services.sleep_coding import SleepCodingService


class FakeGitHubService:
    def __init__(self) -> None:
        self.comments: list[str] = []
        self.labels_applied: list[tuple[int, list[str]]] = []

    def get_issue(
        self,
        repo: str,
        issue_number: int,
        title_override: str | None = None,
        body_override: str | None = None,
    ) -> SleepCodingIssue:
        return SleepCodingIssue(
            issue_number=issue_number,
            title=title_override or "Add sleep coding flow",
            body=body_override or "Need a minimal end-to-end task pipeline.",
            html_url=f"https://github.com/{repo}/issues/{issue_number}",
            is_dry_run=True,
        )

    def create_issue_comment(
        self,
        repo: str,
        issue_number: int,
        body: str,
    ) -> GitHubCommentResult:
        self.comments.append(body)
        return GitHubCommentResult(
            html_url=f"https://github.com/{repo}/issues/{issue_number}#issuecomment-1",
            is_dry_run=True,
        )

    def create_pull_request(self, repo, issue, plan, validation, head_branch, base_branch):
        return SleepCodingPullRequest(
            title=f"[Sleep Coding] #{issue.issue_number} {issue.title}",
            body="dry run pr",
            html_url=f"https://github.com/{repo}/pull/99",
            pr_number=99,
            state="open",
            is_dry_run=True,
        )

    def apply_labels(self, repo: str, issue_number: int, labels: list[str]):
        self.labels_applied.append((issue_number, labels))
        return type(
            "GitHubLabelResultStub",
            (),
            {"labels": labels, "is_dry_run": True},
        )()


class FakeChannelService:
    def __init__(self) -> None:
        self.messages: list[tuple[str, list[str]]] = []

    def notify(self, title: str, lines: list[str]) -> ChannelNotificationResult:
        self.messages.append((title, lines))
        return ChannelNotificationResult(
            provider="feishu",
            delivered=False,
            is_dry_run=True,
        )


class FakeGitWorkspaceService:
    def __init__(self) -> None:
        self.prepared_branches: list[str] = []
        self.committed_branches: list[str] = []
        self.pushed_branches: list[str] = []

    def prepare_worktree(self, branch: str) -> GitExecutionResult:
        self.prepared_branches.append(branch)
        return GitExecutionResult(
            status="prepared",
            worktree_path=f"/tmp/{branch.replace('/', '__')}",
            output="worktree prepared",
            is_dry_run=True,
        )

    def write_task_artifact(
        self,
        branch: str,
        task_id: str,
        issue_number: int,
        plan_summary: str,
    ) -> GitExecutionResult:
        return GitExecutionResult(
            status="prepared",
            worktree_path=f"/tmp/{branch.replace('/', '__')}",
            artifact_path=f"/tmp/{branch.replace('/', '__')}/.sleep_coding/issue-{issue_number}.md",
            output=plan_summary,
            is_dry_run=True,
        )

    def commit_changes(self, branch: str, message: str) -> GitExecutionResult:
        self.committed_branches.append(branch)
        return GitExecutionResult(
            status="skipped",
            worktree_path=f"/tmp/{branch.replace('/', '__')}",
            output=message,
            is_dry_run=True,
        )

    def push_branch(self, branch: str) -> GitExecutionResult:
        self.pushed_branches.append(branch)
        return GitExecutionResult(
            status="skipped",
            worktree_path=f"/tmp/{branch.replace('/', '__')}",
            push_remote="origin",
            output="push skipped",
            is_dry_run=True,
        )


class FakeValidationRunner:
    def __init__(self, status: str) -> None:
        self.status = status

    def run(self, repo_path: Path) -> ValidationResult:
        return ValidationResult(
            status=self.status,
            command="python -m unittest discover -s tests",
            exit_code=0 if self.status == "passed" else 1,
            output="validation output",
        )


def build_settings(database_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{database_path}",
        github_repository="tiezhuli001/youmeng-gateway",
        langsmith_tracing=False,
    )


class SleepCodingServiceTests(unittest.TestCase):
    def test_start_task_generates_plan_and_waits_for_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = build_settings(database_path)
            github = FakeGitHubService()
            channel = FakeChannelService()
            git_workspace = FakeGitWorkspaceService()
            service = SleepCodingService(
                settings=settings,
                github=github,
                channel=channel,
                git_workspace=git_workspace,
                validator=FakeValidationRunner("passed"),
                ledger=TokenLedgerService(settings),
            )

            task = service.start_task(SleepCodingTaskRequest(issue_number=12))

            self.assertEqual(task.status, "awaiting_confirmation")
            self.assertEqual(task.head_branch, "codex/issue-12-sleep-coding")
            self.assertIsNotNone(task.plan)
            self.assertIn("agent:ralph", task.issue.labels)
            self.assertGreaterEqual(len(task.events), 4)
            self.assertEqual(len(github.labels_applied), 1)
            self.assertEqual(len(channel.messages), 1)

    def test_approve_plan_opens_pr_after_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = build_settings(database_path)
            github = FakeGitHubService()
            channel = FakeChannelService()
            git_workspace = FakeGitWorkspaceService()
            service = SleepCodingService(
                settings=settings,
                github=github,
                channel=channel,
                git_workspace=git_workspace,
                validator=FakeValidationRunner("passed"),
                ledger=TokenLedgerService(settings),
            )
            task = service.start_task(SleepCodingTaskRequest(issue_number=18))

            updated = service.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )

            self.assertEqual(updated.status, "in_review")
            self.assertIsNotNone(updated.pull_request)
            self.assertEqual(updated.validation.status, "passed")
            self.assertEqual(updated.git_execution.status, "skipped")
            self.assertTrue(updated.git_execution.artifact_path.endswith("issue-18.md"))
            self.assertIn("codex/issue-18-sleep-coding", git_workspace.prepared_branches)
            self.assertIn("codex/issue-18-sleep-coding", git_workspace.pushed_branches)
            self.assertIn("workflow:sleep-coding", updated.pull_request.labels)
            self.assertEqual(len(github.labels_applied), 2)
            self.assertEqual(len(channel.messages), 2)

    def test_failed_validation_marks_task_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = build_settings(database_path)
            channel = FakeChannelService()
            git_workspace = FakeGitWorkspaceService()
            service = SleepCodingService(
                settings=settings,
                github=FakeGitHubService(),
                channel=channel,
                git_workspace=git_workspace,
                validator=FakeValidationRunner("failed"),
                ledger=TokenLedgerService(settings),
            )
            task = service.start_task(SleepCodingTaskRequest(issue_number=25))

            updated = service.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )

            self.assertEqual(updated.status, "failed")
            self.assertEqual(updated.validation.status, "failed")
            self.assertIsNone(updated.pull_request)
            self.assertEqual(updated.git_execution.status, "prepared")
            self.assertEqual(len(channel.messages), 2)


class GitWorkspaceServiceTests(unittest.TestCase):
    def test_dry_run_worktree_commit_push(self) -> None:
        settings = Settings(
            sleep_coding_enable_git_commit=False,
            sleep_coding_enable_git_push=False,
        )
        service = GitWorkspaceService(settings)

        prepared = service.prepare_worktree("codex/issue-1-sleep-coding")
        artifact = service.write_task_artifact(
            "codex/issue-1-sleep-coding",
            "task-1",
            1,
            "Implement Issue #1",
        )
        committed = service.commit_changes(
            "codex/issue-1-sleep-coding",
            "Sleep coding: issue #1",
        )
        pushed = service.push_branch("codex/issue-1-sleep-coding")

        self.assertEqual(prepared.status, "prepared")
        self.assertTrue(prepared.is_dry_run)
        self.assertEqual(artifact.status, "prepared")
        self.assertTrue(artifact.artifact_path.endswith("issue-1.md"))
        self.assertEqual(committed.status, "skipped")
        self.assertEqual(pushed.status, "skipped")
