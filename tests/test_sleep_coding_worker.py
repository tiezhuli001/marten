import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.config import Settings
from app.ledger.service import TokenLedgerService
from app.models.schemas import (
    GitExecutionResult,
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
from app.channel.notifications import ChannelNotificationResult
from app.agents.ralph import SleepCodingService
from app.control.sleep_coding_worker import SleepCodingWorkerService


class FakeGitHubService:
    def __init__(self) -> None:
        self.labels_applied: list[tuple[int, list[str]]] = []
        self.comments: list[str] = []
        self.issues = [
            WorkerDiscoveredIssue(
                issue_number=55,
                title="Implement worker takeover",
                body="Need automatic issue polling for sleep coding.",
                html_url="https://github.com/tiezhuli001/youmeng-gateway/issues/55",
                labels=["agent:ralph", "workflow:sleep-coding"],
            ),
            WorkerDiscoveredIssue(
                issue_number=56,
                title="Ignore non-ralph issue",
                body="Should be skipped.",
                html_url="https://github.com/tiezhuli001/youmeng-gateway/issues/56",
                labels=["workflow:intake"],
            ),
        ]

    def list_open_issues(self, repo: str, labels: list[str] | None = None, limit: int = 20):
        return self.issues[:limit]

    def get_issue(self, repo: str, issue_number: int, title_override=None, body_override=None):
        return SleepCodingIssue(
            issue_number=issue_number,
            title=title_override or "Issue title",
            body=body_override or "Issue body",
            html_url=f"https://github.com/{repo}/issues/{issue_number}",
            labels=["agent:ralph", "workflow:sleep-coding"],
            is_dry_run=True,
        )

    def create_issue_comment(self, repo: str, issue_number: int, body: str):
        self.comments.append(body)
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

    def apply_labels(self, repo: str, issue_number: int, labels: list[str]):
        self.labels_applied.append((issue_number, labels))
        return type(
            "GitHubLabelResultStub",
            (),
            {"labels": labels, "is_dry_run": True},
        )()


def build_github_mcp(github: FakeGitHubService) -> MCPClient:
    client = MCPClient()
    server = InMemoryMCPServer()
    server.register_tool(
        "list_issues",
        lambda arguments: [
            {
                "number": item.issue_number,
                "title": item.title,
                "body": item.body,
                "state": item.state,
                "html_url": item.html_url,
                "labels": item.labels,
            }
            for item in github.list_open_issues(arguments["repo"], limit=arguments.get("limit", 20))
        ],
        server="github",
    )
    server.register_tool(
        "get_issue",
        lambda arguments: {
            "number": arguments["issue_number"],
            "title": github.get_issue(arguments["repo"], arguments["issue_number"]).title,
            "body": github.get_issue(arguments["repo"], arguments["issue_number"]).body,
            "state": "open",
            "html_url": github.get_issue(arguments["repo"], arguments["issue_number"]).html_url,
            "labels": ["agent:ralph", "workflow:sleep-coding"],
        },
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
    def prepare_worktree(self, branch: str) -> GitExecutionResult:
        return GitExecutionResult(
            status="prepared",
            worktree_path=f"/tmp/{branch.replace('/', '__')}",
            output="prepared",
            is_dry_run=True,
        )

    def write_task_artifact(
        self,
        branch: str,
        task_id: str,
        issue_number: int,
        artifact_markdown: str,
        file_changes=None,
    ) -> GitExecutionResult:
        return GitExecutionResult(
            status="prepared",
            worktree_path=f"/tmp/{branch.replace('/', '__')}",
            artifact_path=f"/tmp/{branch.replace('/', '__')}/.sleep_coding/issue-{issue_number}.md",
            output=artifact_markdown,
            is_dry_run=True,
        )

    def capture_worktree_evidence(self, branch: str) -> GitExecutionResult:
        worktree_path = f"/tmp/{branch.replace('/', '__')}"
        changed_files = [
            ".sleep_coding/issue-artifact.md",
            "tests/generated_test.py",
        ]
        return GitExecutionResult(
            status="prepared",
            worktree_path=worktree_path,
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

    def commit_changes(self, branch: str, message: str) -> GitExecutionResult:
        return GitExecutionResult(
            status="skipped",
            worktree_path=f"/tmp/{branch.replace('/', '__')}",
            output=message,
            is_dry_run=True,
        )

    def push_branch(self, branch: str) -> GitExecutionResult:
        return GitExecutionResult(
            status="skipped",
            worktree_path=f"/tmp/{branch.replace('/', '__')}",
            push_remote="origin",
            output="push skipped",
            is_dry_run=True,
        )

    def cleanup_worktree(self, branch: str) -> None:
        return None


class FakeValidationRunner:
    def __init__(self, status: str = "passed") -> None:
        self.status = status

    def run(self, repo_path: Path) -> ValidationResult:
        return ValidationResult(
            status=self.status,
            command="python -m unittest discover -s tests",
            exit_code=0 if self.status == "passed" else 1,
            output="ok" if self.status == "passed" else "failed",
        )


class FailingSleepCodingService:
    def __init__(self) -> None:
        self.calls = 0

    def start_task(self, payload):
        self.calls += 1
        raise RuntimeError("simulated worker failure")


class FailOnApproveSleepCodingService:
    def __init__(self, base: SleepCodingService) -> None:
        self.base = base

    def start_task(self, payload):
        return self.base.start_task(payload)

    def apply_action(self, task_id, payload):
        raise RuntimeError("simulated approve_plan failure")

    def get_task(self, task_id):
        return self.base.get_task(task_id)


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


def build_settings(database_path: Path, *, auto_approve_plan: bool = False) -> Settings:
    platform_path = database_path.parent / "platform.json"
    models_path = database_path.parent / "models.json"
    platform_path.write_text(
        (
            '{'
            '"github":{"repository":"tiezhuli001/youmeng-gateway"},'
            '"channel":{"provider":"feishu"},'
            f'"sleep_coding":{{"worker":{{"auto_approve_plan":{str(auto_approve_plan).lower()},"scheduler_enabled":false}}}}'
            '}'
        ),
        encoding="utf-8",
    )
    if not models_path.exists():
        models_path.write_text("{}", encoding="utf-8")
    return Settings(
        app_env="test",
        database_url=f"sqlite:///{database_path}",
        github_repository="tiezhuli001/youmeng-gateway",
        platform_config_path=str(platform_path),
        models_config_path=str(models_path),
        langsmith_tracing=False,
        openai_api_key="test-key",
        minimax_api_key=None,
    )


def build_sleep_coding_service(settings: Settings, mcp_client: MCPClient) -> SleepCodingService:
    return SleepCodingService(
        settings=settings,
        channel=FakeChannelService(),
        git_workspace=FakeGitWorkspaceService(),
        validator=FakeValidationRunner(),
        ledger=TokenLedgerService(settings),
        agent_runtime=FakeRalphAgentRuntime(),
        mcp_client=mcp_client,
    )


class SleepCodingWorkerServiceTests(unittest.TestCase):
    def test_poll_once_creates_task_for_eligible_issue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "worker.db")
            github = FakeGitHubService()
            mcp_client = build_github_mcp(github)
            sleep_coding = build_sleep_coding_service(settings, mcp_client)
            worker = SleepCodingWorkerService(
                settings=settings,
                mcp_client=mcp_client,
                sleep_coding=sleep_coding,
            )
            worker.tasks.create_task(
                task_type="main_agent_intake",
                agent_id="main-agent",
                status="issue_created",
                user_id="user-1",
                source="manual",
                repo="tiezhuli001/youmeng-gateway",
                issue_number=55,
                title="Implement worker takeover",
                external_ref="github_issue:tiezhuli001/youmeng-gateway#55",
                payload={"request_id": "req-55"},
            )

            result = worker.poll_once()

            self.assertEqual(result.discovered_count, 2)
            self.assertEqual(result.claimed_count, 1)
            self.assertEqual(result.tasks[0].issue_number, 55)
            self.assertEqual(result.tasks[0].status, "awaiting_confirmation")
            self.assertEqual(result.tasks[0].kickoff_request_id, "req-55")
            self.assertEqual(result.claims[0].issue_number, 56)
            self.assertEqual(result.claims[0].status, "skipped")

    def test_poll_once_can_auto_approve_plan_into_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "worker.db")
            github = FakeGitHubService()
            mcp_client = build_github_mcp(github)
            sleep_coding = build_sleep_coding_service(settings, mcp_client)
            worker = SleepCodingWorkerService(
                settings=settings,
                mcp_client=mcp_client,
                sleep_coding=sleep_coding,
            )

            result = worker.poll_once(
                SleepCodingWorkerPollRequest(auto_approve_plan=True)
            )

            self.assertEqual(result.claimed_count, 1)
            self.assertEqual(result.tasks[0].status, "in_review")
            self.assertIsNotNone(result.tasks[0].pull_request)

    def test_poll_once_does_not_duplicate_existing_active_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "worker.db")
            github = FakeGitHubService()
            mcp_client = build_github_mcp(github)
            sleep_coding = build_sleep_coding_service(settings, mcp_client)
            sleep_coding.start_task(
                SleepCodingTaskRequest(
                    issue_number=55,
                    repo="tiezhuli001/youmeng-gateway",
                    issue_title="Implement worker takeover",
                    issue_body="Need automatic issue polling for sleep coding.",
                )
            )
            worker = SleepCodingWorkerService(
                settings=settings,
                mcp_client=mcp_client,
                sleep_coding=sleep_coding,
            )

            result = worker.poll_once()

            self.assertEqual(result.claimed_count, 0)
            active_claim = next(claim for claim in result.claims if claim.issue_number == 55)
            self.assertEqual(active_claim.status, "awaiting_confirmation")

    def test_poll_once_skips_issue_when_active_control_task_exists_without_domain_row(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "worker.db")
            github = FakeGitHubService()
            mcp_client = build_github_mcp(github)
            worker = SleepCodingWorkerService(
                settings=settings,
                mcp_client=mcp_client,
            )
            worker.tasks.create_task(
                task_type="sleep_coding",
                agent_id="ralph",
                status="coding",
                repo="tiezhuli001/youmeng-gateway",
                issue_number=55,
                title="Implement worker takeover",
                external_ref="sleep_coding_task:control-only-55",
                payload={"head_branch": "codex/issue-55-sleep-coding"},
            )

            result = worker.poll_once()

            self.assertEqual(result.claimed_count, 0)
            active_claim = next(claim for claim in result.claims if claim.issue_number == 55)
            self.assertEqual(active_claim.status, "coding")

    def test_poll_once_records_retry_state_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "worker.db")
            github = FakeGitHubService()
            mcp_client = build_github_mcp(github)
            worker = SleepCodingWorkerService(
                settings=settings,
                mcp_client=mcp_client,
                sleep_coding=FailingSleepCodingService(),  # type: ignore[arg-type]
            )

            result = worker.poll_once()

            self.assertEqual(result.claimed_count, 0)
            failing_claim = next(claim for claim in result.claims if claim.issue_number == 55)
            self.assertEqual(failing_claim.status, "retrying")
            self.assertEqual(failing_claim.retry_count, 1)
            self.assertIn("simulated worker failure", failing_claim.last_error or "")

    def test_poll_once_stops_retrying_after_max_retries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "worker.db").model_copy(
                update={"sleep_coding_worker_max_retries": 1}
            )
            github = FakeGitHubService()
            mcp_client = build_github_mcp(github)
            worker = SleepCodingWorkerService(
                settings=settings,
                mcp_client=mcp_client,
                sleep_coding=FailingSleepCodingService(),  # type: ignore[arg-type]
            )

            first = worker.poll_once()
            with worker._connect() as connection:
                connection.execute(
                    """
                    UPDATE sleep_coding_issue_claims
                    SET next_retry_at = ?
                    WHERE repo = ? AND issue_number = ?
                    """,
                    ((datetime.now(UTC) - timedelta(minutes=5)).isoformat(), "tiezhuli001/youmeng-gateway", 55),
                )
                connection.commit()
            second = worker.poll_once()

            self.assertEqual(first.claimed_count, 0)
            failing_claim = next(claim for claim in second.claims if claim.issue_number == 55)
            self.assertEqual(failing_claim.status, "failed")
            self.assertEqual(failing_claim.retry_count, 2)
            self.assertIn("simulated worker failure", failing_claim.last_error or "")

    def test_poll_once_binds_task_to_claim_when_auto_approve_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "worker.db")
            github = FakeGitHubService()
            mcp_client = build_github_mcp(github)
            base_sleep_coding = build_sleep_coding_service(settings, mcp_client)
            worker = SleepCodingWorkerService(
                settings=settings,
                mcp_client=mcp_client,
                sleep_coding=FailOnApproveSleepCodingService(base_sleep_coding),  # type: ignore[arg-type]
            )

            result = worker.poll_once(SleepCodingWorkerPollRequest(auto_approve_plan=True))

            self.assertEqual(result.claimed_count, 0)
            claim = next(claim for claim in result.claims if claim.issue_number == 55)
            self.assertIsNotNone(claim.task_id)
            self.assertEqual(claim.status, "awaiting_confirmation")
            self.assertIn("simulated approve_plan failure", claim.last_error or "")

    def test_poll_once_uses_mcp_for_issue_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "worker.db")
            mcp_client = MCPClient()
            server = InMemoryMCPServer()
            server.register_tool(
                "list_issues",
                lambda arguments: {
                    "issues": [
                        {
                            "number": 77,
                            "title": "MCP discovered issue",
                            "body": "Found through MCP.",
                            "state": "OPEN",
                            "labels": ["agent:ralph", "workflow:sleep-coding"],
                            "html_url": "https://github.com/tiezhuli001/youmeng-gateway/issues/77",
                        }
                    ]
                },
                server="github",
            )
            mcp_client.register_adapter("github", server)
            sleep_coding = build_sleep_coding_service(
                settings,
                build_github_mcp(FakeGitHubService()),
            )
            worker = SleepCodingWorkerService(
                settings=settings,
                mcp_client=mcp_client,
                sleep_coding=sleep_coding,
            )

            result = worker.poll_once()

            self.assertEqual(result.claimed_count, 1)
            self.assertEqual(result.tasks[0].issue_number, 77)

    def test_expire_stale_claim_marks_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "worker.db")
            github = FakeGitHubService()
            mcp_client = build_github_mcp(github)
            sleep_coding = build_sleep_coding_service(settings, mcp_client)
            worker = SleepCodingWorkerService(
                settings=settings,
                mcp_client=mcp_client,
                sleep_coding=sleep_coding,
            )
            worker.poll_once()
            stale_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
            with worker._connect() as connection:
                connection.execute(
                    """
                    UPDATE sleep_coding_issue_claims
                    SET status = 'claimed', lease_expires_at = ?, last_heartbeat_at = ?
                    WHERE repo = ? AND issue_number = ?
                    """,
                    (stale_time, stale_time, "tiezhuli001/youmeng-gateway", 55),
                )
                connection.commit()

            second = worker.poll_once()
            stale_claim = next(claim for claim in second.claims if claim.issue_number == 55)
            self.assertEqual(stale_claim.status, "awaiting_confirmation")

    def test_list_claims_syncs_terminal_task_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "worker.db")
            github = FakeGitHubService()
            mcp_client = build_github_mcp(github)
            sleep_coding = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner("failed"),
                ledger=TokenLedgerService(settings),
                agent_runtime=FakeRalphAgentRuntime(),
                mcp_client=mcp_client,
            )
            worker = SleepCodingWorkerService(
                settings=settings,
                mcp_client=mcp_client,
                sleep_coding=sleep_coding,
            )

            result = worker.poll_once()
            task = result.tasks[0]
            sleep_coding.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )
            claims = worker.list_claims()
            synced_claim = next(claim for claim in claims if claim.issue_number == 55)

            self.assertEqual(synced_claim.status, "failed")
            self.assertIn("Local validation failed.", synced_claim.last_error or "")

    def test_list_claims_rebinds_issue_to_latest_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_settings(Path(temp_dir) / "worker.db")
            github = FakeGitHubService()
            mcp_client = build_github_mcp(github)
            sleep_coding = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner("failed"),
                ledger=TokenLedgerService(settings),
                agent_runtime=FakeRalphAgentRuntime(),
                mcp_client=mcp_client,
            )
            worker = SleepCodingWorkerService(
                settings=settings,
                mcp_client=mcp_client,
                sleep_coding=sleep_coding,
            )

            first = worker.poll_once()
            failed_task = first.tasks[0]
            sleep_coding.apply_action(
                failed_task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )
            replacement_task = sleep_coding.start_task(
                SleepCodingTaskRequest(
                    issue_number=55,
                    repo="tiezhuli001/youmeng-gateway",
                    issue_title="Implement worker takeover",
                    issue_body="Need automatic issue polling for sleep coding.",
                    head_branch="codex/issue-55-retry",
                )
            )

            claims = worker.list_claims()
            synced_claim = next(claim for claim in claims if claim.issue_number == 55)

            self.assertEqual(synced_claim.task_id, replacement_task.task_id)
            self.assertEqual(synced_claim.status, replacement_task.status)


if __name__ == "__main__":
    unittest.main()
