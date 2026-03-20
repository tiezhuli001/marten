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
    _ZERO_RULE = PricingRule(
        input_per_million=Decimal("0"),
        output_per_million=Decimal("0"),
    )
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
        self._settings = settings
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

    def get_rule(self, provider: str, model: str | None) -> PricingRule:
        provider_rules = self._load_provider_rules(provider)
        if provider_rules is None:
            return self._ZERO_RULE
        if not model:
            return self._ZERO_RULE
        if model in provider_rules:
            return provider_rules[model]
        for prefix, rule in provider_rules.items():
            if model.startswith(prefix):
                return rule
        return self._ZERO_RULE

    def _load_provider_rules(self, provider: str) -> dict[str, PricingRule] | None:
        provider_config = self._settings._get_provider_config(provider)
        configured_rules = self._parse_provider_rules(
            self._settings._get_provider_value(
                provider_config,
                "pricing",
                "pricing.models",
            )
        )
        if configured_rules:
            return configured_rules
        builtin_rules = self._RULES.get(provider)
        if builtin_rules is not None:
            return builtin_rules
        pricing_provider = self._settings.resolve_provider_pricing_provider(provider)
        if pricing_provider != provider:
            return self._RULES.get(pricing_provider)
        return None

    def _parse_provider_rules(self, raw: object) -> dict[str, PricingRule]:
        if not isinstance(raw, dict):
            return {}
        rules: dict[str, PricingRule] = {}
        for model, payload in raw.items():
            if not isinstance(model, str) or not model.strip() or not isinstance(payload, dict):
                continue
            input_rate = self._coerce_decimal(
                payload.get("input_per_million", payload.get("inputPerMillion"))
            )
            output_rate = self._coerce_decimal(
                payload.get("output_per_million", payload.get("outputPerMillion"))
            )
            if input_rate is None or output_rate is None:
                continue
            rules[model.strip()] = PricingRule(
                input_per_million=input_rate,
                output_per_million=output_rate,
                cache_read_per_million=self._coerce_decimal(
                    payload.get("cache_read_per_million", payload.get("cacheReadPerMillion"))
                ) or Decimal("0"),
                cache_write_per_million=self._coerce_decimal(
                    payload.get("cache_write_per_million", payload.get("cacheWritePerMillion"))
                ) or Decimal("0"),
                currency=str(payload.get("currency", "USD")).strip() or "USD",
            )
        return rules

    def _coerce_decimal(self, value: object) -> Decimal | None:
        if value in {None, ""}:
            return None
        return Decimal(str(value))

    def _per_million_cost(self, rate: Decimal, tokens: int) -> Decimal:
        return (rate * Decimal(tokens)) / Decimal(1_000_000)
