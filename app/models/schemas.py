from typing import Literal

from pydantic import BaseModel, Field

IntentType = Literal["general", "stats_query", "sleep_coding"]


class TokenUsage(BaseModel):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class GatewayMessageRequest(BaseModel):
    user_id: str
    content: str
    source: str = "manual"


class GatewayMessageResponse(BaseModel):
    request_id: str
    intent: IntentType
    message: str
    token_usage: TokenUsage
