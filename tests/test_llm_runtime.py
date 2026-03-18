import unittest

from app.core.config import Settings
from app.models.schemas import LLMMessage, LLMRequest
from app.runtime.llm import SharedLLMRuntime
from app.runtime.pricing import PricingRegistry


class FakeTransport:
    def __init__(self, response_payload):
        self.response_payload = response_payload
        self.calls = []

    def post_json(self, *, url, headers, payload, timeout):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "payload": payload,
                "timeout": timeout,
            }
        )
        return self.response_payload


class FlakyTransport:
    def __init__(self, failures, response_payload):
        self.failures = failures
        self.response_payload = response_payload
        self.calls = []

    def post_json(self, *, url, headers, payload, timeout):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "payload": payload,
                "timeout": timeout,
            }
        )
        if self.failures:
            failure = self.failures.pop(0)
            raise failure
        return self.response_payload


class PricingRegistryTests(unittest.TestCase):
    def test_openai_cost_is_calculated_in_usd(self) -> None:
        registry = PricingRegistry(Settings())

        cost = registry.calculate_cost_usd(
            provider="openai",
            model="gpt-4.1-mini",
            prompt_tokens=500_000,
            completion_tokens=250_000,
        )

        self.assertAlmostEqual(cost, 0.6)

    def test_minimax_cost_is_converted_to_usd(self) -> None:
        registry = PricingRegistry(Settings())

        cost = registry.calculate_cost_usd(
            provider="minimax",
            model="MiniMax-M2.5",
            prompt_tokens=1_000_000,
            completion_tokens=500_000,
        )

        self.assertAlmostEqual(cost, 0.9)

    def test_cached_tokens_are_not_double_charged(self) -> None:
        registry = PricingRegistry(Settings())

        cost = registry.calculate_cost_usd(
            provider="minimax",
            model="MiniMax-M2.5",
            prompt_tokens=100_050,
            completion_tokens=393,
            cache_read_tokens=100_000,
            cache_write_tokens=0,
        )

        self.assertAlmostEqual(cost, 0.0034866, places=7)


