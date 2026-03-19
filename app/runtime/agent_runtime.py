from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import AgentSpec, Settings
from app.models.schemas import LLMMessage, LLMRequest, LLMResponse
from app.runtime.llm import SharedLLMRuntime
from app.runtime.mcp import MCPClient
from app.runtime.skills import SkillLoader


@dataclass(frozen=True)
class AgentDescriptor:
    agent_id: str
    workspace: Path
    skill_names: list[str]
    mcp_servers: list[str]
    system_instruction: str
    model_profile: str | None = None
    memory_policy: str = "short-memory"
    execution_policy: str = "default"

    @classmethod
    def from_spec(cls, spec: AgentSpec) -> "AgentDescriptor":
        return cls(
            agent_id=spec.agent_id,
            workspace=spec.workspace,
            skill_names=spec.skills,
            mcp_servers=spec.mcp_servers,
            system_instruction=spec.system_instruction,
            model_profile=spec.model_profile,
            memory_policy=spec.memory_policy,
            execution_policy=spec.execution_policy,
        )


class AgentRuntime:
    def __init__(
        self,
        settings: Settings,
        llm_runtime: SharedLLMRuntime | None = None,
        skills: SkillLoader | None = None,
        mcp_client: MCPClient | None = None,
    ) -> None:
        self.settings = settings
        self.llm_runtime = llm_runtime or SharedLLMRuntime(settings)
        self.skills = skills or SkillLoader(settings)
        self.mcp = mcp_client or MCPClient()

    def generate_structured_output(
        self,
        agent: AgentDescriptor,
        *,
        user_prompt: str,
        output_contract: str,
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        profile_provider, profile_model = self.settings.resolve_model_profile(agent.model_profile)
        system_prompt = self._build_system_prompt(agent, output_contract)
        return self.llm_runtime.generate(
            LLMRequest(
                provider=provider or profile_provider,  # type: ignore[arg-type]
                model=model or profile_model,
                temperature=temperature,
                messages=[
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=user_prompt),
                ],
            )
        )

    def list_available_mcp_tools(self, servers: list[str]) -> list[str]:
        tools: list[str] = []
        for server in servers:
            try:
                server_tools = self.mcp.list_tools(server)
            except Exception:
                continue
            for tool in server_tools:
                tools.append(f"{server}.{tool.name}: {tool.description}".strip())
        return tools

    def _build_system_prompt(self, agent: AgentDescriptor, output_contract: str) -> str:
        skill_catalog = self.skills.render_skill_catalog(agent.skill_names, agent.workspace)
        skill_instructions = self._render_skill_instructions(agent)
        mcp_tools = self.list_available_mcp_tools(agent.mcp_servers)
        workspace_instructions = self._load_workspace_instructions(agent.workspace)
        mcp_section = (
            "\n".join(f"- {tool}" for tool in mcp_tools)
            if mcp_tools
            else "No MCP tools are currently available."
        )
        return (
            f"You are {agent.agent_id} for youmeng-gateway.\n"
            f"{agent.system_instruction}\n\n"
            "Priorities:\n"
            "1. Follow workspace and skill instructions.\n"
            "2. Prefer the listed skills for cognition-heavy work.\n"
            "3. Use MCP tools for external system operations; if required MCP tools are unavailable, stop and surface the missing configuration.\n\n"
            "Agent Policies:\n"
            f"- Memory Policy: {agent.memory_policy}\n"
            f"- Execution Policy: {agent.execution_policy}\n\n"
            "Workspace Instructions:\n"
            f"{workspace_instructions}\n\n"
            "Available Skills:\n"
            f"{skill_catalog}\n\n"
            "Loaded Skill Instructions:\n"
            f"{skill_instructions}\n\n"
            "Available MCP Tools:\n"
            f"{mcp_section}\n\n"
            "Output Contract:\n"
            f"{output_contract}"
        )

    def _load_workspace_instructions(self, workspace: Path) -> str:
        sections: list[str] = []
        for filename in ("AGENTS.md", "TOOLS.md", "SOUL.md"):
            path = workspace / filename
            if path.exists():
                sections.append(f"## {filename}\n{path.read_text(encoding='utf-8').strip()}")
        return "\n\n".join(sections) if sections else "No workspace instructions are configured."

    def _render_skill_instructions(self, agent: AgentDescriptor) -> str:
        skills = self.skills.resolve(agent.skill_names, agent.workspace)
        if not skills:
            return "No skill instructions are available."
        return "\n\n".join(
            f"## {skill.name}\n{skill.instructions}" for skill in skills
        )
