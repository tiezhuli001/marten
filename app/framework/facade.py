from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from app.channel.endpoints import ChannelEndpointRegistry
from app.control.context import ContextAssemblyService
from app.control.session_registry import SessionRegistryService
from app.control.task_registry import TaskRegistryService
from app.core.config import Settings
from app.framework.builtin_agents import BuiltinAgentEntry, builtin_agent_registry
from app.rag import RAGFacade
from app.runtime.agent_runtime import AgentDescriptor
from app.runtime.agent_runtime import AgentRuntime


@dataclass(frozen=True)
class MartenFramework:
    settings: Settings

    def builtin_agents(self) -> dict[str, BuiltinAgentEntry]:
        return builtin_agent_registry(self.settings)

    @cached_property
    def _sessions(self) -> SessionRegistryService:
        return SessionRegistryService(self.settings)

    @cached_property
    def _tasks(self) -> TaskRegistryService:
        return TaskRegistryService(self.settings)

    @cached_property
    def _channel_endpoints(self) -> ChannelEndpointRegistry:
        return ChannelEndpointRegistry(self.settings)

    @cached_property
    def _rag(self) -> RAGFacade:
        return RAGFacade(self.settings)

    @cached_property
    def _runtime(self) -> AgentRuntime:
        return AgentRuntime(settings=self.settings, rag=self._rag)

    @cached_property
    def _context(self) -> ContextAssemblyService:
        return ContextAssemblyService(self._sessions)

    def resolve_agent_descriptor(self, agent_id: str) -> AgentDescriptor:
        return AgentDescriptor.from_spec(self.settings.resolve_agent_spec(agent_id))

    def channel_endpoints(self) -> ChannelEndpointRegistry:
        return self._channel_endpoints

    def sessions(self) -> SessionRegistryService:
        return self._sessions

    def context(self) -> ContextAssemblyService:
        return self._context

    def tasks(self) -> TaskRegistryService:
        return self._tasks

    def runtime(self) -> AgentRuntime:
        return self._runtime

    def rag(self) -> RAGFacade:
        return self._rag

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