class SharedLLMRuntimeTests(unittest.TestCase):
    def test_generate_openai_normalizes_usage(self) -> None:
        transport = FakeTransport(
            {
                "id": "resp-openai-1",
                "choices": [{"message": {"content": "Hello from OpenAI"}}],
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 30,
                    "total_tokens": 150,
                    "prompt_tokens_details": {"cached_tokens": 20},
                    "completion_tokens_details": {"reasoning_tokens": 6},
                },
            }
        )
        runtime = SharedLLMRuntime(
            Settings(openai_api_key="test-openai-key"),
            transport=transport,
        )

        response = runtime.generate(
            LLMRequest(
                messages=[LLMMessage(role="user", content="hello")],
                provider="openai",
            )
        )

        self.assertEqual(response.provider, "openai")
        self.assertEqual(response.model, "gpt-4.1-mini")
        self.assertEqual(response.output_text, "Hello from OpenAI")
        self.assertEqual(response.usage.prompt_tokens, 120)
        self.assertEqual(response.usage.completion_tokens, 30)
        self.assertEqual(response.usage.total_tokens, 150)
        self.assertEqual(response.usage.cache_read_tokens, 20)
        self.assertEqual(response.usage.reasoning_tokens, 6)
        self.assertEqual(response.usage.message_count, 1)
        self.assertEqual(response.usage.provider, "openai")
        self.assertGreater(response.usage.cost_usd, 0)
        self.assertEqual(
            transport.calls[0]["url"],
            "https://api.openai.com/v1/chat/completions",
        )

    def test_generate_minimax_normalizes_usage(self) -> None:
        transport = FakeTransport(
            {
                "id": "resp-minimax-1",
                "choices": [{"message": {"content": "Hello from MiniMax"}}],
                "usage": {
                    "input_tokens": 200,
                    "output_tokens": 80,
                    "total_tokens": 280,
                    "cache_read_input_tokens": 50,
                    "cache_creation_input_tokens": 25,
                },
            }
        )
        runtime = SharedLLMRuntime(
            Settings(
                minimax_api_key="test-minimax-key",
                minimax_api_base="https://api.minimaxi.com",
            ),
            transport=transport,
        )

        response = runtime.generate(
            LLMRequest(
                messages=[LLMMessage(role="user", content="nihao")],
                provider="minimax",
            )
        )

        self.assertEqual(response.provider, "minimax")
        self.assertEqual(response.model, "MiniMax-M2.5")
        self.assertEqual(response.output_text, "Hello from MiniMax")
        self.assertEqual(response.usage.total_tokens, 280)
        self.assertEqual(response.usage.prompt_tokens, 275)
        self.assertEqual(response.usage.cache_read_tokens, 50)
        self.assertEqual(response.usage.cache_write_tokens, 25)
        self.assertEqual(response.usage.provider, "minimax")
        self.assertGreater(response.usage.cost_usd, 0)
        self.assertEqual(
            transport.calls[0]["url"],
            "https://api.minimaxi.com/v1/text/chatcompletion_v2",
        )

    def test_generate_minimax_counts_cached_input_in_prompt_total(self) -> None:
        transport = FakeTransport(
            {
                "id": "resp-minimax-2",
                "choices": [{"message": {"content": "cached answer"}}],
                "usage": {
                    "input_tokens": 50,
                    "output_tokens": 20,
                    "cache_read_input_tokens": 100_000,
                },
            }
        )
        runtime = SharedLLMRuntime(
            Settings(
                minimax_api_key="test-minimax-key",
                minimax_api_base="https://api.minimaxi.com",
            ),
            transport=transport,
        )

        response = runtime.generate(
            LLMRequest(
                messages=[LLMMessage(role="user", content="cached prompt")],
                provider="minimax",
            )
        )

        self.assertEqual(response.usage.prompt_tokens, 100_050)
        self.assertEqual(response.usage.total_tokens, 100_070)

    def test_generate_requires_configured_provider_key(self) -> None:
        runtime = SharedLLMRuntime(Settings())

        with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
            runtime.generate(
                LLMRequest(
                    messages=[LLMMessage(role="user", content="hello")],
                    provider="openai",
                )
            )

    def test_generate_openai_estimates_usage_when_provider_omits_it(self) -> None:
        transport = FakeTransport(
            {
                "id": "resp-openai-2",
                "choices": [{"message": {"content": "Estimated tokens"}}],
                "usage": {},
            }
        )
        runtime = SharedLLMRuntime(
            Settings(openai_api_key="test-openai-key"),
            transport=transport,
        )

        response = runtime.generate(
            LLMRequest(
                messages=[LLMMessage(role="user", content="estimate token usage please")],
                provider="openai",
            )
        )

        self.assertGreater(response.usage.prompt_tokens, 0)
        self.assertGreater(response.usage.completion_tokens, 0)
        self.assertEqual(
            response.usage.total_tokens,
            response.usage.prompt_tokens + response.usage.completion_tokens,
        )

    def test_generate_retries_transport_failures_with_exponential_backoff(self) -> None:
        transport = FlakyTransport(
            failures=[
                RuntimeError("temporary network error"),
                RuntimeError("temporary provider error"),
            ],
            response_payload={
                "id": "resp-openai-retry",
                "choices": [{"message": {"content": "Recovered"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )
        delays = []
        runtime = SharedLLMRuntime(
            Settings(
                openai_api_key="test-openai-key",
                llm_request_max_attempts=3,
                llm_request_retry_base_delay_seconds=1.0,
            ),
            transport=transport,
            sleep_fn=delays.append,
        )

        response = runtime.generate(
            LLMRequest(
                messages=[LLMMessage(role="user", content="retry please")],
                provider="openai",
            )
        )

        self.assertEqual(response.output_text, "Recovered")
        self.assertEqual(len(transport.calls), 3)
        self.assertEqual(delays, [1.0, 2.0])

    def test_generate_raises_after_max_attempts(self) -> None:
        transport = FlakyTransport(
            failures=[
                RuntimeError("attempt 1 failed"),
                RuntimeError("attempt 2 failed"),
                RuntimeError("attempt 3 failed"),
            ],
            response_payload={},
        )
        delays = []
        runtime = SharedLLMRuntime(
            Settings(
                openai_api_key="test-openai-key",
                llm_request_max_attempts=3,
                llm_request_retry_base_delay_seconds=0.5,
            ),
            transport=transport,
            sleep_fn=delays.append,
        )

        with self.assertRaisesRegex(RuntimeError, "attempt 3 failed"):
            runtime.generate(
                LLMRequest(
                    messages=[LLMMessage(role="user", content="still broken")],
                    provider="openai",
                )
            )

        self.assertEqual(len(transport.calls), 3)
        self.assertEqual(delays, [0.5, 1.0])


if __name__ == "__main__":
    unittest.main()
