from __future__ import annotations

import json
import sys
from pathlib import Path

from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility
from sentence_transformers import SentenceTransformer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = PROJECT_ROOT / "docs"
PLATFORM_CONFIG_PATH = PROJECT_ROOT / "platform.json"
MANIFESTS_ROOT = PROJECT_ROOT / ".rag-manifests" / "milvus"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.rag.indexing import collect_markdown_chunks, load_manifest, plan_sync, write_manifest


def load_platform_config() -> dict[str, object]:
    return json.loads(PLATFORM_CONFIG_PATH.read_text(encoding="utf-8"))


def resolve_milvus_config() -> tuple[str, dict[str, object], dict[str, object]]:
    config = load_platform_config()
    rag = config.get("rag", {})
    if not isinstance(rag, dict):
        raise ValueError("platform.json missing rag config")
    providers = rag.get("providers", {})
    domains = rag.get("domains", {})
    if not isinstance(providers, dict) or not isinstance(domains, dict):
        raise ValueError("rag providers/domains config is invalid")
    domain = domains.get("repo-docs-milvus")
    if not isinstance(domain, dict):
        raise ValueError("repo-docs-milvus domain is not configured")
    provider_id = str(domain.get("provider", "")).strip()
    provider = providers.get(provider_id)
    if not provider_id or not isinstance(provider, dict):
        raise ValueError("repo-docs-milvus provider config is missing")
    if str(provider.get("kind", "")).strip().lower() != "milvus":
        raise ValueError("repo-docs-milvus provider is not milvus")
    return provider_id, provider, domain


def manifest_path_for(collection_name: str) -> Path:
    return MANIFESTS_ROOT / f"{collection_name}.json"


def connect_alias(provider_id: str, uri: str) -> str:
    safe_provider = provider_id.replace("-", "_")
    return f"{safe_provider}_{Path(uri).stem}"


def ensure_collection(
    *,
    alias: str,
    collection_name: str,
    vector_dim: int,
    vector_field: str,
    primary_field: str,
) -> bool:
    recreated = False
    if utility.has_collection(collection_name, using=alias):
        collection = Collection(collection_name, using=alias)
        field = next(
            (item for item in collection.schema.fields if item.name == vector_field),
            None,
        )
        existing_dim = getattr(field, "params", {}).get("dim") if field is not None else None
        if int(existing_dim or 0) != vector_dim:
            utility.drop_collection(collection_name, using=alias)
            recreated = True
    if not utility.has_collection(collection_name, using=alias):
        fields = [
            FieldSchema(name=primary_field, dtype=DataType.VARCHAR, is_primary=True, auto_id=False, max_length=64),
            FieldSchema(name=vector_field, dtype=DataType.FLOAT_VECTOR, dim=vector_dim),
            FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=1024),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=1024),
            FieldSchema(name="path", dtype=DataType.VARCHAR, max_length=1024),
        ]
        schema = CollectionSchema(fields=fields, enable_dynamic_field=False)
        collection = Collection(name=collection_name, schema=schema, using=alias)
        collection.create_index(vector_field, {"index_type": "AUTOINDEX", "metric_type": "COSINE"})
        recreated = True
    return recreated


def main() -> None:
    provider_id, provider, domain = resolve_milvus_config()
    uri = str(provider.get("uri", "./milvus-data/marten-docs.db")).strip()
    token = str(provider.get("token", "")).strip()
    db_name = str(provider.get("db_name", "default")).strip()
    model_name = str(provider.get("model_name", "BAAI/bge-small-zh-v1.5"))
    raw_model_path = str(provider.get("model_path", "")).strip()
    model_path = raw_model_path if raw_model_path and Path(raw_model_path).exists() else model_name
    device = str(provider.get("device", "cpu"))
    collection_name = str(domain.get("collection_name", "marten-docs-milvus"))
    vector_field = str(provider.get("vector_field", "vector")).strip()
    primary_field = str(provider.get("primary_field", "id")).strip()

    alias = connect_alias(provider_id, uri)
    connect_kwargs: dict[str, object] = {"alias": alias, "uri": uri, "db_name": db_name}
    if token:
        connect_kwargs["token"] = token
    connections.connect(**connect_kwargs)
    try:
        model = SentenceTransformer(model_path, device=device)
        chunks = collect_markdown_chunks(DOCS_ROOT)
        if not chunks:
            raise ValueError("No markdown chunks found under docs/")

        sample_vector = model.encode([chunks[0].content], normalize_embeddings=True)[0].tolist()
        vector_dim = len(sample_vector)
        recreated = ensure_collection(
            alias=alias,
            collection_name=collection_name,
            vector_dim=vector_dim,
            vector_field=vector_field,
            primary_field=primary_field,
        )
        collection = Collection(collection_name, using=alias)
        collection.load()

        manifest_path = manifest_path_for(collection_name)
        plan = plan_sync(chunks, {} if recreated else load_manifest(manifest_path))

        if plan.delete_ids:
            quoted_ids = ", ".join(json.dumps(item) for item in plan.delete_ids)
            collection.delete(expr=f"{primary_field} in [{quoted_ids}]")

        if plan.upserts:
            embeddings = model.encode(
                [chunk.content for chunk in plan.upserts],
                normalize_embeddings=True,
            )
            rows = []
            for chunk, vector in zip(plan.upserts, embeddings, strict=True):
                rows.append(
                    {
                        primary_field: chunk.item_ref,
                        vector_field: vector.tolist() if hasattr(vector, "tolist") else list(vector),
                        "title": chunk.title,
                        "content": chunk.content,
                        "source": chunk.source,
                        "path": chunk.path,
                    }
                )
            collection.upsert(rows)

        write_manifest(manifest_path, plan.next_manifest)
        print(
            json.dumps(
                {
                    "provider_id": provider_id,
                    "collection_name": collection_name,
                    "chunks_total": len(chunks),
                    "chunks_upserted": len(plan.upserts),
                    "chunks_deleted": len(plan.delete_ids),
                    "chunks_unchanged": plan.unchanged_count,
                    "collection_recreated": recreated,
                    "manifest_path": str(manifest_path),
                    "model_name": model_name,
                    "uri": uri,
                    "docs_root": str(DOCS_ROOT),
                },
                ensure_ascii=False,
            )
        )
    finally:
        connections.disconnect(alias)


if __name__ == "__main__":
    main()
