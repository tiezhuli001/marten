from app.models.schemas import IntentType


STATS_KEYWORDS = ("统计", "token", "消耗", "最近7天", "最近30天")
SLEEP_CODING_KEYWORDS = ("写代码", "修 bug", "修bug", "issue", "pr", "review")


def classify_intent(content: str) -> IntentType:
    lowered = content.lower()
    if any(keyword in lowered for keyword in STATS_KEYWORDS):
        return "stats_query"
    if any(keyword in lowered for keyword in SLEEP_CODING_KEYWORDS):
        return "sleep_coding"
    return "general"
