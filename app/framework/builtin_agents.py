from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.code_review_agent import ReviewService
from app.agents.main_agent import MainAgentService
from app.agents.ralph import SleepCodingService
from app.core.config import Settings


@dataclass(frozen=True)
class BuiltinAgentEntry:
    agent_id: str
    public_id: str
    service_type: type[Any]
    runtime_policy: dict[str, str]


def builtin_agent_registry(settings: Settings | None = None) -> dict[str, BuiltinAgentEntry]:
    active_settings = settings or Settings()
    return {
        "main-agent": BuiltinAgentEntry(
            agent_id="main-agent",
            public_id="main-agent",
            service_type=MainAgentService,
            runtime_policy={
                "session_scope": "user_session",
                "memory_policy": active_settings.resolve_agent_spec("main-agent").memory_policy,
                "execution_policy": active_settings.resolve_agent_spec("main-agent").execution_policy,
            },
        ),
        "ralph": BuiltinAgentEntry(
            agent_id="ralph",
            public_id="ralph",
            service_type=SleepCodingService,
            runtime_policy={
                "session_scope": "task",
                "memory_policy": active_settings.resolve_agent_spec("ralph").memory_policy,
                "execution_policy": active_settings.resolve_agent_spec("ralph").execution_policy,
            },
        ),
        "code-review-agent": BuiltinAgentEntry(
            agent_id="code-review-agent",
            public_id="code-review-agent",
            service_type=ReviewService,
            runtime_policy={
                "session_scope": "task",
                "memory_policy": active_settings.resolve_agent_spec("code-review-agent").memory_policy,
                "execution_policy": active_settings.resolve_agent_spec("code-review-agent").execution_policy,
            },
        ),
    }
