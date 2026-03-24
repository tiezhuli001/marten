from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.core.config import Settings


@dataclass(frozen=True)
class KnowledgeDomain:
    domain_id: str
    domain_type: str
    owner: str
    visibility: str
    provider: str
    metadata: dict[str, object] = field(default_factory=dict)


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
    injection_mode: str = "inline"


@dataclass(frozen=True)
class RetrievedDocument:
    domain_id: str
    item_ref: str
    title: str
    content: str
    source: str
    score: float | None = None
    metadata: dict[str, object] = field(default_factory=dict)


RetrievalResult = RetrievedDocument


@dataclass(frozen=True)
class RetrievalRequest:
    query: str
    agent_id: str
    workflow: str
    domains: list[str]
    top_k: int
    filters: dict[str, object] = field(default_factory=dict)
    query_mode: str = "semantic"
    include_citations: bool = True


@dataclass(frozen=True)
class RetrievalResponse:
    provider: str
    results: list[RetrievedDocument]
    latency_ms: int | None = None
    truncated: bool = False
    debug: dict[str, object] = field(default_factory=dict)


class RetrievalProvider(Protocol):
    def search(
        self,
        request: RetrievalRequest,
        domain: KnowledgeDomain,
    ) -> RetrievalResponse: ...

    def fetch(self, item_ref: str) -> RetrievedDocument | None: ...


class InMemoryRetrievalProvider:
    def __init__(self, items_by_domain: dict[str, list[dict[str, str]]]) -> None:
        self.items_by_domain = items_by_domain

    def search(
        self,
        request: RetrievalRequest,
        domain: KnowledgeDomain,
    ) -> RetrievalResponse:
        top_k = max(int(request.top_k), 1)
        results = [
            RetrievedDocument(
                domain_id=domain.domain_id,
                item_ref=item["item_ref"],
                title=item["title"],
                content=item["content"],
                source=item.get("source", domain.owner),
                metadata={"owner": domain.owner, "visibility": domain.visibility},
            )
            for item in self.items_by_domain.get(domain.domain_id, [])[:top_k]
        ]
        return RetrievalResponse(
            provider="memory",
            results=results,
            debug={"domain_id": domain.domain_id},
        )

    def fetch(self, item_ref: str) -> RetrievedDocument | None:
        for domain_id, items in self.items_by_domain.items():
            for item in items:
                if item.get("item_ref") == item_ref:
                    return RetrievedDocument(
                        domain_id=domain_id,
                        item_ref=item_ref,
                        title=item["title"],
                        content=item["content"],
                        source=item.get("source", domain_id),
                        metadata={},
                    )
        return None


