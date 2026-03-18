from __future__ import annotations

from typing import Iterable

from app.models.schemas import LLMMessage, TokenUsage

try:
    import tiktoken
except Exception:  # pragma: no cover - optional dependency fallback
    tiktoken = None


class TokenCountingService:
    def estimate_openai_usage(
        self,
        *,
        model: str,
        messages: Iterable[LLMMessage],
        output_text: str,
        existing_usage: TokenUsage | None = None,
    ) -> TokenUsage:
        base_usage = existing_usage or TokenUsage()
        if self._has_non_zero_usage(base_usage):
            return base_usage

        prompt_tokens = self._count_openai_chat_tokens(model, messages)
        completion_tokens = self._count_text_tokens(model, output_text)
        total_tokens = prompt_tokens + completion_tokens
        return base_usage.model_copy(
            update={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
        )

    def estimate_text_usage(
        self,
        *,
        provider: str | None,
        model: str | None,
        input_text: str,
        output_text: str = "",
        existing_usage: TokenUsage | None = None,
    ) -> TokenUsage:
        base_usage = existing_usage or TokenUsage()
        if self._has_non_zero_usage(base_usage):
            return base_usage

        encoding_name = self._resolve_encoding_name(provider, model)
        prompt_tokens = self._count_tokens_with_encoding(encoding_name, input_text)
        completion_tokens = self._count_tokens_with_encoding(encoding_name, output_text)
        total_tokens = prompt_tokens + completion_tokens
        return base_usage.model_copy(
            update={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
        )

    def _count_openai_chat_tokens(self, model: str, messages: Iterable[LLMMessage]) -> int:
        # Approximation based on OpenAI chat formatting overhead.
        total = 0
        for message in messages:
            total += 4
            total += self._count_text_tokens(model, message.role)
            total += self._count_text_tokens(model, message.content)
        return total + 2

    def _count_text_tokens(self, model: str, text: str) -> int:
        if not text:
            return 0
        if tiktoken is None:
            return self._fallback_count(text)
        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))

    def _count_tokens_with_encoding(self, encoding_name: str | None, text: str) -> int:
        if not text:
            return 0
        if tiktoken is None or not encoding_name:
            return self._fallback_count(text)
        try:
            encoding = tiktoken.get_encoding(encoding_name)
        except KeyError:
            return self._fallback_count(text)
        return len(encoding.encode(text))

    def _resolve_encoding_name(self, provider: str | None, model: str | None) -> str | None:
        if provider == "openai" and model:
            try:
                return tiktoken.encoding_for_model(model).name if tiktoken is not None else None
            except KeyError:
                return "cl100k_base"
        if provider == "minimax":
            return "cl100k_base"
        return "cl100k_base"

    def _has_non_zero_usage(self, usage: TokenUsage) -> bool:
        return any(
            value > 0
            for value in (
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.total_tokens,
                usage.cache_read_tokens,
                usage.cache_write_tokens,
                usage.reasoning_tokens,
            )
        )

    def _fallback_count(self, text: str) -> int:
        # Cheap fallback when tiktoken is unavailable.
        return max(1, len(text.encode("utf-8")) // 4)
