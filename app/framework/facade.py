from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.framework.builtin_agents import BuiltinAgentEntry, builtin_agent_registry
from app.runtime.agent_runtime import AgentDescriptor


@dataclass(frozen=True)
class MartenFramework:
    settings: Settings

    def builtin_agents(self) -> dict[str, BuiltinAgentEntry]:
        return builtin_agent_registry(self.settings)

    def resolve_agent_descriptor(self, agent_id: str) -> AgentDescriptor:
        return AgentDescriptor.from_spec(self.settings.resolve_agent_spec(agent_id))

    def config_surface(self) -> dict[str, object]:
        return {
            "github_repository": self.settings.resolved_github_repository,
            "channel_provider": self.settings.resolved_channel_provider,
            "default_model_profile": self.settings.resolve_model_profile("default"),
            "builtin_agent_ids": list(self.builtin_agents().keys()),
        }

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "MartenFramework":
        return cls(settings=settings or Settings())
