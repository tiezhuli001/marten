import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.core.config import Settings
from app.ledger.service import TokenLedgerService
from app.models.github_results import GitHubCommentResult
from app.models.schemas import (
    GitExecutionResult,
    RalphCodingArtifact,
    RalphReviewHandoff,
    SleepCodingIssue,
    SleepCodingPlan,
    SleepCodingPullRequest,
    SleepCodingTaskActionRequest,
    SleepCodingTaskRequest,
    TokenUsage,
    ValidationResult,
)
from app.runtime.mcp import InMemoryMCPServer, MCPClient, MCPTool, MCPToolResult
from app.channel.notifications import ChannelNotificationResult
from app.infra.git_workspace import GitWorkspaceService
from app.agents.ralph.github_bridge import RalphGitHubBridge
from app.agents.ralph import SleepCodingService, ValidationRunner
from app.agents.ralph.drafting import RalphDraftingService


class FakeGitHubService:
    def __init__(self) -> None:
        self.comments: list[str] = []
        self.labels_applied: list[tuple[int, list[str]]] = []
        self.created_prs: list[tuple[str, str, str]] = []

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
        self.created_prs.append((repo, head_branch, base_branch))
        return SleepCodingPullRequest(
            title=f"[Ralph] #{issue.issue_number} {issue.title}",
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
        lambda arguments: github.created_prs.append(
            (arguments["repo"], arguments["head_branch"], arguments["base_branch"])
        ) or {
            "title": arguments["title"],
            "body": arguments["body"],
            "html_url": f"https://github.com/{arguments['repo']}/pull/99",
            "number": 99,
            "state": "open",
        },
        server="github",
    )
    client.register_adapter("github", server)
    return client


class FakeChannelService:
    def __init__(self) -> None:
        self.messages: list[tuple[str, list[str], str | None]] = []

    def notify(
        self,
        title: str,
        lines: list[str],
        endpoint_id: str | None = None,
    ) -> ChannelNotificationResult:
        self.messages.append((title, lines, endpoint_id))
        return ChannelNotificationResult(
            provider="feishu",
            delivered=False,
            is_dry_run=True,
            endpoint_id=endpoint_id,
        )


