from __future__ import annotations

from dataclasses import dataclass

from app.models.schemas import IntentType


STATS_KEYWORDS = ("统计", "token", "消耗", "最近7天", "最近30天")
SLEEP_CODING_KEYWORDS = ("写代码", "修 bug", "修bug")
RALPH_MENTIONS = ("@ralph", "ralph", "切到 ralph", "交给 ralph")
REVIEW_MENTIONS = ("@review", "code-review", "code review", "review agent", "让 review")


@dataclass(frozen=True)
class GatewayRoute:
    intent: IntentType
    target_agent: str
    direct_mention: bool = False


def classify_intent(content: str) -> IntentType:
    return resolve_route(content).intent


def resolve_route(content: str) -> GatewayRoute:
    lowered = content.lower()
    if any(keyword in lowered for keyword in STATS_KEYWORDS):
        return GatewayRoute(intent="stats_query", target_agent="main-agent")
    if _contains_any(lowered, RALPH_MENTIONS):
        return GatewayRoute(intent="sleep_coding", target_agent="ralph", direct_mention=True)
    if _contains_any(lowered, REVIEW_MENTIONS):
        return GatewayRoute(intent="general", target_agent="main-agent")
    if any(keyword in lowered for keyword in SLEEP_CODING_KEYWORDS):
        return GatewayRoute(intent="sleep_coding", target_agent="ralph")
    return GatewayRoute(intent="general", target_agent="main-agent")


def _contains_any(content: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in content for pattern in patterns)
