from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.models.schemas import ReviewSkillOutput, TokenUsage
from app.runtime.agent_runtime import AgentDescriptor
from app.runtime.structured_output import parse_structured_object


class RuntimeReviewer:
    def __init__(
        self,
        *,
        agent_descriptor: AgentDescriptor,
    ) -> None:
        self.agent_descriptor = agent_descriptor

    def parse_response(self, response) -> tuple[ReviewSkillOutput, TokenUsage]:
        try:
            output = ReviewSkillOutput.model_validate(
                self._normalize_review_payload(parse_structured_object(response.output_text))
            )
        except Exception as exc:
            error = RuntimeError(
                f"Builtin code-review-agent returned invalid structured review output: {exc}"
            )
            excerpt = response.output_text[:500].strip()
            setattr(
                error,
                "failure_evidence",
                {
                    "stage": "code_review",
                    "provider": getattr(response.usage, "provider", None),
                    "model": getattr(response.usage, "model_name", None),
                    "parse_error": str(exc),
                    "raw_output_excerpt": excerpt,
                },
            )
            raise error from exc
        return (
            output.model_copy(
                update={
                    "run_mode": "real_run",
                    "review_markdown": output.review_markdown or output.summary,
                }
            ),
            response.usage.model_copy(update={"step_name": "code_review"}),
        )

    def _normalize_review_payload(self, payload: Any) -> Any:
        if not isinstance(payload, Mapping):
            return payload
        normalized = dict(payload)
        repair_strategy = normalized.get("repair_strategy")
        if isinstance(repair_strategy, str):
            candidate = repair_strategy.strip()
            normalized["repair_strategy"] = [candidate] if candidate else []
        return normalized
