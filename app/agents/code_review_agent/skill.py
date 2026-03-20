from __future__ import annotations

import json
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.models.schemas import ReviewFinding, ReviewSkillOutput, ReviewSource, TokenUsage
from app.runtime.agent_runtime import AgentDescriptor, AgentRuntime
from app.runtime.mcp import MCPClient, build_default_mcp_client
from app.runtime.pricing import PricingRegistry
from app.runtime.structured_output import parse_structured_object
from app.runtime.token_counting import TokenCountingService


@dataclass(frozen=True)
class ReviewSkillRunResult:
    output: ReviewSkillOutput
    token_usage: TokenUsage


def count_findings_by_severity(findings: list[ReviewFinding]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return counts


class ReviewSkillService:
    def __init__(
        self,
        settings: Settings,
        agent_runtime: AgentRuntime | None = None,
        mcp_client: MCPClient | None = None,
    ) -> None:
        self.settings = settings
        self.skill_name = settings.resolved_review_skill_name
        self.command = settings.resolved_review_skill_command
        self.project_root = settings.project_root
        self.mcp_client = mcp_client or build_default_mcp_client(settings)
        self.agent_runtime = agent_runtime or AgentRuntime(
            settings,
            mcp_client=self.mcp_client,
        )
        self.token_counter = TokenCountingService()
        self.pricing = PricingRegistry(settings)

    def run(self, source: ReviewSource, context: str) -> ReviewSkillRunResult:
        command = self._resolve_command(source)
        if command is not None:
            return self._run_with_command(command, source, context)
        if self.settings.has_runtime_llm_credentials:
            try:
                return self._run_with_agent_runtime(source, context)
            except Exception as exc:
                return ReviewSkillRunResult(
                    output=self._build_agent_runtime_fallback_output(
                        source,
                        context,
                        raw_output="",
                        error=str(exc),
                    ),
                    token_usage=self._estimate_usage(
                        input_text=context,
                        output_text=str(exc),
                    ),
                )
        return self._build_dry_run_output(source, context)

    def _run_with_agent_runtime(self, source: ReviewSource, context: str) -> ReviewSkillRunResult:
        response = self.agent_runtime.generate_structured_output(
            self._build_agent_descriptor(),
            user_prompt=(
                "Review the following code change context and return structured findings.\n\n"
                f"Source type: {source.source_type}\n\n"
                f"{context}"
            ),
            output_contract=(
                "Return strict JSON with keys `summary`, `findings`, `repair_strategy`, `blocking`, and `review_markdown`. "
                "`findings` must be an array of objects with keys `severity`, `title`, `detail`, and optional "
                "`file_path`, `line`, `suggestion`. Severity must be one of `P0`, `P1`, `P2`, `P3`. "
                "`blocking` must be true when any finding is P0 or P1, else false. "
                "`review_markdown` must be human-readable markdown that summarizes the findings."
            ),
        )
        try:
            output = ReviewSkillOutput.model_validate(parse_structured_object(response.output_text))
        except Exception as exc:
            output = self._build_agent_runtime_fallback_output(
                source,
                context,
                raw_output=response.output_text,
                error=str(exc),
            )
        return ReviewSkillRunResult(
            output=output.model_copy(
                update={
                    "run_mode": "real_run",
                    "review_markdown": output.review_markdown or output.summary,
                }
            ),
            token_usage=response.usage.model_copy(update={"step_name": "code_review"}),
        )

    def _run_with_command(
        self,
        command: list[str],
        source: ReviewSource,
        context: str,
    ) -> ReviewSkillRunResult:
        prompt = self._build_prompt(source)
        review_dir = self._resolve_dir(source)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as handle:
            handle.write(context)
            context_path = Path(handle.name)

        try:
            completed = subprocess.run(
                [*command, prompt, "-f", str(context_path)],
                cwd=review_dir,
                text=True,
                capture_output=True,
                check=False,
            )
        finally:
            context_path.unlink(missing_ok=True)
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        if completed.returncode != 0:
            raise RuntimeError(
                f"Review skill command failed with exit_code={completed.returncode}: {output}"
            )
        structured = self._parse_command_output(output)
        return ReviewSkillRunResult(
            output=structured,
            token_usage=self._estimate_usage(
                input_text=f"{prompt}\n\n{context}",
                output_text=output,
            ),
        )

    def _build_agent_runtime_fallback_output(
        self,
        source: ReviewSource,
        context: str,
        *,
        raw_output: str,
        error: str,
    ) -> ReviewSkillOutput:
        excerpt = raw_output.strip()[:1200]
        summary = "Review runtime returned non-contract output; falling back to a minimal review result."
        review_markdown = (
            "## Code Review Agent\n\n"
            "The configured review runtime returned output that did not match the review contract.\n\n"
            f"Source Type: `{source.source_type}`\n\n"
            f"Parse Error: `{error}`\n\n"
            "Raw Output Excerpt:\n"
            f"```text\n{excerpt}\n```\n\n"
            "Fallback decision: no structured blocking findings were produced."
        )
        return ReviewSkillOutput(
            summary=summary,
            findings=[],
            repair_strategy=[
                "Tighten the review output contract or switch to a more reliable review provider.",
            ],
            blocking=False,
            run_mode="real_run",
            review_markdown=review_markdown,
        )

    def _parse_command_output(self, output: str) -> ReviewSkillOutput:
        try:
            parsed_json = json.loads(output)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Review skill command must return strict JSON output.")
        if not isinstance(parsed_json, dict):
            raise RuntimeError("Review skill command must return strict JSON output.")
        structured = ReviewSkillOutput.model_validate(parsed_json)
        return structured.model_copy(
            update={
                "run_mode": "real_run",
                "review_markdown": structured.review_markdown or structured.summary,
            }
        )

    def _build_dry_run_output(self, source: ReviewSource, context: str) -> ReviewSkillRunResult:
        summary = f"Dry-run review generated for {source.source_type}."
        review_markdown = (
            "## Code Review Agent\n\n"
            "Dry-run review executed because no review skill runtime is configured.\n\n"
            f"Source Type: `{source.source_type}`\n\n"
            f"{context}\n"
        )
        output = ReviewSkillOutput(
            summary=summary,
            findings=[],
            repair_strategy=["Configure a review skill runtime for structured findings."],
            blocking=False,
            run_mode="dry_run",
            review_markdown=review_markdown,
        )
        return ReviewSkillRunResult(
            output=output,
            token_usage=self._estimate_usage(
                input_text=context,
                output_text=review_markdown,
            ),
        )

    def _build_agent_descriptor(self) -> AgentDescriptor:
        return AgentDescriptor.from_spec(self.settings.resolve_agent_spec("code-review-agent"))

    def _resolve_command(self, source: ReviewSource) -> list[str] | None:
        if self.command:
            return shlex.split(self.command)
        return None

    def _resolve_dir(self, source: ReviewSource) -> Path:
        if source.local_path:
            return Path(source.local_path).expanduser()
        return self.project_root

    def _build_prompt(self, source: ReviewSource) -> str:
        return (
            f"Use the {self.skill_name} skill to review this source. "
            f"Source type: {source.source_type}. "
            "Return strict JSON with summary, findings, repair_strategy, blocking, and review_markdown."
        )

    def _estimate_usage(
        self,
        *,
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
                "step_name": "code_review",
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
