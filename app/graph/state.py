from typing import TypedDict

from app.models.schemas import IntentType, TokenUsage


class WorkflowState(TypedDict):
    request_id: str
    run_id: str
    user_id: str
    source: str
    content: str
    intent: IntentType
    message: str
    token_usage: TokenUsage