class RAGFacade:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.providers: dict[str, RetrievalProvider] = {}
        self._register_configured_providers()

    def register_provider(self, provider_id: str, provider: RetrievalProvider) -> None:
        self.providers[provider_id] = provider

    def retrieve(self, *, agent_id: str, workflow: str, query: str) -> list[RetrievalResult]:
        return self.retrieve_response(
            agent_id=agent_id,
            workflow=workflow,
            query=query,
        ).results

    def retrieve_response(
        self,
        *,
        agent_id: str,
        workflow: str,
        query: str,
        filters: dict[str, object] | None = None,
        query_mode: str = "semantic",
        include_citations: bool = True,
    ) -> RetrievalResponse:
        policy = self.resolve_policy(agent_id=agent_id, workflow=workflow)
        if policy is None or policy.trigger_mode in {"never", "fallback_only"}:
            return RetrievalResponse(provider="none", results=[], debug={"reason": "policy_disabled"})
        request = RetrievalRequest(
            query=query,
            agent_id=agent_id,
            workflow=workflow,
            domains=policy.domains,
            top_k=policy.top_k,
            filters=filters or {},
            query_mode=query_mode,
            include_citations=include_citations,
        )
        results: list[RetrievedDocument] = []
        providers_used: list[str] = []
        for domain_id in policy.domains:
            domain = self.resolve_domain(domain_id)
            if domain is None:
                continue
            provider = self.providers.get(domain.provider)
            if provider is None:
                continue
            provider_response = provider.search(request, domain)
            providers_used.append(provider_response.provider)
            results.extend(provider_response.results)
        merge_policy = self.resolve_merge_policy(agent_id=agent_id, workflow=workflow)
        processed, unique_result_count = self._post_process_results(
            results,
            top_k=policy.top_k,
            dedupe=merge_policy.dedupe,
        )
        distinct_providers = sorted({provider for provider in providers_used if provider})
        provider_name = distinct_providers[0] if len(distinct_providers) == 1 else "multi"
        return RetrievalResponse(
            provider=provider_name or "none",
            results=processed,
            truncated=unique_result_count > len(processed),
            debug={
                "domains": policy.domains,
                "providers": distinct_providers,
                "query_mode": query_mode,
            },
        )

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
            metadata={
                key: value
                for key, value in raw.items()
                if key not in {"domain_type", "owner", "visibility", "provider"}
            },
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
                    injection_mode=str(raw.get("injection_mode", "inline")),
                )
        return ContextMergePolicy(
            merge_mode="append",
            max_tokens=600,
            dedupe=True,
            citation_mode="inline",
            injection_mode="inline",
        )

    def _rag_config(self) -> dict[str, object]:
        raw = self.settings.platform_config.get("rag", {})
        return raw if isinstance(raw, dict) else {}

    def _register_configured_providers(self) -> None:
        rag = self._rag_config()
        raw_providers = rag.get("providers", {})
        if not isinstance(raw_providers, dict):
            return
        for provider_id, raw_provider in raw_providers.items():
            if not isinstance(provider_id, str) or not provider_id.strip():
                continue
            if not isinstance(raw_provider, dict):
                continue
            provider = self._build_provider(raw_provider)
            if provider is None:
                continue
            self.register_provider(provider_id.strip(), provider)

    def _build_provider(self, raw_provider: dict[str, object]) -> RetrievalProvider | None:
        kind = str(raw_provider.get("kind", "")).strip().lower()
        if not kind:
            return None
        if kind == "qdrant":
            from app.rag.providers import QdrantRetrievalProvider

            return QdrantRetrievalProvider(
                url=str(raw_provider.get("url", "http://127.0.0.1:6333")).strip(),
                api_key=str(raw_provider.get("api_key", "")).strip() or None,
                model_name=str(raw_provider.get("model_name", "BAAI/bge-small-zh-v1.5")).strip(),
                model_path=str(raw_provider.get("model_path", "")).strip() or None,
                device=str(raw_provider.get("device", "cpu")).strip(),
                query_instruction=str(
                    raw_provider.get(
                        "query_instruction",
                        "为这个句子生成表示以用于检索相关文章：",
                    )
                ),
            )
        if kind == "milvus":
            from app.rag.providers import MilvusRetrievalProvider

            raw_search_params = raw_provider.get("search_params", {"metric_type": "COSINE"})
            search_params = raw_search_params if isinstance(raw_search_params, dict) else {"metric_type": "COSINE"}
            raw_output_fields = raw_provider.get("output_fields", ["title", "content", "source"])
            output_fields = (
                [str(field) for field in raw_output_fields if isinstance(field, str)]
                if isinstance(raw_output_fields, list)
                else ["title", "content", "source"]
            )
            return MilvusRetrievalProvider(
                uri=str(raw_provider.get("uri", "./milvus-data/marten-docs.db")).strip(),
                token=str(raw_provider.get("token", "")).strip() or None,
                db_name=str(raw_provider.get("db_name", "default")).strip(),
                model_name=str(raw_provider.get("model_name", "BAAI/bge-small-zh-v1.5")).strip(),
                model_path=str(raw_provider.get("model_path", "")).strip() or None,
                device=str(raw_provider.get("device", "cpu")).strip(),
                query_instruction=str(
                    raw_provider.get(
                        "query_instruction",
                        "为这个句子生成表示以用于检索相关文章：",
                    )
                ),
                search_params=search_params,
                vector_field=str(raw_provider.get("vector_field", "vector")).strip(),
                primary_field=str(raw_provider.get("primary_field", "id")).strip(),
                output_fields=output_fields,
            )
        return None

    def _post_process_results(
        self,
        results: list[RetrievedDocument],
        *,
        top_k: int,
        dedupe: bool,
    ) -> tuple[list[RetrievedDocument], int]:
        if not dedupe:
            return results[:top_k], len(results)
        unique_results: list[RetrievedDocument] = []
        seen_refs: set[str] = set()
        for item in results:
            if item.item_ref in seen_refs:
                continue
            seen_refs.add(item.item_ref)
            unique_results.append(item)
        processed: list[RetrievedDocument] = []
        for item in unique_results:
            processed.append(item)
            if len(processed) >= top_k:
                break
        return processed, len(unique_results)
