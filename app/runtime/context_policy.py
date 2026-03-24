from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

from app.core.config import Settings


@dataclass(frozen=True)
class PromptAssemblyPolicy:
    max_chars: int | None = None


@dataclass(frozen=True)
class PromptSection:
    title: str
    content: str
    priority: int
    required: bool = False

    def render(self) -> str:
        return f"{self.title}:\n{self.content}".strip()


def _coerce_positive_int(value: object) -> int | None:
    if value in {None, ""}:
        return None
    return max(int(value), 1)


def resolve_prompt_assembly_policy(
    settings: Settings,
    *,
    agent_id: str | None = None,
    workflow: str | None = None,
) -> PromptAssemblyPolicy:
    runtime_config = settings.platform_config.get("agent_runtime", {})
    if not isinstance(runtime_config, dict):
        return PromptAssemblyPolicy()
    raw_policy = runtime_config.get("context_policy", {})
    if not isinstance(raw_policy, dict):
        return PromptAssemblyPolicy()
    raw_max_chars = _coerce_positive_int(raw_policy.get("max_chars"))

    if isinstance(agent_id, str) and agent_id.strip():
        by_agent = raw_policy.get("max_chars_by_agent")
        if isinstance(by_agent, Mapping):
            agent_override = _coerce_positive_int(by_agent.get(agent_id.strip()))
            if agent_override is not None:
                raw_max_chars = agent_override

    if isinstance(agent_id, str) and agent_id.strip() and isinstance(workflow, str) and workflow.strip():
        by_workflow = raw_policy.get("max_chars_by_workflow")
        if isinstance(by_workflow, Mapping):
            key = f"{agent_id.strip()}:{workflow.strip()}"
            workflow_override = _coerce_positive_int(by_workflow.get(key))
            if workflow_override is not None:
                raw_max_chars = workflow_override

    return PromptAssemblyPolicy(max_chars=raw_max_chars)


def assemble_prompt_sections(
    sections: list[PromptSection],
    *,
    policy: PromptAssemblyPolicy,
) -> str:
    if policy.max_chars is None:
        return "\n\n".join(section.render() for section in sections if section.content.strip())

    rendered = {index: section.render() for index, section in enumerate(sections) if section.content.strip()}
    included: set[int] = set()
    used_chars = 0

    for index, section in enumerate(sections):
        if index not in rendered:
            continue
        if section.required:
            included.add(index)
            used_chars += len(rendered[index]) + (2 if used_chars else 0)

    optional_indexes = [
        index
        for index, section in enumerate(sections)
        if index in rendered and not section.required
    ]
    optional_indexes.sort(key=lambda index: sections[index].priority, reverse=True)

    for index in optional_indexes:
        candidate = rendered[index]
        separator = 2 if used_chars else 0
        if used_chars + separator + len(candidate) > policy.max_chars:
            continue
        included.add(index)
        used_chars += separator + len(candidate)

    ordered = [rendered[index] for index in range(len(sections)) if index in included]
    return "\n\n".join(ordered)
