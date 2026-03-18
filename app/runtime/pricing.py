from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.core.config import Settings


@dataclass(frozen=True)
class PricingRule:
    input_per_million: Decimal
    output_per_million: Decimal
    cache_read_per_million: Decimal = Decimal("0")
    cache_write_per_million: Decimal = Decimal("0")
    currency: str = "USD"


class PricingRegistry:
    _RULES: dict[str, dict[str, PricingRule]] = {
        "openai": {
            "gpt-4.1-mini": PricingRule(
                input_per_million=Decimal("0.40"),
                output_per_million=Decimal("1.60"),
                cache_read_per_million=Decimal("0.10"),
            ),
        },
        "minimax": {
            "MiniMax-M2.5": PricingRule(
                input_per_million=Decimal("0.30"),
                output_per_million=Decimal("1.20"),
                cache_read_per_million=Decimal("0.03"),
                cache_write_per_million=Decimal("0.375"),
            ),
        },
    }

    def __init__(self, settings: Settings) -> None:
        self._minimax_usd_per_cny = Decimal(str(settings.minimax_usd_per_cny))

    def calculate_cost_usd(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> float:
        rule = self.get_rule(provider, model)
        billable_prompt_tokens = max(
            prompt_tokens - cache_read_tokens - cache_write_tokens,
            0,
        )
        prompt_cost = self._per_million_cost(rule.input_per_million, billable_prompt_tokens)
        completion_cost = self._per_million_cost(
            rule.output_per_million,
            completion_tokens,
        )
        cache_read_cost = self._per_million_cost(
            rule.cache_read_per_million,
            cache_read_tokens,
        )
        cache_write_cost = self._per_million_cost(
            rule.cache_write_per_million,
            cache_write_tokens,
        )
        total_cost = prompt_cost + completion_cost + cache_read_cost + cache_write_cost
        if rule.currency == "CNY":
            total_cost *= self._minimax_usd_per_cny
        return float(total_cost.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP))

    def get_rule(self, provider: str, model: str) -> PricingRule:
        provider_rules = self._RULES.get(provider)
        if provider_rules is None:
            raise ValueError(f"Unsupported pricing provider: {provider}")
        if model in provider_rules:
            return provider_rules[model]
        for prefix, rule in provider_rules.items():
            if model.startswith(prefix):
                return rule
        raise ValueError(f"Unsupported pricing model: {provider}/{model}")

    def _per_million_cost(self, rate: Decimal, tokens: int) -> Decimal:
        return (rate * Decimal(tokens)) / Decimal(1_000_000)
