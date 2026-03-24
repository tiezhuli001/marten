from __future__ import annotations
from dataclasses import dataclass
from time import sleep
from collections.abc import Callable

from app.agents.code_review_agent.runtime_reviewer import RuntimeReviewer
from app.core.config import Settings
from app.models.schemas import ReviewFinding, ReviewSkillOutput, TokenUsage
from app.agents.code_review_agent.target import ReviewTarget
from app.runtime.agent_runtime import AgentDescriptor, AgentRuntime
from app.runtime.mcp import MCPClient, build_default_mcp_client
from app.runtime.pricing import PricingRegistry
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
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self.settings = settings
        self.skill_name = settings.resolved_review_skill_name
        self.project_root = settings.project_root
        self.mcp_client = mcp_client or build_default_mcp_client(settings)
        self.agent_runtime = agent_runtime or AgentRuntime(
            settings,
            mcp_client=self.mcp_client,
        )
        self.token_counter = TokenCountingService()
        self.pricing = PricingRegistry(settings)
        self.sleep_fn = sleep_fn or ((lambda seconds: None) if settings.app_env == "test" else sleep)

    def run(self, target: ReviewTarget, context: str) -> ReviewSkillRunResult:
        if not self.settings.has_runtime_llm_credentials:
            raise RuntimeError(
                "Builtin code-review-agent runtime is unavailable: missing LLM credentials for agent-native review."
            )
        return self._run_with_agent_runtime(target, context)

    def _run_with_agent_runtime(self, target: ReviewTarget, context: str) -> ReviewSkillRunResult:
        reviewer = RuntimeReviewer(
            agent_descriptor=self._build_agent_descriptor(),
        )
        output_contract = (
            "Return strict JSON with keys `summary`, `findings`, `repair_strategy`, `blocking`, and `review_markdown`. "
            "`findings` must be an array of objects with keys `severity`, `title`, `detail`, and optional "
            "`file_path`, `line`, `suggestion`. Severity must be one of `P0`, `P1`, `P2`, `P3`. "
            "`blocking` must be true when any finding is P0 or P1, else false. "
            "`review_markdown` must be human-readable markdown that summarizes the findings. "
            "Do not return shell commands, CLI flags, markdown fences, or prose outside the JSON object."
        )
        response = self._generate_with_retry(
            user_prompt=(
                "Review the following code change context and return structured findings.\n\n"
                "Source type: sleep_coding_task\n\n"
                f"{context}"
            ),
            output_contract=output_contract,
        )
        try:
            output, usage = reviewer.parse_response(response)
        except RuntimeError:
            repair_response = self._generate_with_retry(
                user_prompt=(
                    "Your previous review response was invalid because it did not parse as strict JSON. "
                    "Return only one JSON object with keys `summary`, `findings`, `repair_strategy`, `blocking`, and `review_markdown`. "
                    "Do not return commands, arguments, prose, or markdown fences.\n\n"
                    f"{context}"
                ),
                output_contract=output_contract,
            )
            output, usage = reviewer.parse_response(repair_response)
        return ReviewSkillRunResult(
            output=output,
            token_usage=usage,
        )

    def _build_agent_descriptor(self) -> AgentDescriptor:
        return AgentDescriptor.from_spec(self.settings.resolve_agent_spec("code-review-agent"))

    def _generate_with_retry(
        self,
        *,
        user_prompt: str,
        output_contract: str,
    ):
        return self.agent_runtime.generate_structured_output(
            self._build_agent_descriptor(),
            user_prompt=user_prompt,
            workflow="code_review",
            output_contract=output_contract,
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
