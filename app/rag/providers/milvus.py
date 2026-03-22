from __future__ import annotations

import json
from hashlib import sha1
from pathlib import Path

from app.rag.retrieval import (
    KnowledgeDomain,
    RetrievedDocument,
    RetrievalRequest,
    RetrievalResponse,
)


class _PymilvusClientAdapter:
    def __init__(
        self,
        *,
        uri: str,
        token: str | None,
        db_name: str,
        vector_field: str,
        primary_field: str,
    ) -> None:
        self.uri = uri
        self.token = token
        self.db_name = db_name
        self.vector_field = vector_field
        self.primary_field = primary_field
        self.alias = f"milvus_{sha1(f'{uri}:{db_name}:{primary_field}:{vector_field}'.encode('utf-8')).hexdigest()[:12]}"
        self._connected = False

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
        collection = self._collection(collection_name)
        return collection.search(
            data=data,
            anns_field=self.vector_field,
            param=search_params,
            limit=limit,
            expr=filter or None,
            output_fields=output_fields,
        )

    def get(
        self,
        *,
        collection_name: str,
        ids: list[str],
        output_fields: list[str],
    ) -> list[dict[str, object]]:
        collection = self._collection(collection_name)
        return collection.query(
            expr=self._id_expr(ids),
            output_fields=output_fields,
        )

    def _collection(self, collection_name: str):
        self._connect()
        from pymilvus import Collection

        collection = Collection(name=collection_name, using=self.alias)
        collection.load()
        return collection

    def _connect(self) -> None:
        if self._connected:
            return
        from pymilvus import connections

        connect_kwargs: dict[str, object] = {
            "alias": self.alias,
            "uri": self.uri,
            "db_name": self.db_name,
        }
        if self.token:
            connect_kwargs["token"] = self.token
        connections.connect(**connect_kwargs)
        self._connected = True

    def _id_expr(self, ids: list[str]) -> str:
        values = ", ".join(json.dumps(item) for item in ids)
        return f"{self.primary_field} in [{values}]"


class MilvusRetrievalProvider:
    def __init__(
        self,
        client=None,
        *,
        uri: str | None = None,
        token: str | None = None,
        db_name: str = "default",
        model_name: str = "BAAI/bge-small-zh-v1.5",
        model_path: str | None = None,
        device: str = "cpu",
        query_instruction: str = "为这个句子生成表示以用于检索相关文章：",
        search_params: dict[str, object] | None = None,
        vector_field: str = "vector",
        primary_field: str = "id",
        output_fields: list[str] | None = None,
    ) -> None:
        self.client = client
        self.uri = uri or "./milvus-data/marten-docs.db"
        self.token = token
        self.db_name = db_name
        self.model_name = model_name
        self.model_path = model_path
        self.device = device
        self.query_instruction = query_instruction
        self.search_params = dict(search_params or {"metric_type": "COSINE"})
        self.vector_field = vector_field
        self.primary_field = primary_field
        self.output_fields = output_fields or ["title", "content", "source"]
        self._embedder = None

    def search(
        self,
        request: RetrievalRequest,
        domain: KnowledgeDomain,
    ) -> RetrievalResponse:
        client = self._client()
        collection_name = self._collection_name(domain)
        query_vector = self._embed_query(request.query)
        rows = client.search(
            collection_name=collection_name,
            data=[query_vector],
            limit=request.top_k,
            output_fields=self.output_fields,
            filter=self._filter_expression(request.filters),
            search_params=self.search_params,
        )
        hits = rows[0] if rows and isinstance(rows[0], list) else rows
        results = [
            RetrievedDocument(
                domain_id=domain.domain_id,
                item_ref=f"{collection_name}:{self._row_id(row)}",
                title=str(self._row_entity(row).get("title", self._row_id(row))),
                content=str(self._row_entity(row).get("content", "")),
                source=str(self._row_entity(row).get("source", "milvus")),
                score=self._row_score(row),
                metadata={"provider": "milvus"},
            )
            for row in hits
        ]
        return RetrievalResponse(
            provider="milvus",
            results=results,
            debug={"domain_id": domain.domain_id},
        )

    def fetch(self, item_ref: str) -> RetrievedDocument | None:
        client = self._client()
        collection_name, point_id = self._split_item_ref(item_ref)
        rows = client.get(
            collection_name=collection_name,
            ids=[point_id],
            output_fields=self.output_fields,
        )
        if not rows:
            return None
        row = rows[0]
        return RetrievedDocument(
            domain_id=collection_name,
            item_ref=f"{collection_name}:{row.get(self.primary_field, point_id)}",
            title=str(row.get("title", row.get(self.primary_field, point_id))),
            content=str(row.get("content", "")),
            source=str(row.get("source", "milvus")),
            metadata={"provider": "milvus"},
        )

    def _client(self):
        if self.client is not None:
            return self.client
        self.client = _PymilvusClientAdapter(
            uri=self.uri,
            token=self.token,
            db_name=self.db_name,
            vector_field=self.vector_field,
            primary_field=self.primary_field,
        )
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

    def _filter_expression(self, filters: dict[str, object]) -> str:
        clauses: list[str] = []
        for key, value in filters.items():
            if isinstance(value, str):
                clauses.append(f"{key} == {json.dumps(value)}")
            elif isinstance(value, bool):
                clauses.append(f"{key} == {str(value).lower()}")
            elif isinstance(value, (int, float)):
                clauses.append(f"{key} == {value}")
        return " and ".join(clauses)

    def _row_entity(self, row) -> dict[str, object]:
        if isinstance(row, dict):
            entity = row.get("entity")
            if isinstance(entity, dict):
                return entity
            return row
        entity = getattr(row, "entity", None)
        if isinstance(entity, dict):
            return entity
        return {}

    def _row_id(self, row) -> str:
        if isinstance(row, dict):
            value = row.get("id", "")
            return str(value)
        return str(getattr(row, "id", ""))

    def _row_score(self, row) -> float | None:
        if isinstance(row, dict):
            score = row.get("score", row.get("distance"))
            return float(score) if score is not None else None
        score = getattr(row, "score", getattr(row, "distance", None))
        return float(score) if score is not None else None

    def _split_item_ref(self, item_ref: str) -> tuple[str, str]:
        if ":" not in item_ref:
            return "", item_ref
        collection_name, point_id = item_ref.split(":", 1)
        return collection_name, point_id
