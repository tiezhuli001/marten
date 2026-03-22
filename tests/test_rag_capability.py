import json
import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings
from app.runtime.agent_runtime import AgentDescriptor, AgentRuntime


class FakeLLMRuntime:
    def __init__(self) -> None:
        self.requests = []

    def generate(self, llm_request):
        self.requests.append(llm_request)
        return type(
            "LLMResponseStub",
            (),
            {
                "output_text": json.dumps({"message": "ok"}),
                "usage": type("UsageStub", (), {"total_tokens": 10})(),
            },
        )()


class FakeQdrantClient:
    def __init__(self) -> None:
        self.last_query_points = None
        self.query_called = False

    def query(self, collection_name: str, query_text: str, limit: int, filters: dict[str, object]):
        self.query_called = True
        raise AssertionError("provider should not use deprecated query() path")

    def query_points(
        self,
        collection_name: str,
        query: list[float],
        limit: int,
        with_payload: bool,
    ):
        self.last_query_points = {
            "collection_name": collection_name,
            "query": query,
            "limit": limit,
            "with_payload": with_payload,
        }
        return [
            type(
                "PointStub",
                (),
                {
                    "id": "doc-1",
                    "payload": {
                        "title": f"{collection_name}:{query[0]}",
                        "content": "Qdrant adapter result.",
                        "source": "qdrant",
                    },
                    "score": 0.91,
                },
            )()
        ][:limit]

    def retrieve(self, collection_name: str, ids: list[str], with_payload: bool):
        return [
            type(
                "PointStub",
                (),
                {
                    "id": ids[0],
                    "payload": {
                        "title": f"{collection_name}:{ids[0]}",
                        "content": "Fetched from qdrant.",
                        "source": "qdrant",
                    },
                    "score": 0.88,
                },
            )()
        ]


class FakeMilvusClient:
    def __init__(self) -> None:
        self.last_search = None
        self.last_get = None

    def search(
        self,
        *,
        collection_name: str,
        data: list[list[float]],
        limit: int,
        output_fields: list[str],
        filter: str,
        search_params: dict[str, object],
    ):
        self.last_search = {
            "collection_name": collection_name,
            "data": data,
            "limit": limit,
            "output_fields": output_fields,
            "filter": filter,
            "search_params": search_params,
        }
        return [
            [
                {
                    "id": "doc-2",
                    "distance": 0.83,
                    "entity": {
                        "title": f"{collection_name}:{data[0][0]}",
                        "content": "Milvus adapter result.",
                        "source": "milvus",
                    },
                }
            ][:limit]
        ]

    def get(
        self,
        *,
        collection_name: str,
        ids: list[str],
        output_fields: list[str],
    ):
        self.last_get = {
            "collection_name": collection_name,
            "ids": ids,
            "output_fields": output_fields,
        }
        return [
            {
                "id": ids[0],
                "title": f"{collection_name}:{ids[0]}",
                "content": "Fetched from milvus.",
                "source": "milvus",
            }
        ]


