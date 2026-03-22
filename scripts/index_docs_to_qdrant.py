from __future__ import annotations

import json
import sys
from pathlib import Path

from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = PROJECT_ROOT / "docs"
PLATFORM_CONFIG_PATH = PROJECT_ROOT / "platform.json"
MANIFESTS_ROOT = PROJECT_ROOT / ".rag-manifests" / "qdrant"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.rag.indexing import collect_markdown_chunks, load_manifest, plan_sync, write_manifest


def load_platform_config() -> dict[str, object]:
    return json.loads(PLATFORM_CONFIG_PATH.read_text(encoding="utf-8"))


def resolve_qdrant_config() -> tuple[str, dict[str, object], dict[str, object]]:
    config = load_platform_config()
    rag = config.get("rag", {})
    if not isinstance(rag, dict):
        raise ValueError("platform.json missing rag config")
    providers = rag.get("providers", {})
    domains = rag.get("domains", {})
    if not isinstance(providers, dict) or not isinstance(domains, dict):
        raise ValueError("rag providers/domains config is invalid")
    domain = domains.get("repo-docs")
    if not isinstance(domain, dict):
        raise ValueError("repo-docs domain is not configured")
    provider_id = str(domain.get("provider", "")).strip()
    provider = providers.get(provider_id)
    if not provider_id or not isinstance(provider, dict):
        raise ValueError("repo-docs provider config is missing")
    if str(provider.get("kind", "")).strip().lower() != "qdrant":
        raise ValueError("repo-docs provider is not qdrant")
    return provider_id, provider, domain


def manifest_path_for(collection_name: str) -> Path:
    return MANIFESTS_ROOT / f"{collection_name}.json"


def collection_vector_size(client: QdrantClient, collection_name: str) -> int | None:
    if not client.collection_exists(collection_name):
        return None
    info = client.get_collection(collection_name)
    vectors = info.config.params.vectors
    size = getattr(vectors, "size", None)
    return int(size) if size is not None else None


def main() -> None:
    provider_id, provider, domain = resolve_qdrant_config()
    url = str(provider.get("url", "http://127.0.0.1:6333"))
    model_name = str(provider.get("model_name", "BAAI/bge-small-zh-v1.5"))
    raw_model_path = str(provider.get("model_path", "")).strip()
    model_path = raw_model_path if raw_model_path and Path(raw_model_path).exists() else model_name
    device = str(provider.get("device", "cpu"))
    collection_name = str(domain.get("collection_name", "marten-docs"))

    client = QdrantClient(url=url)
    model = SentenceTransformer(model_path, device=device)
    chunks = collect_markdown_chunks(DOCS_ROOT)
    if not chunks:
        raise ValueError("No markdown chunks found under docs/")
    manifest_path = manifest_path_for(collection_name)
    plan = plan_sync(chunks, load_manifest(manifest_path))

    sample_vector = model.encode([chunks[0].content], normalize_embeddings=True)[0].tolist()
    vector_size = len(sample_vector)
    existing_vector_size = collection_vector_size(client, collection_name)
    recreated = existing_vector_size != vector_size
    if recreated:
        client.recreate_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        )
        plan = plan_sync(chunks, {})

    points: list[models.PointStruct] = []
    if plan.upserts:
        embeddings = model.encode(
            [chunk.content for chunk in plan.upserts],
            normalize_embeddings=True,
        )
        for chunk, vector in zip(plan.upserts, embeddings, strict=True):
            points.append(
                models.PointStruct(
                    id=chunk.item_ref,
                    vector=vector.tolist() if hasattr(vector, "tolist") else list(vector),
                    payload={
                        "title": chunk.title,
                        "content": chunk.content,
                        "source": chunk.source,
                        "path": chunk.path,
                        "provider_id": provider_id,
                    },
                )
            )
    if plan.delete_ids:
        client.delete(collection_name=collection_name, points_selector=plan.delete_ids, wait=True)
    if points:
        client.upsert(collection_name=collection_name, points=points, wait=True)
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
                "docs_root": str(DOCS_ROOT),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