class FakeGitWorkspaceService:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root
        self.prepared_branches: list[str] = []
        self.committed_branches: list[str] = []
        self.pushed_branches: list[str] = []
        self.cleaned_branches: list[str] = []

    def _worktree_path(self, branch: str) -> Path:
        if self.root is not None:
            return self.root / branch.replace("/", "__")
        return Path(f"/tmp/{branch.replace('/', '__')}")

    def prepare_worktree(self, branch: str) -> GitExecutionResult:
        self.prepared_branches.append(branch)
        worktree_path = self._worktree_path(branch)
        worktree_path.mkdir(parents=True, exist_ok=True)
        return GitExecutionResult(
            status="prepared",
            worktree_path=str(worktree_path),
            output="worktree prepared",
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
        worktree_path = self._worktree_path(branch)
        artifact_path = worktree_path / ".sleep_coding" / f"issue-{issue_number}.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(artifact_markdown, encoding="utf-8")
        return GitExecutionResult(
            status="prepared",
            worktree_path=str(worktree_path),
            artifact_path=str(artifact_path),
            output=artifact_markdown,
            is_dry_run=True,
        )

    def commit_changes(self, branch: str, message: str) -> GitExecutionResult:
        self.committed_branches.append(branch)
        return GitExecutionResult(
            status="skipped",
            worktree_path=str(self._worktree_path(branch)),
            output=message,
            is_dry_run=True,
        )

    def push_branch(self, branch: str) -> GitExecutionResult:
        self.pushed_branches.append(branch)
        return GitExecutionResult(
            status="skipped",
            worktree_path=str(self._worktree_path(branch)),
            push_remote="origin",
            output="push skipped",
            is_dry_run=True,
        )

    def cleanup_worktree(self, branch: str) -> None:
        self.cleaned_branches.append(branch)


class FakeValidationRunner:
    def __init__(self, status: str) -> None:
        self.status = status
        self.calls = 0

    def run(self, repo_path: Path) -> ValidationResult:
        self.calls += 1
        return ValidationResult(
            status=self.status,
            command="python -m unittest discover -s tests",
            exit_code=0 if self.status == "passed" else 1,
            output="validation output",
        )


class FakeAgentRuntime:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.mcp = MCPClient()

    def generate_structured_output(self, agent, *, user_prompt, output_contract, **kwargs):
        self.calls.append(output_contract)
        if "artifact_markdown" in output_contract:
            content = (
                '{"artifact_markdown":"## Summary\\nGenerated coding draft",'
                '"commit_message":"feat: implement sleep coding task",'
                '"file_changes":[{"path":"tests/generated_test.py","content":"print(\\"ok\\")","description":"generated test"}]}'
            )
        else:
            content = (
                '{"summary":"LLM generated plan","scope":["Update service code","Add tests"],'
                '"validation":["python -m unittest discover -s tests"],'
                '"risks":["Issue details may still need clarification."]}'
            )
        return type(
            "FakeLLMResponse",
            (),
            {
                "output_text": content,
                "usage": type(
                    "FakeUsage",
                    (),
                    {
                        "prompt_tokens": 11,
                        "completion_tokens": 13,
                        "total_tokens": 24,
                        "cache_read_tokens": 0,
                        "cache_write_tokens": 0,
                        "reasoning_tokens": 0,
                        "message_count": 2,
                        "duration_seconds": 0.0,
                        "model_name": "test-model",
                        "provider": "openai",
                        "cost_usd": 0.0,
                        "step_name": None,
                        "model_copy": lambda self, update=None: self,
                    },
                )(),
            },
        )()


class FailingAgentRuntime(FakeAgentRuntime):
    def generate_structured_output(self, agent, *, user_prompt, output_contract, **kwargs):
        raise RuntimeError("LLM provider is unreachable")


class ListSummaryAgentRuntime(FakeAgentRuntime):
    def generate_structured_output(self, agent, *, user_prompt, output_contract, **kwargs):
        self.calls.append(output_contract)
        return type(
            "FakeLLMResponse",
            (),
            {
                "output_text": (
                    '{"summary":["Add the smoke note file.","Keep the change minimal."],'
                    '"scope":["Create docs/e2e-real-chain-smoke.md"],'
                    '"validation":["python -m unittest discover -s tests"],'
                    '"risks":["None."]}'
                ),
                "usage": type(
                    "FakeUsage",
                    (),
                    {
                        "prompt_tokens": 11,
                        "completion_tokens": 13,
                        "total_tokens": 24,
                        "cache_read_tokens": 0,
                        "cache_write_tokens": 0,
                        "reasoning_tokens": 0,
                        "message_count": 2,
                        "duration_seconds": 0.0,
                        "model_name": "test-model",
                        "provider": "openai",
                        "cost_usd": 0.0,
                        "step_name": None,
                        "model_copy": lambda self, update=None: self,
                    },
                )(),
            },
        )()


class WrappedJsonPlanAgentRuntime(FakeAgentRuntime):
    def generate_structured_output(self, agent, *, user_prompt, output_contract, **kwargs):
        self.calls.append(output_contract)
        return type(
            "FakeLLMResponse",
            (),
            {
                "output_text": (
                    "<think>\nPlan the task first.\n</think>\n\n"
                    '{"summary":"LLM generated plan","scope":["Update service code","Add tests"],'
                    '"validation":["python scripts/run_sleep_coding_validation.py"],'
                    '"risks":["Issue details may still need clarification."]}'
                ),
                "usage": type(
                    "FakeUsage",
                    (),
                    {
                        "prompt_tokens": 11,
                        "completion_tokens": 13,
                        "total_tokens": 24,
                        "cache_read_tokens": 0,
                        "cache_write_tokens": 0,
                        "reasoning_tokens": 0,
                        "message_count": 2,
                        "duration_seconds": 0.0,
                        "model_name": "test-model",
                        "provider": "openai",
                        "cost_usd": 0.0,
                        "step_name": None,
                        "model_copy": lambda self, update=None: self,
                    },
                )(),
            },
        )()


class HashRocketPlanAgentRuntime(FakeAgentRuntime):
    def generate_structured_output(self, agent, *, user_prompt, output_contract, **kwargs):
        self.calls.append(output_contract)
        return type(
            "FakeLLMResponse",
            (),
            {
                "output_text": (
                    '{summary => "LLM generated plan", '
                    'scope => ["Update service code", "Add tests"], '
                    'validation => ["python scripts/run_sleep_coding_validation.py"], '
                    'risks => ["Issue details may still need clarification."]}'
                ),
                "usage": type(
                    "FakeUsage",
                    (),
                    {
                        "prompt_tokens": 11,
                        "completion_tokens": 13,
                        "total_tokens": 24,
                        "cache_read_tokens": 0,
                        "cache_write_tokens": 0,
                        "reasoning_tokens": 0,
                        "message_count": 2,
                        "duration_seconds": 0.0,
                        "model_name": "test-model",
                        "provider": "openai",
                        "cost_usd": 0.0,
                        "step_name": None,
                        "model_copy": lambda self, update=None: self,
                    },
                )(),
            },
        )()


class InvalidPlanAgentRuntime(FakeAgentRuntime):
    def generate_structured_output(self, agent, *, user_prompt, output_contract, **kwargs):
        self.calls.append(output_contract)
        return type(
            "FakeLLMResponse",
            (),
            {
                "output_text": "Plan: update docs and add tests.",
                "usage": type(
                    "FakeUsage",
                    (),
                    {
                        "prompt_tokens": 11,
                        "completion_tokens": 13,
                        "total_tokens": 24,
                        "cache_read_tokens": 0,
                        "cache_write_tokens": 0,
                        "reasoning_tokens": 0,
                        "message_count": 2,
                        "duration_seconds": 0.0,
                        "model_name": "test-model",
                        "provider": "openai",
                        "cost_usd": 0.0,
                        "step_name": None,
                        "model_copy": lambda self, update=None: self,
                    },
                )(),
            },
        )()


class InvalidExecutionAgentRuntime(FakeAgentRuntime):
    def generate_structured_output(self, agent, *, user_prompt, output_contract, **kwargs):
        self.calls.append(output_contract)
        if "artifact_markdown" in output_contract:
            output_text = "Draft: touch docs and keep the change minimal."
        else:
            output_text = (
                '{"summary":"LLM generated plan","scope":["Update docs"],'
                '"validation":["python -m unittest discover -s tests"],'
                '"risks":["Issue details may still need clarification."]}'
            )
        return type(
            "FakeLLMResponse",
            (),
            {
                "output_text": output_text,
                "usage": type(
                    "FakeUsage",
                    (),
                    {
                        "prompt_tokens": 11,
                        "completion_tokens": 13,
                        "total_tokens": 24,
                        "cache_read_tokens": 0,
                        "cache_write_tokens": 0,
                        "reasoning_tokens": 0,
                        "message_count": 2,
                        "duration_seconds": 0.0,
                        "model_name": "test-model",
                        "provider": "openai",
                        "cost_usd": 0.0,
                        "step_name": None,
                        "model_copy": lambda self, update=None: self,
                    },
                )(),
            },
        )()


def build_settings(database_path: Path, **kwargs) -> Settings:
    platform_config_path = database_path.parent / "platform.json"
    if not platform_config_path.exists():
        platform_config_path.write_text("{}", encoding="utf-8")
    return Settings(
        app_env="test",
        database_url=f"sqlite:///{database_path}",
        platform_config_path=str(platform_config_path),
        github_repository="tiezhuli001/youmeng-gateway",
        langsmith_tracing=False,
        openai_api_key="test-key",
        minimax_api_key=None,
        **kwargs,
    )


class SleepCodingServiceTests(unittest.TestCase):
    def test_sleep_coding_emits_structured_handoff_and_execution_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_settings(root / "sleep_coding.db")
            github = FakeGitHubService()
            service = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(root=root / "worktrees"),
                validator=FakeValidationRunner("passed"),
                ledger=TokenLedgerService(settings),
                agent_runtime=FakeAgentRuntime(),
                mcp_client=build_github_mcp(github),
            )

            task = service.start_task(SleepCodingTaskRequest(issue_number=12))
            task = service.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )
            control_task = service.tasks.get_task(task.control_task_id)

            self.assertEqual(control_task.payload["handoff"]["owner_agent"], "ralph")
            coding_artifact = RalphCodingArtifact.model_validate(control_task.payload["coding_artifact"])
            review_handoff = RalphReviewHandoff.model_validate(control_task.payload["review_handoff"])
            self.assertTrue(coding_artifact.generated_files)
            self.assertEqual(review_handoff.next_owner_agent, "code-review-agent")
            coding_event = next(event for event in task.events if event.event_type == "coding_draft_generated")
            event_artifact = RalphCodingArtifact.model_validate(coding_event.payload["artifact"])
            self.assertTrue(event_artifact.file_changes)

    def test_build_plan_normalizes_summary_list_from_llm_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = build_settings(database_path)
            github = FakeGitHubService()
            service = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner("passed"),
                agent_runtime=ListSummaryAgentRuntime(),
                mcp_client=build_github_mcp(github),
            )
            issue = SleepCodingIssue(
                issue_number=62,
                title="Add minimal real-chain smoke note file",
                body="Add docs/e2e-real-chain-smoke.md",
                html_url="https://github.com/tiezhuli001/youmeng-gateway/issues/62",
            )

            plan, _ = service._build_plan(issue)

            self.assertEqual(
                plan.summary,
                "Add the smoke note file. Keep the change minimal.",
            )

    def test_build_plan_accepts_json_wrapped_in_think_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = build_settings(database_path)
            github = FakeGitHubService()
            service = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner("passed"),
                agent_runtime=WrappedJsonPlanAgentRuntime(),
                mcp_client=build_github_mcp(github),
            )
            issue = SleepCodingIssue(
                issue_number=63,
                title="Add minimal real-chain smoke note file for MiniMax validation",
                body="Add docs/e2e-real-chain-smoke-minimax.md",
                html_url="https://github.com/tiezhuli001/youmeng-gateway/issues/63",
            )

            plan, _ = service._build_plan(issue)

            self.assertEqual(plan.summary, "LLM generated plan")

    def test_build_plan_accepts_hash_rocket_wrapped_object(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = build_settings(database_path)
            github = FakeGitHubService()
            service = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner("passed"),
                agent_runtime=HashRocketPlanAgentRuntime(),
                mcp_client=build_github_mcp(github),
            )
            issue = SleepCodingIssue(
                issue_number=64,
                title="Add hash rocket plan parsing coverage",
                body="Add docs/e2e-real-chain-smoke-minimax.md",
                html_url="https://github.com/tiezhuli001/youmeng-gateway/issues/64",
            )

            plan, _ = service._build_plan(issue)

            self.assertEqual(plan.summary, "LLM generated plan")

    def test_build_plan_falls_back_to_heuristic_when_provider_output_is_not_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = build_settings(database_path)
            github = FakeGitHubService()
            service = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner("passed"),
                agent_runtime=InvalidPlanAgentRuntime(),
                mcp_client=build_github_mcp(github),
            )
            issue = SleepCodingIssue(
                issue_number=65,
                title="Add live chain validation marker",
                body="Touch docs/internal/live-chain-validation.md",
                html_url="https://github.com/tiezhuli001/youmeng-gateway/issues/65",
            )

            plan, usage = service._build_plan(issue)

            self.assertEqual(plan.summary, "Implement Issue #65: Add live chain validation marker")
            self.assertEqual(usage.total_tokens, 24)

    def test_heuristic_execution_draft_updates_live_chain_validation_doc_when_issue_targets_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = build_settings(database_path)
            github = FakeGitHubService()
            service = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner("passed"),
                agent_runtime=FakeAgentRuntime(),
                mcp_client=build_github_mcp(github),
            )
            repo_path = Path(temp_dir) / "repo"
            target = repo_path / "docs" / "internal" / "live-chain-validation.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# Live Chain Validation\n", encoding="utf-8")
            service.repo_path = repo_path
            service.drafting.repo_path = repo_path
            issue = SleepCodingIssue(
                issue_number=56,
                title="Add live chain validation marker",
                body="Please append a dated marker to docs/internal/live-chain-validation.md.",
                html_url="https://github.com/tiezhuli001/youmeng-gateway/issues/56",
            )

            draft = service._build_heuristic_execution_draft(
                issue,
                service._build_heuristic_plan(issue),
                "codex/issue-56-sleep-coding",
            )

            self.assertEqual(len(draft.file_changes), 1)
            self.assertEqual(draft.file_changes[0].path, "docs/internal/live-chain-validation.md")
            self.assertIn("live validation marker:", draft.file_changes[0].content)
            self.assertIn("<!-- ralph-e2e-issue-56 -->", draft.file_changes[0].content)

    def test_heuristic_execution_draft_adds_readme_change_when_issue_mentions_readme(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = build_settings(database_path)
            github = FakeGitHubService()
            service = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner("passed"),
                agent_runtime=FakeAgentRuntime(),
                mcp_client=build_github_mcp(github),
            )
            repo_path = Path(temp_dir) / "repo"
            repo_path.mkdir()
            (repo_path / "README.md").write_text("# Demo\n", encoding="utf-8")
            service.repo_path = repo_path
            issue = SleepCodingIssue(
                issue_number=101,
                title="Update README with MVP marker",
                body="Please add a README note for integration validation.",
                html_url="https://github.com/tiezhuli001/youmeng-gateway/issues/101",
            )

            draft = service._build_heuristic_execution_draft(
                issue,
                service._build_heuristic_plan(issue),
                "codex/issue-101-sleep-coding",
            )

            self.assertEqual(len(draft.file_changes), 1)
            self.assertEqual(draft.file_changes[0].path, "README.md")
            self.assertIn("<!-- ralph-e2e-issue-101 -->", draft.file_changes[0].content)

    def test_start_task_generates_plan_and_waits_for_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = build_settings(database_path)
            github = FakeGitHubService()
            channel = FakeChannelService()
            git_workspace = FakeGitWorkspaceService()
            agent_runtime = FakeAgentRuntime()
            service = SleepCodingService(
                settings=settings,
                channel=channel,
                git_workspace=git_workspace,
                validator=FakeValidationRunner("passed"),
                ledger=TokenLedgerService(settings),
                agent_runtime=agent_runtime,
                mcp_client=build_github_mcp(github),
            )

            task = service.start_task(SleepCodingTaskRequest(issue_number=12))

            self.assertEqual(task.status, "awaiting_confirmation")
            self.assertEqual(task.head_branch, "codex/issue-12-sleep-coding")
            self.assertIsNotNone(task.plan)
            self.assertEqual(task.plan.summary, "LLM generated plan")
            self.assertIn("agent:ralph", task.issue.labels)
            self.assertGreaterEqual(len(task.events), 4)
            self.assertEqual(len(github.labels_applied), 1)
            self.assertEqual(len(channel.messages), 1)
            self.assertEqual(len(agent_runtime.calls), 1)

    def test_approve_plan_opens_pr_after_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = build_settings(database_path)
            github = FakeGitHubService()
            channel = FakeChannelService()
            git_workspace = FakeGitWorkspaceService()
            agent_runtime = FakeAgentRuntime()
            service = SleepCodingService(
                settings=settings,
                channel=channel,
                git_workspace=git_workspace,
                validator=FakeValidationRunner("passed"),
                ledger=TokenLedgerService(settings),
                agent_runtime=agent_runtime,
                mcp_client=build_github_mcp(github),
            )
            task = service.start_task(SleepCodingTaskRequest(issue_number=18))

            updated = service.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )

            self.assertEqual(updated.status, "in_review")

    def test_approve_plan_falls_back_to_heuristic_execution_when_provider_output_is_not_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = build_settings(database_path)
            github = FakeGitHubService()
            channel = FakeChannelService()
            git_workspace = FakeGitWorkspaceService()
            service = SleepCodingService(
                settings=settings,
                channel=channel,
                git_workspace=git_workspace,
                validator=FakeValidationRunner("passed"),
                ledger=TokenLedgerService(settings),
                agent_runtime=InvalidExecutionAgentRuntime(),
                mcp_client=build_github_mcp(github),
            )
            task = service.start_task(SleepCodingTaskRequest(issue_number=66))

            updated = service.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )

            self.assertEqual(updated.status, "in_review")
            self.assertIsNotNone(updated.pull_request)

    def test_approve_plan_prefers_local_execution_command_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database_path = root / "sleep_coding.db"
            runner = root / "fake_coding_runner.py"
            runner.write_text(
                "\n".join(
                    [
                        "import json",
                        "import pathlib",
                        "import sys",
                        "",
                        "repo = pathlib.Path.cwd()",
                        "(repo / 'generated.txt').write_text('local-first execution\\n', encoding='utf-8')",
                        "print(json.dumps({",
                        "  'artifact_markdown': '## Summary\\nExecuted local coding command',",
                        "  'commit_message': 'feat: local-first coding command'",
                        "}))",
                    ]
                ),
                encoding="utf-8",
            )
            settings = build_settings(
                database_path,
                sleep_coding_execution_command=f"python {runner}",
            )
            github = FakeGitHubService()
            git_workspace = FakeGitWorkspaceService(root / "worktrees")
            agent_runtime = FakeAgentRuntime()
            service = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=git_workspace,
                validator=FakeValidationRunner("passed"),
                ledger=TokenLedgerService(settings),
                agent_runtime=agent_runtime,
                mcp_client=build_github_mcp(github),
            )
            task = service.start_task(SleepCodingTaskRequest(issue_number=20))

            updated = service.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )

            self.assertEqual(updated.status, "in_review")
            worktree = root / "worktrees" / "codex__issue-20-sleep-coding"
            self.assertTrue((worktree / "generated.txt").exists())
            self.assertEqual(len(agent_runtime.calls), 1)
    
    def test_start_and_approve_plan_append_usage_to_kickoff_request(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = build_settings(database_path)
            ledger = TokenLedgerService(settings)
            github = FakeGitHubService()
            ledger.record_request(
                request_id="req-42",
                run_id="run-42",
                user_id="user-42",
                source="manual",
                intent="sleep_coding",
                content="issue 42",
                usage=TokenUsage(
                    prompt_tokens=3,
                    completion_tokens=2,
                    total_tokens=5,
                    message_count=1,
                    duration_seconds=0.5,
                    step_name="main_agent_issue_intake",
                ),
            )
            service = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner("passed"),
                ledger=ledger,
                agent_runtime=FakeAgentRuntime(),
                mcp_client=build_github_mcp(github),
            )

            task = service.start_task(
                SleepCodingTaskRequest(issue_number=42, request_id="req-42")
            )
            service.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )

            usage = ledger.get_request_usage("req-42")
            plan_usage = ledger.get_request_usage("req-42", ["sleep_coding_plan"])

            self.assertIsNone(usage.step_name)
            self.assertGreater(usage.prompt_tokens, 3)
            self.assertGreater(usage.completion_tokens, 2)
            self.assertGreater(usage.total_tokens, 5)
            self.assertGreaterEqual(usage.message_count, 5)
            self.assertEqual(plan_usage.step_name, "sleep_coding_plan")
            self.assertGreater(plan_usage.total_tokens, 0)

    def test_start_task_inherits_request_id_from_parent_control_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = build_settings(database_path)
            ledger = TokenLedgerService(settings)
            github = FakeGitHubService()
            ledger.record_request(
                request_id="req-parent-42",
                run_id="run-parent-42",
                user_id="user-42",
                source="manual",
                intent="sleep_coding",
                content="issue 42",
                usage=TokenUsage(
                    prompt_tokens=3,
                    completion_tokens=2,
                    total_tokens=5,
                    message_count=1,
                    duration_seconds=0.5,
                    step_name="main_agent_issue_intake",
                ),
            )
            service = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner("passed"),
                ledger=ledger,
                agent_runtime=FakeAgentRuntime(),
                mcp_client=build_github_mcp(github),
            )
            service.tasks.create_task(
                task_type="main_agent_intake",
                agent_id="main-agent",
                status="issue_created",
                user_id="user-42",
                source="manual",
                repo="tiezhuli001/youmeng-gateway",
                issue_number=42,
                title="Parent intake task",
                external_ref="github_issue:tiezhuli001/youmeng-gateway#42",
                payload={"request_id": "req-parent-42"},
            )

            task = service.start_task(SleepCodingTaskRequest(issue_number=42))

            self.assertEqual(task.kickoff_request_id, "req-parent-42")
            plan_usage = ledger.get_request_usage("req-parent-42", ["sleep_coding_plan"])
            self.assertGreater(plan_usage.total_tokens, 0)

    def test_start_task_raises_when_plan_llm_fails_with_provider_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            platform_config_path = Path(temp_dir) / "platform.json"
            platform_config_path.write_text("{}", encoding="utf-8")
            settings = Settings(
                app_env="development",
                database_url=f"sqlite:///{database_path}",
                platform_config_path=str(platform_config_path),
                github_repository="tiezhuli001/youmeng-gateway",
                langsmith_tracing=False,
                minimax_api_key="test-key",
                openai_api_key=None,
                sleep_coding_execution_command=None,
                sleep_coding_execution_allow_llm_fallback=False,
            )
            github = FakeGitHubService()
            service = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner("passed"),
                ledger=TokenLedgerService(settings),
                agent_runtime=FailingAgentRuntime(),
                mcp_client=build_github_mcp(github),
            )

            with self.assertRaisesRegex(RuntimeError, "LLM provider is unreachable"):
                service.start_task(SleepCodingTaskRequest(issue_number=19))

    def test_apply_action_raises_when_execution_llm_fails_with_provider_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            platform_config_path = Path(temp_dir) / "platform.json"
            platform_config_path.write_text(
                '{"sleep_coding":{"execution":{"allow_llm_fallback":true}}}',
                encoding="utf-8",
            )
            settings = Settings(
                app_env="development",
                database_url=f"sqlite:///{database_path}",
                platform_config_path=str(platform_config_path),
                github_repository="tiezhuli001/youmeng-gateway",
                langsmith_tracing=False,
                minimax_api_key="test-key",
                openai_api_key=None,
                sleep_coding_execution_command=None,
                sleep_coding_execution_allow_llm_fallback=False,
            )
            github = FakeGitHubService()
            service = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner("passed"),
                ledger=TokenLedgerService(settings),
                agent_runtime=FakeAgentRuntime(),
                mcp_client=build_github_mcp(github),
            )
            task = service.start_task(SleepCodingTaskRequest(issue_number=19))
            service.agent_runtime = FailingAgentRuntime()
            service.agent_runtime.mcp = build_github_mcp(github)

            with self.assertRaisesRegex(RuntimeError, "LLM provider is unreachable"):
                service.apply_action(
                    task.task_id,
                    SleepCodingTaskActionRequest(action="approve_plan"),
                )

    def test_apply_action_requires_local_execution_command_when_llm_fallback_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            platform_config_path = Path(temp_dir) / "platform.json"
            platform_config_path.write_text("{}", encoding="utf-8")
            settings = Settings(
                app_env="development",
                database_url=f"sqlite:///{database_path}",
                platform_config_path=str(platform_config_path),
                github_repository="tiezhuli001/youmeng-gateway",
                langsmith_tracing=False,
                minimax_api_key="test-key",
                openai_api_key=None,
                sleep_coding_execution_command=None,
                sleep_coding_execution_allow_llm_fallback=False,
            )
            github = FakeGitHubService()
            service = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner("passed"),
                ledger=TokenLedgerService(settings),
                agent_runtime=FakeAgentRuntime(),
                mcp_client=build_github_mcp(github),
            )
            task = service.start_task(SleepCodingTaskRequest(issue_number=23))

            with self.assertRaisesRegex(RuntimeError, "Local sleep coding execution command is required"):
                service.apply_action(
                    task.task_id,
                    SleepCodingTaskActionRequest(action="approve_plan"),
                )

    def test_uses_configured_validation_command(self) -> None:
        class ValidationPlanAgentRuntime(FakeAgentRuntime):
            def generate_structured_output(self, agent, *, user_prompt, output_contract, **kwargs):
                self.calls.append(output_contract)
                return type(
                    "FakeLLMResponse",
                    (),
                    {
                        "output_text": (
                            '{"summary":"LLM generated plan","scope":["Update service code","Add tests"],'
                            '"validation":["Run python -m unittest tests.test_main_agent"],'
                            '"risks":["Issue details may still need clarification."]}'
                        ),
                        "usage": type(
                            "FakeUsage",
                            (),
                            {
                                "prompt_tokens": 11,
                                "completion_tokens": 13,
                                "total_tokens": 24,
                                "cache_read_tokens": 0,
                                "cache_write_tokens": 0,
                                "reasoning_tokens": 0,
                                "message_count": 2,
                                "duration_seconds": 0.0,
                                "model_name": "test-model",
                                "provider": "openai",
                                "cost_usd": 0.0,
                                "step_name": None,
                                "model_copy": lambda self, update=None: self,
                            },
                        )(),
                    },
                )()

        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = Settings(
                app_env="test",
                database_url=f"sqlite:///{database_path}",
                github_repository="tiezhuli001/youmeng-gateway",
                langsmith_tracing=False,
                platform_config_path=str(Path(temp_dir) / "platform.json"),
            )
            Path(settings.resolved_platform_config_path).write_text(
                '{"sleep_coding":{"validation":{"command":"python -m unittest tests.test_main_agent"}}}',
                encoding="utf-8",
            )
            github = FakeGitHubService()
            service = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=None,
                ledger=TokenLedgerService(settings),
                agent_runtime=ValidationPlanAgentRuntime(),
                mcp_client=build_github_mcp(github),
            )

            self.assertEqual(
                service.validator.command,
                "python -m unittest tests.test_main_agent",
            )
            task = service.start_task(SleepCodingTaskRequest(issue_number=21))
            self.assertEqual(
                task.plan.validation[0],
                "Run python -m unittest tests.test_main_agent",
            )

    def test_validation_runner_prefers_project_venv_python_for_worktree_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            worktree = project_root / ".worktrees" / "issue-1"
            project_python = project_root / ".venv" / "bin" / "python"
            script_path = project_root / "scripts" / "run_sleep_coding_validation.py"
            project_python.parent.mkdir(parents=True, exist_ok=True)
            script_path.parent.mkdir(parents=True, exist_ok=True)
            project_python.write_text("#!/bin/sh\n", encoding="utf-8")
            script_path.write_text("print('ok')\n", encoding="utf-8")
            worktree.mkdir(parents=True, exist_ok=True)

            runner = ValidationRunner(
                command="python scripts/run_sleep_coding_validation.py",
                project_root=project_root,
            )

            resolved = runner._resolve_command_args(
                ["python", "scripts/run_sleep_coding_validation.py"],
                worktree,
            )

            self.assertEqual(resolved[0], str(project_python))
            self.assertEqual(resolved[1], str(script_path))

    def test_validation_runner_marks_timeout_as_failed_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            runner = ValidationRunner(
                command="python -m unittest",
                project_root=repo_path,
                timeout_seconds=12,
            )

            with patch(
                "app.agents.ralph.validation.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd=["python"], timeout=12),
            ):
                result = runner.run(repo_path)

            self.assertEqual(result.status, "failed")
            self.assertEqual(result.exit_code, 124)
            self.assertIn("timed out after 12.0s", result.output)

    def test_local_execution_command_timeout_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            settings = Settings(
                app_env="test",
                sleep_coding_execution_timeout_seconds=9,
            )
            service = RalphDraftingService(
                settings=settings,
                repo_path=repo_path,
                context=Mock(),
                tasks=Mock(),
                agent_runtime=Mock(),
            )

            with self.assertRaisesRegex(RuntimeError, "timed out after 9.0s"):
                with patch(
                    "app.agents.ralph.drafting.subprocess.run",
                    side_effect=subprocess.TimeoutExpired(cmd=["runner"], timeout=9),
                ):
                    service._run_local_execution_command(
                        command=["runner"],
                        prompt="do work",
                        worktree_path=repo_path,
                        issue=SleepCodingIssue(issue_number=1, title="Timeout", body="Test"),
                        plan=SleepCodingPlan(summary="s", scope=[], validation=[], risks=[]),
                        head_branch="codex/test-timeout",
                    )

    def test_github_bridge_coerces_string_url_payload(self) -> None:
        settings = Settings(app_env="test", github_repository="tiezhuli001/youmeng-gateway")
        bridge = RalphGitHubBridge(settings, MCPClient())
        payload = bridge.coerce_mapping(
            "created pull request: https://github.com/tiezhuli001/youmeng-gateway/pull/123"
        )
        self.assertEqual(
            payload["html_url"],
            "https://github.com/tiezhuli001/youmeng-gateway/pull/123",
        )

    def test_github_bridge_coerces_text_mapping_payload(self) -> None:
        settings = Settings(app_env="test", github_repository="tiezhuli001/youmeng-gateway")
        bridge = RalphGitHubBridge(settings, MCPClient())
        payload = bridge.coerce_mapping(
            [
                {
                    "type": "text",
                    "text": '{"html_url":"https://github.com/tiezhuli001/youmeng-gateway/pull/456","number":456}',
                }
            ]
        )
        self.assertEqual(
            payload["html_url"],
            "https://github.com/tiezhuli001/youmeng-gateway/pull/456",
        )
        self.assertEqual(payload["number"], 456)


    def test_failed_validation_marks_task_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = build_settings(database_path)
            channel = FakeChannelService()
            git_workspace = FakeGitWorkspaceService()
            agent_runtime = FakeAgentRuntime()
            github = FakeGitHubService()
            service = SleepCodingService(
                settings=settings,
                channel=channel,
                git_workspace=git_workspace,
                validator=FakeValidationRunner("failed"),
                ledger=TokenLedgerService(settings),
                agent_runtime=agent_runtime,
                mcp_client=build_github_mcp(github),
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
            self.assertIn("codex/issue-25-sleep-coding", git_workspace.cleaned_branches)
            self.assertEqual(len(channel.messages), 2)
            self.assertTrue(any("Ralph 执行计划" in title for title, _, _ in channel.messages))

    def test_review_handoff_requires_validation_evidence_or_explicit_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = build_settings(database_path)
            service = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner("pending"),
                ledger=TokenLedgerService(settings),
                agent_runtime=FakeAgentRuntime(),
                mcp_client=build_github_mcp(FakeGitHubService()),
            )
            task = service.start_task(SleepCodingTaskRequest(issue_number=30))

            with self.assertRaisesRegex(ValueError, "validation evidence"):
                service.apply_action(
                    task.task_id,
                    SleepCodingTaskActionRequest(action="approve_plan"),
                )

    def test_resume_planned_task_reuses_persisted_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = build_settings(database_path)
            agent_runtime = FakeAgentRuntime()
            service = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner("passed"),
                ledger=TokenLedgerService(settings),
                agent_runtime=agent_runtime,
                mcp_client=build_github_mcp(FakeGitHubService()),
            )
            task = service.start_task(SleepCodingTaskRequest(issue_number=31))
            runtime_calls_after_start = len(agent_runtime.calls)

            resumed = service.resume_task(task.task_id)

            self.assertEqual(resumed.status, "awaiting_confirmation")
            self.assertEqual(resumed.plan.summary, task.plan.summary)
            self.assertEqual(len(agent_runtime.calls), runtime_calls_after_start)

    def test_resume_after_validation_reuses_validation_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = build_settings(database_path)
            github = FakeGitHubService()
            validator = FakeValidationRunner("passed")
            service = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=validator,
                ledger=TokenLedgerService(settings),
                agent_runtime=FakeAgentRuntime(),
                mcp_client=build_github_mcp(github),
            )
            task = service.start_task(SleepCodingTaskRequest(issue_number=32))
            with service._connect() as connection:
                service.store.update_task_payloads(
                    connection,
                    task.task_id,
                    status="validating",
                    git_execution=GitExecutionResult(
                        status="prepared",
                        worktree_path=f"/tmp/{task.head_branch.replace('/', '__')}",
                        artifact_path=f"/tmp/{task.head_branch.replace('/', '__')}/.sleep_coding/issue-32.md",
                        output="artifact ready",
                        is_dry_run=True,
                    ),
                    validation=ValidationResult(
                        status="passed",
                        command="python -m unittest discover -s tests",
                        exit_code=0,
                        output="already passed",
                    ),
                )
                connection.commit()
            validator_calls_before_resume = validator.calls

            resumed = service.resume_task(task.task_id)

            self.assertEqual(resumed.status, "in_review")
            self.assertEqual(resumed.validation.status, "passed")
            self.assertEqual(validator.calls, validator_calls_before_resume)
            self.assertEqual(len(github.created_prs), 1)

    def test_resume_after_validation_reuses_existing_pull_request_and_review_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = build_settings(database_path)
            github = FakeGitHubService()
            service = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner("passed"),
                ledger=TokenLedgerService(settings),
                agent_runtime=FakeAgentRuntime(),
                mcp_client=build_github_mcp(github),
            )
            task = service.start_task(SleepCodingTaskRequest(issue_number=33))
            first = service.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )
            control_before = service.tasks.get_task(first.control_task_id)
            with service._connect() as connection:
                service.store.update_status(connection, task.task_id, "validating")
                connection.commit()

            resumed = service.resume_task(task.task_id)
            control_after = service.tasks.get_task(first.control_task_id)

            self.assertEqual(resumed.status, "in_review")
            self.assertEqual(resumed.pull_request.pr_number, first.pull_request.pr_number)
            self.assertEqual(len(github.created_prs), 1)
            self.assertEqual(
                RalphReviewHandoff.model_validate(control_after.payload["review_handoff"]).task_id,
                task.task_id,
            )
            self.assertEqual(
                control_after.payload["review_handoff"],
                control_before.payload["review_handoff"],
            )

    def test_resume_changes_requested_uses_persisted_review_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = build_settings(database_path)
            github = FakeGitHubService()
            service = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner("passed"),
                ledger=TokenLedgerService(settings),
                agent_runtime=FakeAgentRuntime(),
                mcp_client=build_github_mcp(github),
            )
            task = service.start_task(SleepCodingTaskRequest(issue_number=34))
            service.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )
            service.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="request_changes"),
            )
            control_task = service.tasks.get_task(service.get_task(task.task_id).control_task_id)
            service.tasks.update_task(
                control_task.task_id,
                payload_patch={
                    "latest_review_id": "review-ctx-1",
                    "latest_review_summary": "Need one repair pass.",
                    "latest_review_status": "changes_requested",
                    "review_round": 1,
                },
            )

            resumed = service.resume_task(task.task_id)

            self.assertEqual(resumed.status, "in_review")
            resume_events = [event for event in resumed.events if event.event_type == "coding_resumed"]
            self.assertTrue(resume_events)
            self.assertEqual(resume_events[-1].payload["review_id"], "review-ctx-1")
            self.assertEqual(resume_events[-1].payload["review_round"], 1)
            self.assertIn("Need one repair pass.", resume_events[-1].payload["review_summary"])

    def test_repair_round_reuses_existing_pull_request(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = build_settings(database_path)
            github = FakeGitHubService()
            service = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner("passed"),
                ledger=TokenLedgerService(settings),
                agent_runtime=FakeAgentRuntime(),
                mcp_client=build_github_mcp(github),
            )
            task = service.start_task(SleepCodingTaskRequest(issue_number=26))
            first = service.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )
            service.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="request_changes"),
            )

            repaired = service.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )

            self.assertEqual(repaired.status, "in_review")
            self.assertEqual(repaired.pull_request.pr_number, first.pull_request.pr_number)
            self.assertEqual(len(github.created_prs), 1)

    def test_repair_round_recovers_existing_pull_request_from_control_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sleep_coding.db"
            settings = build_settings(database_path)
            github = FakeGitHubService()
            service = SleepCodingService(
                settings=settings,
                channel=FakeChannelService(),
                git_workspace=FakeGitWorkspaceService(),
                validator=FakeValidationRunner("passed"),
                ledger=TokenLedgerService(settings),
                agent_runtime=FakeAgentRuntime(),
                mcp_client=build_github_mcp(github),
            )
            task = service.start_task(SleepCodingTaskRequest(issue_number=27))
            first = service.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )
            service.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="request_changes"),
            )
            with service._connect() as connection:
                connection.execute(
                    "UPDATE sleep_coding_tasks SET pr_payload = NULL WHERE task_id = ?",
                    (task.task_id,),
                )
                connection.commit()

            repaired = service.apply_action(
                task.task_id,
                SleepCodingTaskActionRequest(action="approve_plan"),
            )

            self.assertEqual(repaired.status, "in_review")
            self.assertEqual(repaired.pull_request.pr_number, first.pull_request.pr_number)
            self.assertEqual(repaired.pull_request.html_url, first.pull_request.html_url)
            self.assertEqual(len(github.created_prs), 1)


