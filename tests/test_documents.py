from __future__ import annotations

import json
import unittest

from tests.test_support import workspace_tempdir

from ragnos.documents import format_docs, list_document_paths, load_all_documents


class DocumentLoadingTests(unittest.TestCase):
    def test_load_all_documents_reads_json_transcript(self) -> None:
        with workspace_tempdir() as root:
            transcript_path = root / "sedation.json"
            transcript_path.write_text(
                json.dumps(
                    {
                        "title": "Qu'est-ce que la reanimation ? - Sedation",
                        "content": "La sedation peut correspondre a un coma artificiel temporaire.",
                        "author": "SRLF",
                        "topic": "general_reanimation",
                        "source_type": "video_transcript",
                        "url": "https://example.test/video",
                    }
                ),
                encoding="utf-8",
            )

            docs, paths = load_all_documents(root)

        self.assertEqual(paths, [transcript_path])
        self.assertEqual(len(docs), 1)
        self.assertIn("coma artificiel", docs[0].page_content)
        self.assertEqual(docs[0].metadata["page"], "transcript")
        self.assertEqual(docs[0].metadata["source_type"], "video_transcript")

    def test_list_document_paths_includes_pdfs_and_json_only(self) -> None:
        with workspace_tempdir() as root:
            (root / "a.pdf").write_bytes(b"pdf")
            (root / "b.json").write_text("{}", encoding="utf-8")
            (root / "c.txt").write_text("ignored", encoding="utf-8")

            paths = list_document_paths(root)

        self.assertEqual([path.name for path in paths], ["a.pdf", "b.json"])

    def test_format_docs_labels_json_transcript_as_section(self) -> None:
        with workspace_tempdir() as root:
            transcript_path = root / "famille.json"
            transcript_path.write_text(
                json.dumps({"content": "Les proches peuvent poser leurs questions.", "source_type": "video_transcript"}),
                encoding="utf-8",
            )
            docs, _ = load_all_documents(root)

        formatted = format_docs(docs)

        self.assertIn("section=transcript", formatted)
        self.assertIn("Les proches", formatted)
