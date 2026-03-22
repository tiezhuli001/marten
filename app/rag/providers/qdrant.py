from __future__ import annotations

from pathlib import Path

from app.rag.retrieval import (
    KnowledgeDomain,
    RetrievedDocument,
    RetrievalRequest,
    RetrievalResponse,
)


class QdrantRetrievalProvider:
    def __init__(
        self,
        client=None,
        *,
        url: str | None = None,
        api_key: str | None = None,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        model_path: str | None = None,
        device: str = "cpu",
        query_instruction: str = "为这个句子生成表示以用于检索相关文章：",
    ) -> None:
        self.client = client
        self.url = url
        self.api_key = api_key
        self.model_name = model_name
        self.model_path = model_path
        self.device = device
        self.query_instruction = query_instruction
        self._embedder = None

    def search(
        self,
        request: RetrievalRequest,
        domain: KnowledgeDomain,
    ) -> RetrievalResponse:
        client = self._client()
        query_vector = self._embed_query(request.query)
        collection_name = self._collection_name(domain)
        rows = self._query_points(
            client=client,
            collection_name=collection_name,
            query_vector=query_vector,
            limit=request.top_k,
        )
        results = [
            RetrievedDocument(
                domain_id=domain.domain_id,
                item_ref=f"{collection_name}:{row['id']}",
                title=str(row.get("payload", {}).get("title", row["id"])),
                content=str(row.get("payload", {}).get("content", "")),
                source=str(row.get("payload", {}).get("source", "qdrant")),
                score=float(row["score"]) if row.get("score") is not None else None,
                metadata={"provider": "qdrant"},
            )
            for row in rows
        ]
        return RetrievalResponse(
            provider="qdrant",
            results=results,
            debug={"domain_id": domain.domain_id},
        )

    def fetch(self, item_ref: str) -> RetrievedDocument | None:
        client = self._client()
        collection_name, point_id = self._split_item_ref(item_ref)
        row = self._retrieve_point(client=client, collection_name=collection_name, item_ref=point_id)
        if row is None:
            return None
        payload = row.get("payload", {})
        return RetrievedDocument(
            domain_id=collection_name,
            item_ref=f"{collection_name}:{row['id']}",
            title=str(payload.get("title", row["id"])),
            content=str(payload.get("content", "")),
            source=str(payload.get("source", "qdrant")),
            score=float(row["score"]) if row.get("score") is not None else None,
            metadata={"provider": "qdrant"},
        )

    def _client(self):
        if self.client is not None:
            return self.client
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:  # pragma: no cover - runtime dependency path
            raise RuntimeError("qdrant-client is not installed") from exc
        self.client = QdrantClient(url=self.url or "http://127.0.0.1:6333", api_key=self.api_key)
        return self.client

    def _model(self):
        if self._embedder is not None:
            return self._embedder
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - runtime dependency path
            raise RuntimeError("sentence-transformers is not installed") from exc
        model_ref = (
            self.model_path
            if self.model_path and Path(self.model_path).exists()
            else self.model_name
        )
        self._embedder = SentenceTransformer(model_ref, device=self.device)
        return self._embedder

    def _embed_query(self, query: str) -> list[float]:
        text = f"{self.query_instruction}{query}".strip()
        vector = self._model().encode([text], normalize_embeddings=True)
        row = vector[0]
        return row.tolist() if hasattr(row, "tolist") else list(row)

    def _collection_name(self, domain: KnowledgeDomain) -> str:
        raw = domain.metadata.get("collection_name")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return domain.domain_id

    def _query_points(
        self,
        *,
        client,
        collection_name: str,
        query_vector: list[float],
        limit: int,
    ) -> list[dict[str, object]]:
        if hasattr(client, "query_points"):
            response = client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=limit,
                with_payload=True,
            )
        elif hasattr(client, "query"):
            return client.query(
                collection_name=collection_name,
                query_text=query_vector,
                limit=limit,
                filters={},
            )
        else:
            raise RuntimeError("Qdrant client does not support query_points or query")
        points = getattr(response, "points", response)
        rows: list[dict[str, object]] = []
        for point in points:
            rows.append(
                {
                    "id": getattr(point, "id", None),
                    "payload": getattr(point, "payload", {}) or {},
                    "score": getattr(point, "score", None),
                }
            )
        return rows

    def _retrieve_point(self, *, client, collection_name: str, item_ref: str) -> dict[str, object] | None:
        if hasattr(client, "fetch"):
            return client.fetch(collection_name=collection_name, item_ref=item_ref)
        rows = client.retrieve(
            collection_name=collection_name,
            ids=[item_ref],
            with_payload=True,
        )
        if not rows:
            return None
        point = rows[0]
        return {
            "id": getattr(point, "id", item_ref),
            "payload": getattr(point, "payload", {}) or {},
            "score": getattr(point, "score", None),
        }

    def _split_item_ref(self, item_ref: str) -> tuple[str, str]:
        if ":" not in item_ref:
            return "", item_ref
        collection_name, point_id = item_ref.split(":", 1)
        return collection_name, point_id
