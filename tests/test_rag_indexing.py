import tempfile
import unittest
from pathlib import Path


class RAGIndexingTests(unittest.TestCase):
    def test_plan_sync_marks_upserts_deletes_and_unchanged_chunks(self) -> None:
        from app.rag.indexing import DocumentChunk, plan_sync

        chunks = [
            DocumentChunk(
                item_ref="doc-1",
                title="A",
                content="alpha",
                source="docs/a.md",
                path="docs/a.md",
                content_hash="hash-a",
            ),
            DocumentChunk(
                item_ref="doc-2",
                title="B",
                content="beta-new",
                source="docs/b.md",
                path="docs/b.md",
                content_hash="hash-b-new",
            ),
        ]
        manifest = {
            "doc-1": "hash-a",
            "doc-2": "hash-b-old",
            "doc-3": "hash-c",
        }

        plan = plan_sync(chunks, manifest)

        self.assertEqual(plan.unchanged_count, 1)
        self.assertEqual([chunk.item_ref for chunk in plan.upserts], ["doc-2"])
        self.assertEqual(plan.delete_ids, ["doc-3"])
        self.assertEqual(
            plan.next_manifest,
            {
                "doc-1": "hash-a",
                "doc-2": "hash-b-new",
            },
        )

    def test_markdown_chunker_builds_stable_ids_and_titles(self) -> None:
        from app.rag.indexing import collect_markdown_chunks

        with tempfile.TemporaryDirectory() as temp_dir:
            docs_root = Path(temp_dir) / "docs"
            docs_root.mkdir()
            path = docs_root / "guide.md"
            path.write_text(
                "# Intro\nfirst\n## Next\nsecond\n",
                encoding="utf-8",
            )

            chunks = collect_markdown_chunks(docs_root)

            self.assertEqual(len(chunks), 2)
            self.assertEqual(chunks[0].title, "guide.md::Intro")
            self.assertEqual(chunks[1].title, "guide.md::Next")
            self.assertEqual(chunks[0].path, "docs/guide.md")
            self.assertTrue(chunks[0].item_ref)
            self.assertNotEqual(chunks[0].item_ref, chunks[1].item_ref)

    def test_markdown_chunker_keeps_duplicate_titles_unique(self) -> None:
        from app.rag.indexing import collect_markdown_chunks

        with tempfile.TemporaryDirectory() as temp_dir:
            docs_root = Path(temp_dir) / "docs"
            docs_root.mkdir()
            path = docs_root / "dup.md"
            path.write_text(
                "# Same\nfirst\n# Same\nsecond\n",
                encoding="utf-8",
            )

            chunks = collect_markdown_chunks(docs_root)

            self.assertEqual([chunk.title for chunk in chunks], ["dup.md::Same", "dup.md::Same"])
            self.assertEqual(len({chunk.item_ref for chunk in chunks}), 2)


if __name__ == "__main__":
    unittest.main()
