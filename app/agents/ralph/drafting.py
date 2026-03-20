from __future__ import annotations

import json
import shlex
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.models.schemas import (
    SleepCodingExecutionDraft,
    SleepCodingFileChange,
    SleepCodingIssue,
    SleepCodingPlan,
    TokenUsage,
)
from app.runtime.agent_runtime import AgentDescriptor
from app.runtime.pricing import PricingRegistry
from app.runtime.structured_output import parse_structured_object
from app.runtime.token_counting import TokenCountingService

if TYPE_CHECKING:
    from app.control.context import ContextAssemblyService
    from app.core.config import Settings
    from app.runtime.agent_runtime import AgentRuntime
    from app.services.task_registry import TaskRegistryService


class RalphDraftingService:
    def __init__(
        self,
        *,
        settings: Settings,
        repo_path: Path,
        context: ContextAssemblyService,
        tasks: TaskRegistryService,
        agent_runtime: AgentRuntime,
    ) -> None:
        self.settings = settings
        self.repo_path = repo_path
        self.context = context
        self.tasks = tasks
        self.agent_runtime = agent_runtime
        self.token_counter = TokenCountingService()
        self.pricing = PricingRegistry(settings)

    def build_plan(
        self,
        issue: SleepCodingIssue,
        run_session_id: str | None = None,
    ) -> tuple[SleepCodingPlan, TokenUsage]:
        prompt = self.context.build_agent_input(
            session_id=run_session_id,
            heading="Current Ralph Planning Task",
            current_input=(
                "Build a concise implementation plan for this GitHub issue.\n\n"
                f"Issue #{issue.issue_number}: {issue.title}\n\n"
                f"{issue.body.strip() or 'Issue body is empty.'}"
            ),
        )
        if self.settings.has_runtime_llm_credentials:
            try:
                response = self.agent_runtime.generate_structured_output(
                    self.build_agent_descriptor(),
                    user_prompt=prompt,
                    output_contract=(
                        "Return strict JSON with keys `summary`, `scope`, `validation`, and `risks`. "
                        "Each non-summary key must be an array of short strings. "
                        "The plan must emphasize concrete code changes and tests."
                    ),
                )
                try:
                    plan = self._parse_plan_output(response.output_text)
                except (RuntimeError, json.JSONDecodeError, ValidationError, ValueError, SyntaxError):
                    plan = self.build_heuristic_plan(issue)
                return (plan, response.usage.model_copy(update={"step_name": "sleep_coding_plan"}))
            except Exception:
                if self.settings.app_env != "test":
                    raise
        plan = self.build_heuristic_plan(issue)
        usage = self.estimate_usage(
            step_name="sleep_coding_plan",
            input_text=prompt,
            output_text=plan.model_dump_json(),
        )
        return plan, usage

    def build_heuristic_plan(self, issue: SleepCodingIssue) -> SleepCodingPlan:
        issue_body = issue.body.strip() or "Issue body is empty."
        summary = f"Implement Issue #{issue.issue_number}: {issue.title}"
        return SleepCodingPlan(
            summary=summary,
            scope=[
                "Read the issue context and confirm the affected modules.",
                "Implement the minimum code path required for the issue.",
                "Prepare a reviewable branch and PR summary.",
            ],
            validation=[
                f"Run {self.settings.resolved_sleep_coding_validation_command}",
                "Record the command, exit code, and captured output in task state.",
            ],
            risks=[
                "Issue details may be incomplete, so the generated plan may need human correction.",
                f"Current issue context: {issue_body[:160]}",
            ],
        )

    def _parse_plan_output(self, output_text: str) -> SleepCodingPlan:
        parsed = parse_structured_object(output_text)
        if not isinstance(parsed, dict):
            raise RuntimeError("Sleep coding plan output must be a JSON object.")
        normalized = dict(parsed)
        summary = normalized.get("summary")
        if isinstance(summary, list):
            normalized["summary"] = " ".join(
                str(item).strip() for item in summary if str(item).strip()
            )
        return SleepCodingPlan.model_validate(normalized)

    def build_execution_draft(
        self,
        issue: SleepCodingIssue,
        plan: SleepCodingPlan,
        head_branch: str,
        worktree_path: Path | None = None,
        control_task_id: str | None = None,
    ) -> tuple[SleepCodingExecutionDraft, TokenUsage]:
        run_session_id = None
        if control_task_id:
            control_task = self.tasks.get_task(control_task_id)
            candidate = control_task.payload.get("run_session_id")
            if isinstance(candidate, str) and candidate.strip():
                run_session_id = candidate
        prompt = self.context.build_agent_input(
            session_id=run_session_id,
            heading="Current Ralph Execution Task",
            current_input=(
                "Generate the initial coding draft for this task.\n\n"
                f"Issue #{issue.issue_number}: {issue.title}\n"
                f"Branch: {head_branch}\n\n"
                "Issue body:\n"
                f"{issue.body.strip() or 'Issue body is empty.'}\n\n"
                "Approved plan:\n"
                f"{plan.model_dump_json(indent=2)}"
            ),
        )
        command = self._resolve_execution_command(worktree_path)
        if command is not None and worktree_path is not None:
            return self._run_local_execution_command(
                command=command,
                prompt=prompt,
                worktree_path=worktree_path,
                issue=issue,
                plan=plan,
                head_branch=head_branch,
            )
        if (
            self.settings.app_env != "test"
            and not self.settings.resolved_sleep_coding_execution_allow_llm_fallback
        ):
            raise RuntimeError(
                "Local sleep coding execution command is required. "
                "Configure `sleep_coding.execution.command` or explicitly enable `sleep_coding.execution.allow_llm_fallback`."
            )
        if self.settings.has_runtime_llm_credentials:
            try:
                response = self.agent_runtime.generate_structured_output(
                    self.build_agent_descriptor(),
                    user_prompt=prompt,
                    output_contract=(
                        "Return strict JSON with keys `artifact_markdown`, `commit_message`, and `file_changes`. "
                        "`artifact_markdown` must be markdown for `.sleep_coding/issue-<number>.md`. "
                        "`commit_message` must be one concise git commit message. "
                        "`file_changes` must be an array of objects with keys `path`, `content`, and optional `description`. "
                        "Only include relative repo paths and include tests when code changes are proposed."
                    ),
                )
                try:
                    draft = SleepCodingExecutionDraft.model_validate(
                        parse_structured_object(response.output_text)
                    )
                except (json.JSONDecodeError, ValidationError, ValueError, SyntaxError):
                    draft = self.build_heuristic_execution_draft(issue, plan, head_branch)
                return (draft, response.usage.model_copy(update={"step_name": "sleep_coding_execution"}))
            except Exception:
                if self.settings.app_env != "test":
                    raise
        draft = self.build_heuristic_execution_draft(issue, plan, head_branch)
        usage = self.estimate_usage(
            step_name="sleep_coding_execution",
            input_text=prompt,
            output_text=draft.model_dump_json(),
        )
        return draft, usage

    def _run_local_execution_command(
        self,
        *,
        command: list[str],
        prompt: str,
        worktree_path: Path,
        issue: SleepCodingIssue,
        plan: SleepCodingPlan,
        head_branch: str,
    ) -> tuple[SleepCodingExecutionDraft, TokenUsage]:
        context = self._build_local_execution_context(
            issue=issue,
            plan=plan,
            head_branch=head_branch,
            worktree_path=worktree_path,
        )
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as handle:
            handle.write(context)
            context_path = Path(handle.name)
        try:
            completed = subprocess.run(
                [*command, prompt, "-f", str(context_path)],
                cwd=worktree_path,
                text=True,
                capture_output=True,
                check=False,
            )
        finally:
            context_path.unlink(missing_ok=True)
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        if completed.returncode != 0:
            raise RuntimeError(
                f"Sleep coding execution command failed with exit_code={completed.returncode}: {output}"
            )
        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Sleep coding execution command must return strict JSON output.") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Sleep coding execution command must return strict JSON output.")
        draft = SleepCodingExecutionDraft.model_validate(payload)
        return (
            draft,
            self.estimate_usage(
                step_name="sleep_coding_execution",
                input_text=f"{prompt}\n\n{context}",
                output_text=output,
            ),
        )

    def _build_local_execution_context(
        self,
        *,
        issue: SleepCodingIssue,
        plan: SleepCodingPlan,
        head_branch: str,
        worktree_path: Path,
    ) -> str:
        return (
            f"Local Worktree: {worktree_path}\n"
            f"Issue #{issue.issue_number}: {issue.title}\n"
            f"Branch: {head_branch}\n\n"
            "Read and edit files directly in this worktree. "
            "Inspect the repository before making changes. "
            "Do not return file contents in JSON; write files locally and only summarize the task artifact and commit message.\n\n"
            "Approved plan:\n"
            f"{plan.model_dump_json(indent=2)}\n"
        )

    def _resolve_execution_command(self, worktree_path: Path | None) -> list[str] | None:
        if worktree_path is None:
            return None
        if self.settings.resolved_sleep_coding_execution_command:
            return shlex.split(self.settings.resolved_sleep_coding_execution_command)
        return None

    def build_heuristic_execution_draft(
        self,
        issue: SleepCodingIssue,
        plan: SleepCodingPlan,
        head_branch: str,
    ) -> SleepCodingExecutionDraft:
        artifact_markdown = (
            f"## Summary\n{plan.summary}\n\n"
            "## Scope\n"
            + "\n".join(f"- {item}" for item in plan.scope)
            + "\n\n## Validation\n"
            + "\n".join(f"- {item}" for item in plan.validation)
            + "\n\n## Risks\n"
            + "\n".join(f"- {item}" for item in plan.risks)
            + "\n\n## Working Branch\n"
            + f"- {head_branch}"
        )
        file_changes = self.build_heuristic_file_changes(issue)
        return SleepCodingExecutionDraft(
            artifact_markdown=artifact_markdown,
            commit_message=f"Sleep coding: issue #{issue.issue_number}",
            file_changes=file_changes,
        )

    def build_heuristic_file_changes(
        self,
        issue: SleepCodingIssue,
    ) -> list[SleepCodingFileChange]:
        issue_text = f"{issue.title}\n{issue.body}".lower()
        marker = f"<!-- ralph-e2e-issue-{issue.issue_number} -->"
        live_chain_path = "docs/internal/live-chain-validation.md"
        if live_chain_path in issue_text:
            target = self.repo_path / live_chain_path
            marker_line = f"- live validation marker: {date.today().isoformat()} {marker}"
            if target.exists():
                existing = target.read_text(encoding="utf-8")
                if marker not in existing:
                    content = existing.rstrip() + f"\n{marker_line}\n"
                    return [
                        SleepCodingFileChange(
                            path=live_chain_path,
                            content=content,
                            description="Append a dated live-chain validation marker for the current issue.",
                        )
                    ]
            else:
                content = f"# Live Chain Validation\n\n{marker_line}\n"
                return [
                    SleepCodingFileChange(
                        path=live_chain_path,
                        content=content,
                        description="Create the live-chain validation note file with a dated marker.",
                    )
                ]
        if "readme" in issue_text:
            readme_path = self.repo_path / "README.md"
            if readme_path.exists():
                existing = readme_path.read_text(encoding="utf-8")
                if marker not in existing:
                    content = existing.rstrip() + f"\n\n{marker}\n"
                    return [
                        SleepCodingFileChange(
                            path="README.md",
                            content=content,
                            description="Append an issue marker to README for MVP integration validation.",
                        )
                    ]
        if any(keyword in issue_text for keyword in ("doc", "docs", "documentation", "markdown")):
            return []
        return []

    def estimate_usage(
        self,
        *,
        step_name: str,
        input_text: str,
        output_text: str,
    ) -> TokenUsage:
        provider = self.settings.resolved_llm_default_provider
        model = self.settings.resolved_llm_default_model
        usage = self.token_counter.estimate_text_usage(
            provider=provider,
            model=model,
            input_text=input_text,
            output_text=output_text,
            existing_usage=TokenUsage(),
        )
        return usage.model_copy(
            update={
                "provider": provider,
                "model_name": model,
                "message_count": 2,
                "step_name": step_name,
                "cost_usd": self.pricing.calculate_cost_usd(
                    provider=provider,
                    model=model,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    cache_read_tokens=usage.cache_read_tokens,
                    cache_write_tokens=usage.cache_write_tokens,
                ),
            }
        )

    def build_agent_descriptor(self) -> AgentDescriptor:
        return AgentDescriptor.from_spec(self.settings.resolve_agent_spec("ralph"))

    def render_plan_comment(self, plan: SleepCodingPlan) -> str:
        scope = "\n".join(f"- {item}" for item in plan.scope)
        validation = "\n".join(f"- {item}" for item in plan.validation)
        risks = "\n".join(f"- {item}" for item in plan.risks)
        return (
            "## Ralph Plan\n"
            f"{plan.summary}\n\n"
            f"### Scope\n{scope}\n\n"
            f"### Validation\n{validation}\n\n"
            f"### Risks\n{risks}"
        )

    def render_pr_comment(
        self,
        *,
        issue: SleepCodingIssue,
        pull_request,
        plan: SleepCodingPlan,
        validation,
        head_branch: str,
    ) -> str:
        return (
            "## Ralph PR Ready\n"
            f"- 来源 Issue: #{issue.issue_number} {issue.title}\n"
            f"- Issue: {issue.html_url or 'n/a'}\n"
            f"- PR: {pull_request.html_url or 'pending'}\n"
            f"- Branch: {head_branch}\n"
            f"- Plan Summary: {plan.summary}\n"
            f"- Validation: {validation.status} ({validation.command})\n"
            f"- Dry run: {pull_request.is_dry_run}\n"
            "- 下一步: 等待 Code Review 与最终交付通知"
        )

    def summarize_issue_for_notification(
        self,
        issue: SleepCodingIssue,
        plan: SleepCodingPlan,
    ) -> str:
        normalized = " ".join(issue.body.split())
        if normalized:
            return normalized[:240]
        return plan.summary

    def render_plan_preview(self, plan: SleepCodingPlan) -> list[str]:
        steps: list[str] = []
        for item in plan.scope:
            if item.strip():
                steps.append(item.strip())
        for item in plan.validation:
            if item.strip():
                steps.append(f"验证: {item.strip()}")
        if not steps and plan.summary.strip():
            steps.append(plan.summary.strip())
        return [f"{index}. {item}" for index, item in enumerate(steps[:5], start=1)]