class RAGCapabilityTests(unittest.TestCase):
    def test_vector_store_adapters_map_backend_results_to_unified_response(self) -> None:
        from app.rag import KnowledgeDomain, RetrievalRequest
        from app.rag.providers import MilvusRetrievalProvider, QdrantRetrievalProvider

        request = RetrievalRequest(
            query="review loop",
            agent_id="main-agent",
            workflow="general",
            domains=["repo-docs"],
            top_k=1,
        )
        domain = KnowledgeDomain(
            domain_id="repo-docs",
            domain_type="operational",
            owner="framework",
            visibility="shared",
            provider="qdrant",
        )

        qdrant_client = FakeQdrantClient()
        qdrant = QdrantRetrievalProvider(client=qdrant_client)
        qdrant._embed_query = lambda query: [0.25, 0.75]  # type: ignore[method-assign]
        qdrant_response = qdrant.search(request, domain)

        self.assertEqual(qdrant_response.provider, "qdrant")
        self.assertEqual(qdrant_response.results[0].source, "qdrant")
        self.assertEqual(qdrant_response.results[0].score, 0.91)
        self.assertEqual(
            qdrant_client.last_query_points,
            {
                "collection_name": "repo-docs",
                "query": [0.25, 0.75],
                "limit": 1,
                "with_payload": True,
            },
        )
        self.assertFalse(qdrant_client.query_called)

        milvus = MilvusRetrievalProvider(client=FakeMilvusClient())
        milvus._embed_query = lambda query: [0.6, 0.4]  # type: ignore[method-assign]
        milvus_response = milvus.search(
            request,
            domain.__class__(
                domain_id="repo-docs",
                domain_type="operational",
                owner="framework",
                visibility="shared",
                provider="milvus",
                metadata={"collection_name": "marten-docs"},
            ),
        )

        self.assertEqual(milvus_response.provider, "milvus")
        self.assertEqual(milvus_response.results[0].source, "milvus")
        self.assertEqual(milvus_response.results[0].score, 0.83)
        self.assertEqual(milvus_response.results[0].item_ref, "marten-docs:doc-2")
        self.assertEqual(
            milvus.client.last_search,
            {
                "collection_name": "marten-docs",
                "data": [[0.6, 0.4]],
                "limit": 1,
                "output_fields": ["title", "content", "source"],
                "filter": "",
                "search_params": {"metric_type": "COSINE"},
            },
        )
        fetched = milvus.fetch("marten-docs:doc-2")
        assert fetched is not None
        self.assertEqual(fetched.title, "marten-docs:doc-2")
        self.assertEqual(
            milvus.client.last_get,
            {
                "collection_name": "marten-docs",
                "ids": ["doc-2"],
                "output_fields": ["title", "content", "source"],
            },
        )

    def test_rag_facade_builds_milvus_provider_from_platform_config(self) -> None:
        from app.rag import RAGFacade
        from app.rag.providers import MilvusRetrievalProvider

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            platform_json = root / "platform.json"
            platform_json.write_text(
                json.dumps(
                    {
                        "rag": {
                            "providers": {
                                "local-milvus": {
                                    "kind": "milvus",
                                    "uri": "./milvus-local.db",
                                    "token": "",
                                    "model_name": "BAAI/bge-small-zh-v1.5",
                                    "model_path": "/tmp/bge-small-zh-v1.5",
                                    "device": "cpu",
                                    "search_params": {"metric_type": "COSINE"},
                                    "vector_field": "embedding",
                                    "primary_field": "doc_id",
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            facade = RAGFacade(Settings(platform_config_path=str(platform_json)))
            provider = facade.providers["local-milvus"]

            self.assertIsInstance(provider, MilvusRetrievalProvider)
            self.assertEqual(provider.uri, "./milvus-local.db")
            self.assertEqual(provider.model_name, "BAAI/bge-small-zh-v1.5")
            self.assertEqual(provider.model_path, "/tmp/bge-small-zh-v1.5")
            self.assertEqual(provider.vector_field, "embedding")
            self.assertEqual(provider.primary_field, "doc_id")

    def test_rag_facade_returns_unified_response_and_dedupes_results(self) -> None:
        from app.rag import InMemoryRetrievalProvider, RAGFacade

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            platform_json = root / "platform.json"
            platform_json.write_text(
                json.dumps(
                    {
                        "rag": {
                            "domains": {
                                "repo-docs": {
                                    "domain_type": "operational",
                                    "owner": "framework",
                                    "visibility": "shared",
                                    "provider": "memory",
                                },
                                "review-docs": {
                                    "domain_type": "operational",
                                    "owner": "framework",
                                    "visibility": "shared",
                                    "provider": "memory",
                                },
                            },
                            "policies": [
                                {
                                    "agent_id": "main-agent",
                                    "workflow": "general",
                                    "domains": ["repo-docs", "review-docs"],
                                    "top_k": 3,
                                    "trigger_mode": "always",
                                    "merge_mode": "append",
                                    "max_tokens": 300,
                                    "dedupe": True,
                                    "citation_mode": "inline",
                                }
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )
            settings = Settings(platform_config_path=str(platform_json))
            facade = RAGFacade(settings)
            facade.register_provider(
                "memory",
                InMemoryRetrievalProvider(
                    {
                        "repo-docs": [
                            {
                                "item_ref": "doc-1",
                                "title": "Routing Spec",
                                "content": "Route to the default agent when no explicit target exists.",
                                "source": "docs",
                            }
                        ],
                        "review-docs": [
                            {
                                "item_ref": "doc-1",
                                "title": "Routing Spec Duplicate",
                                "content": "This duplicate should be deduped.",
                                "source": "docs",
                            },
                            {
                                "item_ref": "doc-2",
                                "title": "Review Loop",
                                "content": "Blocking reviews rerun coding until the loop stops.",
                                "source": "docs",
                            },
                        ],
                    }
                ),
            )

            response = facade.retrieve_response(
                agent_id="main-agent",
                workflow="general",
                query="main agent should route requests and explain review loop",
            )

            self.assertEqual(response.provider, "memory")
            self.assertEqual([item.item_ref for item in response.results], ["doc-1", "doc-2"])
            self.assertFalse(response.truncated)
            self.assertEqual(response.debug["domains"], ["repo-docs", "review-docs"])
            self.assertEqual(response.debug["providers"], ["memory"])

    def test_inmemory_provider_supports_request_response_contract(self) -> None:
        from app.rag import InMemoryRetrievalProvider, KnowledgeDomain, RetrievalRequest

        provider = InMemoryRetrievalProvider(
            {
                "repo-docs": [
                    {
                        "item_ref": "doc-1",
                        "title": "Framework Surface",
                        "content": "Builtin agents should stay reusable through the framework facade.",
                        "source": "docs",
                    }
                ]
            }
        )

        response = provider.search(
            RetrievalRequest(
                query="framework facade",
                agent_id="main-agent",
                workflow="general",
                domains=["repo-docs"],
                top_k=1,
            ),
            KnowledgeDomain(
                domain_id="repo-docs",
                domain_type="operational",
                owner="framework",
                visibility="shared",
                provider="memory",
            ),
        )

        self.assertEqual(response.provider, "memory")
        self.assertEqual(len(response.results), 1)
        self.assertEqual(response.results[0].title, "Framework Surface")
        self.assertEqual(response.results[0].metadata["owner"], "framework")

    def test_rag_facade_resolves_policy_and_retrieves_domain_results(self) -> None:
        from app.rag import InMemoryRetrievalProvider, RAGFacade

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            platform_json = root / "platform.json"
            platform_json.write_text(
                json.dumps(
                    {
                        "rag": {
                            "domains": {
                                "repo-docs": {
                                    "domain_type": "operational",
                                    "owner": "framework",
                                    "visibility": "shared",
                                    "provider": "memory",
                                }
                            },
                            "policies": [
                                {
                                    "agent_id": "main-agent",
                                    "workflow": "general",
                                    "domains": ["repo-docs"],
                                    "top_k": 2,
                                    "trigger_mode": "always",
                                    "merge_mode": "append",
                                    "max_tokens": 300,
                                    "dedupe": True,
                                    "citation_mode": "inline",
                                }
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )
            settings = Settings(platform_config_path=str(platform_json))
            facade = RAGFacade(settings)
            facade.register_provider(
                "memory",
                InMemoryRetrievalProvider(
                    {
                        "repo-docs": [
                            {
                                "item_ref": "doc-1",
                                "title": "Routing Spec",
                                "content": "Multi-endpoint routing uses default agent bindings.",
                                "source": "docs",
                            }
                        ]
                    }
                ),
            )

            results = facade.retrieve(
                agent_id="main-agent",
                workflow="general",
                query="如何做多 endpoint routing",
            )

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].domain_id, "repo-docs")
            self.assertEqual(results[0].title, "Routing Spec")

    def test_agent_runtime_merges_retrieval_context_when_policy_is_always(self) -> None:
        from app.rag import InMemoryRetrievalProvider, RAGFacade

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            platform_json = root / "platform.json"
            workspace = root / "agents" / "main-agent"
            workspace.mkdir(parents=True)
            (workspace / "AGENTS.md").write_text("Main agent rules.", encoding="utf-8")
            platform_json.write_text(
                json.dumps(
                    {
                        "rag": {
                            "domains": {
                                "repo-docs": {
                                    "domain_type": "operational",
                                    "owner": "framework",
                                    "visibility": "shared",
                                    "provider": "memory",
                                }
                            },
                            "policies": [
                                {
                                    "agent_id": "main-agent",
                                    "workflow": "default",
                                    "domains": ["repo-docs"],
                                    "top_k": 1,
                                    "trigger_mode": "always",
                                    "merge_mode": "append",
                                    "max_tokens": 300,
                                    "dedupe": True,
                                    "citation_mode": "inline",
                                }
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )
            settings = Settings(platform_config_path=str(platform_json))
            rag = RAGFacade(settings)
            rag.register_provider(
                "memory",
                InMemoryRetrievalProvider(
                    {
                        "repo-docs": [
                            {
                                "item_ref": "doc-1",
                                "title": "Framework Surface",
                                "content": "Builtin agents should stay reusable through the framework facade.",
                                "source": "docs",
                            }
                        ]
                    }
                ),
            )
            fake_llm = FakeLLMRuntime()
            runtime = AgentRuntime(settings=settings, llm_runtime=fake_llm, rag=rag)

            runtime.generate_structured_output(
                AgentDescriptor(
                    agent_id="main-agent",
                    workspace=workspace,
                    skill_names=[],
                    mcp_servers=[],
                    system_instruction="Draft issues.",
                    model_profile="default",
                ),
                user_prompt="总结框架 public surface",
                output_contract="Return JSON.",
            )

            system_prompt = fake_llm.requests[0].messages[0].content
            self.assertIn("Retrieved Context", system_prompt)
            self.assertIn("Framework Surface", system_prompt)
            self.assertIn("framework facade", system_prompt)


if __name__ == "__main__":
    unittest.main()
