from __future__ import annotations

import unittest
from unittest.mock import patch

from langchain_core.documents import Document

from tests.test_support import workspace_tempdir, write_prompt

from ragnos.catalog import CorpusCatalog, DocumentRecord, build_document_record, read_catalog, write_catalog
from ragnos.config import load_config
from ragnos.documents import get_docs_fingerprint
from ragnos.indexing import (
    INGEST_COMMAND,
    ingest_corpus,
    marker_file,
    read_index_fingerprint,
    validate_runtime_readiness,
)


class FingerprintTests(unittest.TestCase):
    def test_fingerprint_changes_when_file_stats_change(self) -> None:
        with workspace_tempdir() as docs_dir:
            pdf_path = docs_dir / "sample.pdf"
            pdf_path.write_bytes(b"first")

            first = get_docs_fingerprint([pdf_path])
            same = get_docs_fingerprint([pdf_path])
            pdf_path.write_bytes(b"second-version")
            changed = get_docs_fingerprint([pdf_path])

        self.assertEqual(first, same)
        self.assertNotEqual(first, changed)


class IngestTests(unittest.TestCase):
    def test_ingest_noop_skips_rebuild_when_fingerprint_matches(self) -> None:
        with workspace_tempdir() as root:
            docs_dir = root / "documents"
            chroma_dir = root / "chroma"
            docs_dir.mkdir()
            chroma_dir.mkdir()
            prompt_path = write_prompt(root)

            pdf_path = docs_dir / "sample.pdf"
            pdf_path.write_bytes(b"fake")
            docs_fingerprint = get_docs_fingerprint([pdf_path])
            seeded_record = build_document_record(docs_dir, pdf_path)

            record = DocumentRecord(
                relative_path="sample.pdf",
                file_hash=seeded_record.file_hash,
                file_size=seeded_record.file_size,
                modified_ns=seeded_record.modified_ns,
                page_count=1,
                chunk_ids=[f"sample.pdf:{seeded_record.file_hash}:0:0"],
            )
            write_catalog(chroma_dir, CorpusCatalog(version=1, documents={"sample.pdf": record}))
            marker_file(chroma_dir).write_text(docs_fingerprint, encoding="utf-8")
            (chroma_dir / "existing.bin").write_text("ready", encoding="utf-8")

            config = load_config(
                docs_dir=str(docs_dir),
                chroma_dir=str(chroma_dir),
                prompt_path=str(prompt_path),
            )

            with patch("ragnos.indexing.load_all_documents") as load_mock, patch("ragnos.indexing.build_chroma_store") as build_mock:
                result = ingest_corpus(config)

        self.assertEqual(result.status, "up_to_date")
        load_mock.assert_not_called()
        build_mock.assert_not_called()

    def test_ingest_rebuilds_index_and_updates_catalog_when_manifest_missing(self) -> None:
        with workspace_tempdir() as root:
            docs_dir = root / "documents"
            chroma_dir = root / "chroma"
            docs_dir.mkdir()
            chroma_dir.mkdir()
            prompt_path = write_prompt(root)

            pdf_path = docs_dir / "sample.pdf"
            pdf_path.write_bytes(b"fake")
            expected_fingerprint = get_docs_fingerprint([pdf_path])

            marker_file(chroma_dir).write_text("stale", encoding="utf-8")
            (chroma_dir / "stale.bin").write_text("old", encoding="utf-8")

            config = load_config(
                docs_dir=str(docs_dir),
                chroma_dir=str(chroma_dir),
                prompt_path=str(prompt_path),
            )
            fake_docs = [Document(page_content="Article 1", metadata={"page": 0, "source": str(pdf_path)})]

            def fake_build(documents, embeddings, persist_directory, ids=None):
                persist_directory.mkdir(parents=True, exist_ok=True)
                (persist_directory / "index.bin").write_text("new", encoding="utf-8")
                return object()

            with patch("ragnos.indexing.load_all_documents", return_value=(fake_docs, [pdf_path])) as load_mock, patch(
                "ragnos.indexing.create_embeddings", return_value=object()
            ) as embeddings_mock, patch("ragnos.indexing.build_chroma_store", side_effect=fake_build) as build_mock:
                result = ingest_corpus(config)

            catalog = read_catalog(chroma_dir)
            self.assertEqual(result.status, "rebuilt")
            self.assertEqual(result.document_count, 1)
            self.assertEqual(result.indexed_document_count, 1)
            self.assertTrue(load_mock.called)
            self.assertTrue(embeddings_mock.called)
            self.assertTrue(build_mock.called)
            self.assertEqual(read_index_fingerprint(chroma_dir), expected_fingerprint)
            self.assertIsNotNone(catalog)
            self.assertIn("sample.pdf", catalog.documents)

    def test_incremental_ingest_deletes_removed_document_chunks(self) -> None:
        class FakeVectorStore:
            def __init__(self) -> None:
                self.deleted_ids: list[list[str]] = []

            def delete(self, ids):
                self.deleted_ids.append(list(ids))

        with workspace_tempdir() as root:
            docs_dir = root / "documents"
            chroma_dir = root / "chroma"
            docs_dir.mkdir()
            chroma_dir.mkdir()
            prompt_path = write_prompt(root)

            surviving_pdf = docs_dir / "a.pdf"
            surviving_pdf.write_bytes(b"a")
            surviving_seed = build_document_record(docs_dir, surviving_pdf)
            removed_record = DocumentRecord(
                relative_path="b.pdf",
                file_hash="hash-b",
                file_size=1,
                modified_ns=1,
                page_count=1,
                chunk_ids=["b.pdf:hash-b:0:0"],
            )
            surviving_record = DocumentRecord(
                relative_path="a.pdf",
                file_hash=surviving_seed.file_hash,
                file_size=surviving_seed.file_size,
                modified_ns=surviving_seed.modified_ns,
                page_count=1,
                chunk_ids=[f"a.pdf:{surviving_seed.file_hash}:0:0"],
            )
            write_catalog(
                chroma_dir,
                CorpusCatalog(version=1, documents={"a.pdf": surviving_record, "b.pdf": removed_record}),
            )
            marker_file(chroma_dir).write_text("stale", encoding="utf-8")
            (chroma_dir / "existing.bin").write_text("ready", encoding="utf-8")

            config = load_config(
                docs_dir=str(docs_dir),
                chroma_dir=str(chroma_dir),
                prompt_path=str(prompt_path),
            )
            vectorstore = FakeVectorStore()

            with patch("ragnos.indexing.create_embeddings", return_value=object()), patch(
                "ragnos.indexing.open_vectorstore", return_value=vectorstore
            ), patch("ragnos.indexing.load_all_documents") as load_mock:
                result = ingest_corpus(config)

            self.assertEqual(result.deleted_document_count, 1)
            self.assertEqual(vectorstore.deleted_ids, [["b.pdf:hash-b:0:0"]])
            load_mock.assert_not_called()

    def test_incremental_ingest_reindexes_changed_document(self) -> None:
        class FakeVectorStore:
            def __init__(self) -> None:
                self.deleted_ids: list[list[str]] = []
                self.added_ids: list[list[str]] = []

            def delete(self, ids):
                self.deleted_ids.append(list(ids))

            def add_documents(self, documents, ids=None):
                self.added_ids.append(list(ids or []))

        with workspace_tempdir() as root:
            docs_dir = root / "documents"
            chroma_dir = root / "chroma"
            docs_dir.mkdir()
            chroma_dir.mkdir()
            prompt_path = write_prompt(root)

            pdf_path = docs_dir / "sample.pdf"
            pdf_path.write_bytes(b"new-content")
            write_catalog(
                chroma_dir,
                CorpusCatalog(
                    version=1,
                    documents={
                        "sample.pdf": DocumentRecord(
                            relative_path="sample.pdf",
                            file_hash="old-hash",
                            file_size=4,
                            modified_ns=1,
                            page_count=1,
                            chunk_ids=["sample.pdf:old-hash:0:0"],
                        )
                    },
                ),
            )
            marker_file(chroma_dir).write_text("stale", encoding="utf-8")
            (chroma_dir / "existing.bin").write_text("ready", encoding="utf-8")

            config = load_config(
                docs_dir=str(docs_dir),
                chroma_dir=str(chroma_dir),
                prompt_path=str(prompt_path),
            )
            raw_docs = [Document(page_content="Raw", metadata={"page": 0, "source": str(pdf_path)})]
            split_docs = [Document(page_content="Split", metadata={"page": 0, "source": str(pdf_path)})]
            vectorstore = FakeVectorStore()

            with patch("ragnos.indexing.create_embeddings", return_value=object()), patch(
                "ragnos.indexing.open_vectorstore", return_value=vectorstore
            ), patch("ragnos.indexing.load_all_documents", return_value=(raw_docs, [pdf_path])), patch(
                "ragnos.indexing.split_documents", return_value=split_docs
            ):
                result = ingest_corpus(config)

            self.assertEqual(result.indexed_document_count, 1)
            self.assertEqual(vectorstore.deleted_ids, [["sample.pdf:old-hash:0:0"]])
            self.assertEqual(len(vectorstore.added_ids), 1)
            catalog = read_catalog(chroma_dir)
            self.assertNotEqual(catalog.documents["sample.pdf"].file_hash, "old-hash")
            self.assertEqual(len(catalog.documents["sample.pdf"].chunk_ids), 1)


