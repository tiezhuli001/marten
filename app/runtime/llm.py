from __future__ import annotations

import json
from time import sleep
from time import perf_counter
from typing import Any, Callable, Protocol
from urllib import error, request

from app.core.config import Settings
from app.models.schemas import LLMRequest, LLMResponse, TokenUsage
from app.runtime.pricing import PricingRegistry
from app.runtime.token_counting import TokenCountingService


class JsonTransport(Protocol):
    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]: ...


class UrllibJsonTransport:
    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        http_request = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"LLM provider request failed: {exc.code} {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"LLM provider is unreachable: {exc.reason}") from exc


class SharedLLMRuntime:
    def __init__(
        self,
        settings: Settings,
        pricing: PricingRegistry | None = None,
        transport: JsonTransport | None = None,
        token_counter: TokenCountingService | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self.settings = settings
        self.pricing = pricing or PricingRegistry(settings)
        self.transport = transport or UrllibJsonTransport()
        self.token_counter = token_counter or TokenCountingService()
        self.sleep_fn = sleep_fn or sleep

    def generate(self, llm_request: LLMRequest) -> LLMResponse:
        provider = llm_request.provider or self.settings.resolved_llm_default_provider
        protocol = self.settings.resolve_provider_protocol(provider)
        if llm_request.model:
            model = llm_request.model
        elif llm_request.provider is None:
            model = self.settings.resolved_llm_default_model or self._default_model_for_provider(provider, protocol)
        else:
            model = self._default_model_for_provider(provider, protocol)
        if protocol == "openai":
            return self._generate_openai(provider, model, llm_request)
        raise ValueError(f"Unsupported LLM provider: {provider}")

    def _generate_openai(
        self,
        provider: str,
        model: str,
        llm_request: LLMRequest,
    ) -> LLMResponse:
        api_key = self.settings.resolve_provider_api_key(provider)
        api_base = self.settings.resolve_provider_api_base(provider)
        pricing_provider = self.settings.resolve_provider_pricing_provider(provider)
        if not api_key:
            raise RuntimeError(f"Provider `{provider}` is missing an API key")
        if not api_base:
            raise RuntimeError(f"Provider `{provider}` is missing an API base URL")
        payload: dict[str, Any] = {
            "model": model,
            "messages": [message.model_dump() for message in llm_request.messages],
            "temperature": llm_request.temperature,
        }
        if llm_request.max_output_tokens is not None:
            payload["max_completion_tokens"] = llm_request.max_output_tokens
        started_at = perf_counter()
        response = self._post_with_retry(
            url=f"{api_base.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            payload=payload,
        )
        duration_seconds = perf_counter() - started_at
        content = self._extract_choice_text(response)
        usage = self._build_usage("openai", model, response.get("usage", {}), pricing_provider)
        usage = self.token_counter.estimate_openai_usage(
            model=model,
            messages=llm_request.messages,
            output_text=content,
            existing_usage=usage,
        )
        usage = usage.model_copy(
            update={
                "model_name": model,
                "provider": provider,
                "message_count": len(llm_request.messages),
                "duration_seconds": duration_seconds,
                "cost_usd": self.pricing.calculate_cost_usd(
                    provider=pricing_provider,
                    model=model,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    cache_read_tokens=usage.cache_read_tokens,
                    cache_write_tokens=usage.cache_write_tokens,
                ),
            }
        )
        return LLMResponse(
            provider=provider,
            model=model,
            output_text=content,
            usage=usage,
            response_id=response.get("id"),
        )

    def _build_usage(
        self,
        provider: str,
        model: str,
        usage_payload: dict[str, Any],
        pricing_provider: str | None = None,
    ) -> TokenUsage:
        raw_prompt_tokens = int(
            usage_payload.get("prompt_tokens")
            or usage_payload.get("input_tokens")
            or 0
        )
        prompt_details = usage_payload.get("prompt_tokens_details")
        completion_details = usage_payload.get("completion_tokens_details")
        cache_read_tokens = int(
            (
                prompt_details.get("cached_tokens")
                if isinstance(prompt_details, dict)
                else None
            )
            or usage_payload.get("cache_read_input_tokens")
            or 0
        )
        cache_write_tokens = int(
            usage_payload.get("cache_creation_input_tokens")
            or 0
        )
        reasoning_tokens = int(
            (
                completion_details.get("reasoning_tokens")
                if isinstance(completion_details, dict)
                else None
            )
            or usage_payload.get("reasoning_tokens")
            or 0
        )
        prompt_tokens = raw_prompt_tokens
        if provider == "minimax":
            prompt_tokens = raw_prompt_tokens + cache_read_tokens + cache_write_tokens
        completion_tokens = int(
            usage_payload.get("completion_tokens")
            or usage_payload.get("output_tokens")
            or 0
        )
        total_tokens = int(
            usage_payload.get("total_tokens")
            or prompt_tokens + completion_tokens
        )
        cost_usd = self.pricing.calculate_cost_usd(
            provider=pricing_provider or provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
        )
        return TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            reasoning_tokens=reasoning_tokens,
            model_name=model,
            provider=provider,
            cost_usd=cost_usd,
        )

    def _extract_choice_text(self, response: dict[str, Any]) -> str:
        choices = response.get("choices") or []
        if not choices:
            raise RuntimeError("LLM provider response did not include choices")
        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            return "\n".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("text")
            ).strip()
        if not isinstance(content, str):
            raise RuntimeError("LLM provider response content is not text")
        return content.strip()

    def _post_with_retry(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        max_attempts = self.settings.resolved_llm_request_max_attempts
        timeout = self.settings.resolved_llm_request_timeout_seconds
        base_delay = self.settings.resolved_llm_request_retry_base_delay_seconds
        last_error: RuntimeError | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                return self.transport.post_json(
                    url=url,
                    headers=headers,
                    payload=payload,
                    timeout=timeout,
                )
            except RuntimeError as exc:
                last_error = exc
                if attempt >= max_attempts:
                    break
                delay_seconds = base_delay * (2 ** (attempt - 1))
                if delay_seconds > 0:
                    self.sleep_fn(delay_seconds)

        assert last_error is not None
        raise last_error

    def _default_model_for_provider(self, provider: str, protocol: str) -> str:
        configured = self.settings.resolve_provider_default_model(provider)
        if configured:
            return configured
        if protocol == "openai":
            return self.settings.resolved_openai_model
        raise ValueError(f"Unsupported LLM provider: {provider}")
