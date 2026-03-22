from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.config import Settings


@dataclass(frozen=True)
class KnowledgeDomain:
    domain_id: str
    domain_type: str
    owner: str
    visibility: str
    provider: str


@dataclass(frozen=True)
class RetrievalPolicy:
    agent_id: str
    workflow: str
    domains: list[str]
    top_k: int
    trigger_mode: str


@dataclass(frozen=True)
class ContextMergePolicy:
    merge_mode: str
    max_tokens: int
    dedupe: bool
    citation_mode: str


@dataclass(frozen=True)
class RetrievalResult:
    domain_id: str
    item_ref: str
    title: str
    content: str
    source: str


class RetrievalProvider(Protocol):
    def search(
        self,
        query: str,
        domain: KnowledgeDomain,
        options: dict[str, object],
    ) -> list[RetrievalResult]: ...

    def fetch(self, item_ref: str) -> RetrievalResult | None: ...


class InMemoryRetrievalProvider:
    def __init__(self, items_by_domain: dict[str, list[dict[str, str]]]) -> None:
        self.items_by_domain = items_by_domain

    def search(
        self,
        query: str,
        domain: KnowledgeDomain,
        options: dict[str, object],
    ) -> list[RetrievalResult]:
        del query
        top_k = int(options.get("top_k", 3))
        return [
            RetrievalResult(
                domain_id=domain.domain_id,
                item_ref=item["item_ref"],
                title=item["title"],
                content=item["content"],
                source=item.get("source", domain.owner),
            )
            for item in self.items_by_domain.get(domain.domain_id, [])[:top_k]
        ]

    def fetch(self, item_ref: str) -> RetrievalResult | None:
        for domain_id, items in self.items_by_domain.items():
            for item in items:
                if item.get("item_ref") == item_ref:
                    return RetrievalResult(
                        domain_id=domain_id,
                        item_ref=item_ref,
                        title=item["title"],
                        content=item["content"],
                        source=item.get("source", domain_id),
                    )
        return None


class RAGFacade:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.providers: dict[str, RetrievalProvider] = {}

    def register_provider(self, provider_id: str, provider: RetrievalProvider) -> None:
        self.providers[provider_id] = provider

    def retrieve(self, *, agent_id: str, workflow: str, query: str) -> list[RetrievalResult]:
        policy = self.resolve_policy(agent_id=agent_id, workflow=workflow)
        if policy is None or policy.trigger_mode in {"never", "fallback_only"}:
            return []
        results: list[RetrievalResult] = []
        seen_refs: set[str] = set()
        for domain_id in policy.domains:
            domain = self.resolve_domain(domain_id)
            if domain is None:
                continue
            provider = self.providers.get(domain.provider)
            if provider is None:
                continue
            for item in provider.search(query, domain, {"top_k": policy.top_k}):
                if item.item_ref in seen_refs:
                    continue
                seen_refs.add(item.item_ref)
                results.append(item)
        return results

    def resolve_domain(self, domain_id: str) -> KnowledgeDomain | None:
        rag = self._rag_config()
        raw_domains = rag.get("domains", {})
        if not isinstance(raw_domains, dict):
            return None
        raw = raw_domains.get(domain_id)
        if not isinstance(raw, dict):
            return None
        provider = raw.get("provider")
        if not isinstance(provider, str) or not provider.strip():
            return None
        return KnowledgeDomain(
            domain_id=domain_id,
            domain_type=str(raw.get("domain_type", "operational")),
            owner=str(raw.get("owner", "framework")),
            visibility=str(raw.get("visibility", "shared")),
            provider=provider.strip(),
        )

    def resolve_policy(
        self,
        *,
        agent_id: str,
        workflow: str,
    ) -> RetrievalPolicy | None:
        rag = self._rag_config()
        raw_policies = rag.get("policies", [])
        if not isinstance(raw_policies, list):
            return None
        for raw in raw_policies:
            if not isinstance(raw, dict):
                continue
            if raw.get("agent_id") != agent_id:
                continue
            raw_workflow = str(raw.get("workflow", "default"))
            if raw_workflow not in {workflow, "default"}:
                continue
            return RetrievalPolicy(
                agent_id=agent_id,
                workflow=raw_workflow,
                domains=[
                    str(domain_id).strip()
                    for domain_id in raw.get("domains", [])
                    if isinstance(domain_id, str) and domain_id.strip()
                ],
                top_k=max(int(raw.get("top_k", 3)), 1),
                trigger_mode=str(raw.get("trigger_mode", "never")),
            )
        return None

    def resolve_merge_policy(self, *, agent_id: str, workflow: str) -> ContextMergePolicy:
        rag = self._rag_config()
        raw_policies = rag.get("policies", [])
        if isinstance(raw_policies, list):
            for raw in raw_policies:
                if not isinstance(raw, dict):
                    continue
                if raw.get("agent_id") != agent_id:
                    continue
                raw_workflow = str(raw.get("workflow", "default"))
                if raw_workflow not in {workflow, "default"}:
                    continue
                return ContextMergePolicy(
                    merge_mode=str(raw.get("merge_mode", "append")),
                    max_tokens=max(int(raw.get("max_tokens", 600)), 1),
                    dedupe=bool(raw.get("dedupe", True)),
                    citation_mode=str(raw.get("citation_mode", "inline")),
                )
        return ContextMergePolicy(
            merge_mode="append",
            max_tokens=600,
            dedupe=True,
            citation_mode="inline",
        )

    def _rag_config(self) -> dict[str, object]:
        raw = self.settings.platform_config.get("rag", {})
        return raw if isinstance(raw, dict) else {}