class RuntimeValidationTests(unittest.TestCase):
    def test_missing_index_is_actionable(self) -> None:
        with workspace_tempdir() as root:
            docs_dir = root / "documents"
            docs_dir.mkdir()
            prompt_path = write_prompt(root)
            (docs_dir / "sample.pdf").write_bytes(b"fake")

            config = load_config(
                docs_dir=str(docs_dir),
                chroma_dir=str(root / "missing-index"),
                prompt_path=str(prompt_path),
            )
            result = validate_runtime_readiness(config)

        self.assertEqual(result.status, "missing_index")
        self.assertIn(INGEST_COMMAND, result.message)

    def test_empty_index_is_actionable(self) -> None:
        with workspace_tempdir() as root:
            docs_dir = root / "documents"
            chroma_dir = root / "chroma"
            docs_dir.mkdir()
            chroma_dir.mkdir()
            prompt_path = write_prompt(root)

            pdf_path = docs_dir / "sample.pdf"
            pdf_path.write_bytes(b"fake")
            docs_fingerprint = get_docs_fingerprint([pdf_path])
            marker_file(chroma_dir).write_text(docs_fingerprint, encoding="utf-8")

            config = load_config(
                docs_dir=str(docs_dir),
                chroma_dir=str(chroma_dir),
                prompt_path=str(prompt_path),
            )
            result = validate_runtime_readiness(config)

        self.assertEqual(result.status, "empty_index")
        self.assertIn(INGEST_COMMAND, result.message)

    def test_stale_index_is_actionable(self) -> None:
        with workspace_tempdir() as root:
            docs_dir = root / "documents"
            chroma_dir = root / "chroma"
            docs_dir.mkdir()
            chroma_dir.mkdir()
            prompt_path = write_prompt(root)

            (docs_dir / "sample.pdf").write_bytes(b"fake")
            marker_file(chroma_dir).write_text("stale", encoding="utf-8")
            (chroma_dir / "index.bin").write_text("ready", encoding="utf-8")

            config = load_config(
                docs_dir=str(docs_dir),
                chroma_dir=str(chroma_dir),
                prompt_path=str(prompt_path),
            )
            result = validate_runtime_readiness(config)

        self.assertEqual(result.status, "stale_index")
        self.assertIn(INGEST_COMMAND, result.message)