class GitWorkspaceServiceTests(unittest.TestCase):
    def test_dry_run_worktree_commit_push(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            platform_path = root / "platform.json"
            platform_path.write_text(
                '{"sleep_coding":{"git":{"enable_commit":false,"enable_push":false}}}',
                encoding="utf-8",
            )
            settings = Settings(platform_config_path=str(platform_path))
            service = GitWorkspaceService(settings, mcp_client=MCPClient())

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

    def test_collect_changed_files_includes_untracked_nested_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            repo_root.mkdir()
            subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "checkout", "-b", "main"], cwd=repo_root, check=True, capture_output=True, text=True)
            (repo_root / "README.md").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True, text=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Test User",
                    "-c",
                    "user.email=test@example.com",
                    "commit",
                    "-m",
                    "init",
                ],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
            )

            worktree_path = repo_root
            nested = worktree_path / "docs" / "e2e" / "issue-33.md"
            nested.parent.mkdir(parents=True, exist_ok=True)
            nested.write_text("live smoke\n", encoding="utf-8")

            platform_config_path = Path(temp_dir) / "platform.json"
            platform_config_path.write_text("{}", encoding="utf-8")
            settings = Settings(
                app_env="test",
                database_url=f"sqlite:///{repo_root / 'test.db'}",
                platform_config_path=str(platform_config_path),
                github_repository="tiezhuli001/youmeng-gateway",
                langsmith_tracing=False,
            )
            service = GitWorkspaceService(settings, mcp_client=MCPClient())
            service.repo_path = repo_root
            collected = service._collect_changed_files(worktree_path, branch="codex/issue-33")

            self.assertEqual(
                collected,
                [{"path": "docs/e2e/issue-33.md", "content": "live smoke\n"}],
            )

    def test_collect_changed_files_includes_pending_ignored_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            repo_root.mkdir()
            subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "checkout", "-b", "main"], cwd=repo_root, check=True, capture_output=True, text=True)
            (repo_root / ".gitignore").write_text("docs/internal/\n", encoding="utf-8")
            subprocess.run(["git", "add", ".gitignore"], cwd=repo_root, check=True, capture_output=True, text=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Test User",
                    "-c",
                    "user.email=test@example.com",
                    "commit",
                    "-m",
                    "init",
                ],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
            )

            ignored = repo_root / "docs" / "internal" / "live-chain-validation.md"
            ignored.parent.mkdir(parents=True, exist_ok=True)
            ignored.write_text("marker\n", encoding="utf-8")

            platform_config_path = Path(temp_dir) / "platform.json"
            platform_config_path.write_text("{}", encoding="utf-8")
            settings = Settings(
                app_env="test",
                database_url=f"sqlite:///{repo_root / 'test.db'}",
                platform_config_path=str(platform_config_path),
                github_repository="tiezhuli001/youmeng-gateway",
                langsmith_tracing=False,
            )
            service = GitWorkspaceService(settings, mcp_client=MCPClient())
            service.repo_path = repo_root
            service._pending_files["codex/issue-65"] = ["docs/internal/live-chain-validation.md"]

            collected = service._collect_changed_files(worktree_path=repo_root, branch="codex/issue-65")

            self.assertEqual(
                collected,
                [{"path": "docs/internal/live-chain-validation.md", "content": "marker\n"}],
            )
