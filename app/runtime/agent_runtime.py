from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import AgentSpec, Settings
from app.models.schemas import LLMMessage, LLMRequest, LLMResponse
from app.rag import RAGFacade
from app.runtime.llm import SharedLLMRuntime
from app.runtime.mcp import MCPClient
from app.runtime.context_policy import (
    PromptSection,
    assemble_prompt_sections,
    resolve_prompt_assembly_policy,
)
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
        rag: RAGFacade | None = None,
    ) -> None:
        self.settings = settings
        self.llm_runtime = llm_runtime or SharedLLMRuntime(settings)
        self.skills = skills or SkillLoader(settings)
        self.mcp = mcp_client or MCPClient()
        self.rag = rag or RAGFacade(settings)

    def generate_structured_output(
        self,
        agent: AgentDescriptor,
        *,
        user_prompt: str,
        output_contract: str,
        workflow: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        profile_provider, profile_model = self.settings.resolve_model_profile(agent.model_profile)
        system_prompt = self._build_system_prompt(
            agent,
            output_contract,
            user_prompt=user_prompt,
            workflow=workflow,
        )
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
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to load MCP tools for server `{server}`: {exc}"
                ) from exc
            for tool in server_tools:
                tools.append(f"{server}.{tool.name}: {tool.description}".strip())
        return tools

    def _build_system_prompt(
        self,
        agent: AgentDescriptor,
        output_contract: str,
        *,
        user_prompt: str,
        workflow: str | None,
    ) -> str:
        prompt_policy = resolve_prompt_assembly_policy(
            self.settings,
            agent_id=agent.agent_id,
            workflow=workflow,
        )
        skill_catalog = self.skills.render_skill_catalog(agent.skill_names, agent.workspace)
        skill_instructions = self._render_skill_instructions(agent)
        mcp_tools = self.list_available_mcp_tools(agent.mcp_servers)
        workspace_instructions = self._load_workspace_instructions(agent.workspace)
        rag_context = self._render_retrieved_context(agent, user_prompt, workflow=workflow)
        mcp_section = (
            "\n".join(f"- {tool}" for tool in mcp_tools)
            if mcp_tools
            else "No MCP tools are currently available."
        )
        return assemble_prompt_sections(
            [
                PromptSection(
                    title="Bootstrap Instructions",
                    content=(
                        f"You are {agent.agent_id} for {self.settings.app_name}.\n"
                        f"{agent.system_instruction}\n\n"
                        "Priorities:\n"
                        "1. Follow workspace and skill instructions.\n"
                        "2. Prefer the listed skills for cognition-heavy work.\n"
                        "3. Use MCP tools for external system operations; if required MCP tools are unavailable, stop and surface the missing configuration."
                    ),
                    priority=100,
                    required=True,
                ),
                PromptSection(
                    title="Agent Policies",
                    content=(
                        f"- Memory Policy: {agent.memory_policy}\n"
                        f"- Execution Policy: {agent.execution_policy}"
                    ),
                    priority=95,
                    required=True,
                ),
                PromptSection(
                    title="Workspace Instructions",
                    content=workspace_instructions,
                    priority=80,
                ),
                PromptSection(
                    title="Available Skills",
                    content=skill_catalog,
                    priority=50,
                ),
                PromptSection(
                    title="Loaded Skill Instructions",
                    content=skill_instructions,
                    priority=40,
                ),
                PromptSection(
                    title="Available MCP Tools",
                    content=mcp_section,
                    priority=60,
                ),
                PromptSection(
                    title="Retrieved Context",
                    content=rag_context,
                    priority=30,
                ),
                PromptSection(
                    title="Output Contract",
                    content=output_contract,
                    priority=100,
                    required=True,
                ),
            ],
            policy=prompt_policy,
        )

    def _load_workspace_instructions(self, workspace: Path) -> str:
        sections: list[str] = []
        for filename in ("AGENTS.md", "TOOLS.md"):
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

    def _render_retrieved_context(
        self,
        agent: AgentDescriptor,
        user_prompt: str,
        *,
        workflow: str | None,
    ) -> str:
        active_workflow = workflow.strip() if isinstance(workflow, str) and workflow.strip() else "default"
        results = self.rag.retrieve(
            agent_id=agent.agent_id,
            workflow=active_workflow,
            query=user_prompt,
        )
        if not results:
            return "No retrieved context."
        merge_policy = self.rag.resolve_merge_policy(
            agent_id=agent.agent_id,
            workflow=active_workflow,
        )
        if merge_policy.injection_mode == "disabled":
            return "Policy: disabled\nRetrieved context is disabled for prompt injection."
        if merge_policy.injection_mode == "runtime_only":
            return "Policy: runtime_only\nRetrieved documents are available to the runtime but are not injected into the prompt."
        lines: list[str] = []
        used_chars = 0
        for item in results:
            snippet = f"- [{item.domain_id}] {item.title}: {item.content}"
            used_chars += len(snippet)
            if used_chars > merge_policy.max_tokens:
                break
            lines.append(snippet)
        return "\n".join(lines) if lines else "No retrieved context."
