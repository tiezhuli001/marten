import unittest
import json
import tempfile
from pathlib import Path

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

    def test_unknown_pricing_model_falls_back_to_zero_cost(self) -> None:
        registry = PricingRegistry(Settings())

        cost = registry.calculate_cost_usd(
            provider="openai",
            model="gpt-5.4-mini",
            prompt_tokens=1000,
            completion_tokens=500,
        )

        self.assertEqual(cost, 0.0)

    def test_missing_pricing_model_falls_back_to_zero_cost(self) -> None:
        registry = PricingRegistry(Settings())

        cost = registry.calculate_cost_usd(
            provider="openai",
            model=None,
            prompt_tokens=1000,
            completion_tokens=500,
        )

        self.assertEqual(cost, 0.0)

    def test_custom_provider_pricing_can_be_driven_from_models_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            models_json = root / "models.json"
            models_json.write_text(
                json.dumps(
                    {
                        "providers": {
                            "custom-openai": {
                                "protocol": "openai",
                                "api_key": "custom-key",
                                "api_base": "https://llm.example.com/v1",
                                "default_model": "custom-model",
                                "pricing": {
                                    "custom-model": {
                                        "inputPerMillion": 1.5,
                                        "outputPerMillion": 3.0,
                                    }
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            registry = PricingRegistry(Settings(models_config_path=str(models_json)))

            cost = registry.calculate_cost_usd(
                provider="custom-openai",
                model="custom-model",
                prompt_tokens=1_000_000,
                completion_tokens=500_000,
            )

        self.assertAlmostEqual(cost, 3.0)


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
                models_config_path="/tmp/non-existent-models.json",
                minimax_api_key="test-minimax-key",
                minimax_api_base="https://api.minimax.io/v1",
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
        self.assertEqual(response.usage.prompt_tokens, 200)
        self.assertEqual(response.usage.cache_read_tokens, 50)
        self.assertEqual(response.usage.cache_write_tokens, 25)
        self.assertEqual(response.usage.provider, "minimax")
        self.assertGreater(response.usage.cost_usd, 0)
        self.assertEqual(
            transport.calls[0]["url"],
            "https://api.minimax.io/v1/chat/completions",
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
                models_config_path="/tmp/non-existent-models.json",
                minimax_api_key="test-minimax-key",
                minimax_api_base="https://api.minimax.io/v1",
            ),
            transport=transport,
        )

        response = runtime.generate(
            LLMRequest(
                messages=[LLMMessage(role="user", content="cached prompt")],
                provider="minimax",
            )
        )

        self.assertGreater(response.usage.prompt_tokens, 0)
        self.assertEqual(
            response.usage.total_tokens,
            response.usage.prompt_tokens + response.usage.completion_tokens,
        )

    def test_generate_requires_configured_provider_key(self) -> None:
        runtime = SharedLLMRuntime(Settings())

        with self.assertRaisesRegex(RuntimeError, "Provider `openai` is missing an API key"):
            runtime.generate(
                LLMRequest(
                    messages=[LLMMessage(role="user", content="hello")],
                    provider="openai",
                )
            )

    def test_generate_does_not_inherit_openai_key_for_custom_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            models_json = root / "models.json"
            models_json.write_text(
                json.dumps(
                    {
                        "providers": {
                            "custom-openai": {
                                "protocol": "openai",
                                "api_base": "https://llm.example.com/v1",
                                "default_model": "custom-model",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            runtime = SharedLLMRuntime(
                Settings(
                    openai_api_key="env-openai-key",
                    models_config_path=str(models_json),
                )
            )

            with self.assertRaisesRegex(RuntimeError, "Provider `custom-openai` is missing an API key"):
                runtime.generate(
                    LLMRequest(
                        messages=[LLMMessage(role="user", content="hello")],
                        provider="custom-openai",
                        model="custom-model",
                    )
                )

    def test_generate_uses_models_json_provider_credentials_and_base(self) -> None:
        transport = FakeTransport(
            {
                "id": "resp-minimax-json",
                "choices": [{"message": {"content": "Hello from models.json"}}],
                "usage": {
                    "input_tokens": 20,
                    "output_tokens": 10,
                    "total_tokens": 30,
                },
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            models_json = root / "models.json"
            models_json.write_text(
                json.dumps(
                    {
                        "providers": {
                            "minimax": {
                                "api_key": "json-minimax-key",
                                "api_base": "https://api.minimax.io/v1",
                                "default_model": "MiniMax-M2.5",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            runtime = SharedLLMRuntime(
                Settings(
                    models_config_path=str(models_json),
                    minimax_api_key=None,
                    minimax_api_base="https://api.minimax.io/v1",
                ),
                transport=transport,
            )

            response = runtime.generate(
                LLMRequest(
                    messages=[LLMMessage(role="user", content="nihao")],
                    provider="minimax",
                )
            )

        self.assertEqual(response.output_text, "Hello from models.json")
        self.assertEqual(
            transport.calls[0]["url"],
            "https://api.minimax.io/v1/chat/completions",
        )
        self.assertEqual(
            transport.calls[0]["headers"]["Authorization"],
            "Bearer json-minimax-key",
        )

    def test_generate_supports_custom_openai_compatible_provider_from_models_json(self) -> None:
        transport = FakeTransport(
            {
                "id": "resp-custom-provider",
                "choices": [{"message": {"content": "Hello from custom provider"}}],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 8,
                    "total_tokens": 20,
                },
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            models_json = root / "models.json"
            models_json.write_text(
                json.dumps(
                    {
                        "profiles": {
                            "default": {
                                "model": "minimax-coding-plan/MiniMax-M2.5"
                            }
                        },
                        "providers": {
                            "minimax-coding-plan": {
                                "protocol": "openai",
                                "api_key": "custom-key",
                                "api_base": "https://llm.example.com/v1",
                                "default_model": "MiniMax-M2.5",
                                "pricing_provider": "minimax",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            runtime = SharedLLMRuntime(
                Settings(models_config_path=str(models_json)),
                transport=transport,
            )

            response = runtime.generate(
                LLMRequest(
                    messages=[LLMMessage(role="user", content="nihao")],
                )
            )

        self.assertEqual(response.provider, "minimax-coding-plan")
        self.assertEqual(response.model, "MiniMax-M2.5")
        self.assertEqual(response.output_text, "Hello from custom provider")
        self.assertEqual(transport.calls[0]["url"], "https://llm.example.com/v1/chat/completions")
        self.assertEqual(transport.calls[0]["headers"]["Authorization"], "Bearer custom-key")

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
