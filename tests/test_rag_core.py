from __future__ import annotations

import shutil
import sys
import unittest
import uuid
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from langchain_core.documents import Document

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import ragnos.core as rag_core

TEST_TMP_ROOT = Path(".files") / "test-temp"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


@contextmanager
def workspace_tempdir():
    path = TEST_TMP_ROOT / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class FingerprintTests(unittest.TestCase):
    def test_fingerprint_changes_when_file_stats_change(self) -> None:
        with workspace_tempdir() as docs_dir:
            pdf_path = docs_dir / "sample.pdf"
            pdf_path.write_bytes(b"first")

            first = rag_core.get_docs_fingerprint([pdf_path])
            same = rag_core.get_docs_fingerprint([pdf_path])
            pdf_path.write_bytes(b"second-version")
            changed = rag_core.get_docs_fingerprint([pdf_path])

        self.assertEqual(first, same)
        self.assertNotEqual(first, changed)


class IngestTests(unittest.TestCase):
    def test_ingest_noop_skips_rebuild_when_fingerprint_matches(self) -> None:
        with workspace_tempdir() as root:
            docs_dir = root / "documents"
            chroma_dir = root / "chroma"
            docs_dir.mkdir()
            chroma_dir.mkdir()

            pdf_path = docs_dir / "sample.pdf"
            pdf_path.write_bytes(b"fake")
            docs_fingerprint = rag_core.get_docs_fingerprint([pdf_path])

            rag_core.marker_file(chroma_dir).write_text(docs_fingerprint, encoding="utf-8")
            (chroma_dir / "existing.bin").write_text("ready", encoding="utf-8")

            config = rag_core.load_config(
                docs_dir=str(docs_dir),
                chroma_dir=str(chroma_dir),
            )

            with patch("ragnos.core.load_all_pdfs") as load_mock, patch("ragnos.core.build_chroma_store") as build_mock:
                result = rag_core.ingest_corpus(config)

        self.assertEqual(result.status, "up_to_date")
        load_mock.assert_not_called()
        build_mock.assert_not_called()

    def test_ingest_rebuilds_index_and_updates_fingerprint(self) -> None:
        with workspace_tempdir() as root:
            docs_dir = root / "documents"
            chroma_dir = root / "chroma"
            docs_dir.mkdir()
            chroma_dir.mkdir()

            pdf_path = docs_dir / "sample.pdf"
            pdf_path.write_bytes(b"fake")
            expected_fingerprint = rag_core.get_docs_fingerprint([pdf_path])

            rag_core.marker_file(chroma_dir).write_text("stale", encoding="utf-8")
            (chroma_dir / "stale.bin").write_text("old", encoding="utf-8")

            config = rag_core.load_config(
                docs_dir=str(docs_dir),
                chroma_dir=str(chroma_dir),
            )
            fake_docs = [Document(page_content="Article 1", metadata={"page": 0})]

            def fake_build(documents, embeddings, persist_directory):
                persist_directory.mkdir(parents=True, exist_ok=True)
                (persist_directory / "index.bin").write_text("new", encoding="utf-8")
                return object()

            with patch("ragnos.core.load_all_pdfs", return_value=(fake_docs, [pdf_path])) as load_mock, patch(
                "ragnos.core.create_embeddings", return_value=object()
            ) as embeddings_mock, patch("ragnos.core.build_chroma_store", side_effect=fake_build) as build_mock:
                result = rag_core.ingest_corpus(config)

            self.assertEqual(result.status, "rebuilt")
            self.assertEqual(result.pdf_count, 1)
            self.assertTrue(load_mock.called)
            self.assertTrue(embeddings_mock.called)
            self.assertTrue(build_mock.called)
            self.assertEqual(rag_core.read_index_fingerprint(chroma_dir), expected_fingerprint)
            self.assertTrue((chroma_dir / "index.bin").exists())
            self.assertFalse((chroma_dir / "stale.bin").exists())


class RuntimeValidationTests(unittest.TestCase):
    def test_missing_index_is_actionable(self) -> None:
        with workspace_tempdir() as root:
            docs_dir = root / "documents"
            docs_dir.mkdir()
            (docs_dir / "sample.pdf").write_bytes(b"fake")

            config = rag_core.load_config(
                docs_dir=str(docs_dir),
                chroma_dir=str(root / "missing-index"),
            )
            result = rag_core.validate_runtime_readiness(config)

        self.assertEqual(result.status, "missing_index")
        self.assertIn(rag_core.INGEST_COMMAND, result.message)

    def test_empty_index_is_actionable(self) -> None:
        with workspace_tempdir() as root:
            docs_dir = root / "documents"
            chroma_dir = root / "chroma"
            docs_dir.mkdir()
            chroma_dir.mkdir()

            pdf_path = docs_dir / "sample.pdf"
            pdf_path.write_bytes(b"fake")
            docs_fingerprint = rag_core.get_docs_fingerprint([pdf_path])
            rag_core.marker_file(chroma_dir).write_text(docs_fingerprint, encoding="utf-8")

            config = rag_core.load_config(
                docs_dir=str(docs_dir),
                chroma_dir=str(chroma_dir),
            )
            result = rag_core.validate_runtime_readiness(config)

        self.assertEqual(result.status, "empty_index")
        self.assertIn(rag_core.INGEST_COMMAND, result.message)

    def test_stale_index_is_actionable(self) -> None:
        with workspace_tempdir() as root:
            docs_dir = root / "documents"
            chroma_dir = root / "chroma"
            docs_dir.mkdir()
            chroma_dir.mkdir()

            (docs_dir / "sample.pdf").write_bytes(b"fake")
            rag_core.marker_file(chroma_dir).write_text("stale", encoding="utf-8")
            (chroma_dir / "index.bin").write_text("ready", encoding="utf-8")

            config = rag_core.load_config(
                docs_dir=str(docs_dir),
                chroma_dir=str(chroma_dir),
            )
            result = rag_core.validate_runtime_readiness(config)

        self.assertEqual(result.status, "stale_index")
        self.assertIn(rag_core.INGEST_COMMAND, result.message)


class CacheNamespaceTests(unittest.TestCase):
    def test_cache_namespace_changes_with_runtime_inputs(self) -> None:
        config = rag_core.load_config(docs_dir="documents", chroma_dir="chroma_data")

        base_namespace = rag_core.build_cache_namespace(config, "fingerprint-a")
        other_fingerprint = rag_core.build_cache_namespace(config, "fingerprint-b")
        other_prompt = rag_core.build_cache_namespace(replace(config, prompt_text="another prompt"), "fingerprint-a")
        other_model = rag_core.build_cache_namespace(replace(config, llm_model="other-model"), "fingerprint-a")
        other_retrieval = rag_core.build_cache_namespace(replace(config, top_k=config.top_k + 1), "fingerprint-a")

        self.assertNotEqual(base_namespace, other_fingerprint)
        self.assertNotEqual(base_namespace, other_prompt)
        self.assertNotEqual(base_namespace, other_model)
        self.assertNotEqual(base_namespace, other_retrieval)
        self.assertNotEqual(
            rag_core.build_cache_key("Question", base_namespace),
            rag_core.build_cache_key("Question", other_prompt),
        )


if __name__ == "__main__":
    unittest.main()
