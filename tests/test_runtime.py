from __future__ import annotations

import unittest

from langchain_core.documents import Document

from tests import test_support  # noqa: F401

from ragnos.runtime import build_citations, render_answer


class RuntimeCitationTests(unittest.TestCase):
    def test_build_citations_deduplicates_source_page_pairs(self) -> None:
        docs = [
            Document(page_content="A", metadata={"source": "documents/a.pdf", "page": 1, "chunk_index": 0}),
            Document(page_content="B", metadata={"source": "documents/a.pdf", "page": 1, "chunk_index": 1}),
            Document(page_content="C", metadata={"source": "documents/b.pdf", "page": 2, "chunk_index": 0}),
        ]

        citations = build_citations(docs)

        self.assertEqual(len(citations), 2)
        self.assertEqual(citations[0].source, "a.pdf")
        self.assertEqual(citations[1].page, "2")

    def test_render_answer_appends_sources_block(self) -> None:
        docs = [Document(page_content="A", metadata={"source": "documents/a.pdf", "page": 1, "chunk_index": 0})]
        citations = build_citations(docs)

        rendered = render_answer("Reponse", citations)

        self.assertIn("Sources:", rendered)
        self.assertIn("a.pdf", rendered)

    def test_render_answer_labels_video_transcripts(self) -> None:
        docs = [
            Document(
                page_content="A",
                metadata={
                    "source": "tools/extracts/famille.json",
                    "page": "transcript",
                    "chunk_index": 0,
                    "source_type": "video_transcript",
                },
            )
        ]
        citations = build_citations(docs)

        rendered = render_answer("Reponse", citations)

        self.assertIn("famille.json (transcript video)", rendered)
