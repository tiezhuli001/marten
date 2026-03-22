from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DocumentChunk:
    item_ref: str
    title: str
    content: str
    source: str
    path: str
    content_hash: str


@dataclass(frozen=True)
class SyncPlan:
    upserts: list[DocumentChunk]
    delete_ids: list[str]
    unchanged_count: int
    next_manifest: dict[str, str]


def stable_item_id(value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, digest))


def content_hash(*, title: str, content: str, source: str) -> str:
    payload = json.dumps(
        {"title": title, "content": content, "source": source},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def collect_markdown_chunks(docs_root: Path) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    docs_root = docs_root.resolve()
    source_prefix = docs_root.name
    for path in sorted(docs_root.rglob("*.md")):
        relative_path = path.relative_to(docs_root).as_posix()
        source_path = f"{source_prefix}/{relative_path}"
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        current_title = relative_path
        current_lines: list[str] = []
        title_occurrences: dict[str, int] = {}

        def flush() -> None:
            content = "\n".join(current_lines).strip()
            if not content:
                return
            title = current_title
            occurrence = title_occurrences.get(title, 0) + 1
            title_occurrences[title] = occurrence
            item_ref = stable_item_id(f"{source_path}:{title}:{occurrence}")
            chunks.append(
                DocumentChunk(
                    item_ref=item_ref,
                    title=title,
                    content=content,
                    source=source_path,
                    path=source_path,
                    content_hash=content_hash(title=title, content=content, source=source_path),
                )
            )

        for line in lines:
            if line.startswith("#"):
                flush()
                current_title = f"{relative_path}::{line.lstrip('#').strip()}"
                current_lines = [line]
                continue
            current_lines.append(line)
        flush()
    return chunks


def load_manifest(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in raw.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def write_manifest(path: Path, manifest: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def plan_sync(chunks: list[DocumentChunk], manifest: dict[str, str]) -> SyncPlan:
    next_manifest = {chunk.item_ref: chunk.content_hash for chunk in chunks}
    upserts = [
        chunk
        for chunk in chunks
        if manifest.get(chunk.item_ref) != chunk.content_hash
    ]
    delete_ids = sorted(item_ref for item_ref in manifest if item_ref not in next_manifest)
    unchanged_count = len(chunks) - len(upserts)
    return SyncPlan(
        upserts=upserts,
        delete_ids=delete_ids,
        unchanged_count=unchanged_count,
        next_manifest=next_manifest,
    )
