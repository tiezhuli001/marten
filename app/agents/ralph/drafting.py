from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.agents.ralph.runtime_executor import RalphRuntimeExecutor
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
    from app.control.task_registry import TaskRegistryService


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
                    workflow="sleep_coding",
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
        if not self.settings.has_runtime_llm_credentials:
            raise RuntimeError(
                "Builtin Ralph runtime is unavailable: missing LLM credentials for agent-native execution."
            )
        executor = RalphRuntimeExecutor(
            agent_runtime=self.agent_runtime,
            agent_descriptor=self.build_agent_descriptor(),
        )
        return executor.generate_execution_draft(
            prompt=prompt,
            issue=issue,
            plan=plan,
            head_branch=head_branch,
        )

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
