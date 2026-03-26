from __future__ import annotations

import unittest
from pathlib import Path

from tests.test_support import workspace_tempdir, write_prompt

import ragnos.app as app_mod
from ragnos.config import load_config


class FakeUpload:
    def __init__(self, name: str, path: Path, mime: str) -> None:
        self.name = name
        self.path = str(path)
        self.mime = mime


class AppUploadTests(unittest.TestCase):
    def test_extract_pdf_uploads_filters_non_pdf_elements(self) -> None:
        uploads = [
            FakeUpload("a.pdf", Path("a.pdf"), "application/pdf"),
            FakeUpload("b.txt", Path("b.txt"), "text/plain"),
        ]

        extracted = app_mod._extract_pdf_uploads(uploads)

        self.assertEqual(len(extracted), 1)
        self.assertEqual(extracted[0].name, "a.pdf")

    def test_persist_uploaded_pdfs_copies_files_into_docs_dir(self) -> None:
        with workspace_tempdir() as root:
            prompt_path = write_prompt(root)
            docs_dir = root / "documents"
            chroma_dir = root / "chroma"
            source_file = root / "upload.pdf"
            source_file.write_bytes(b"pdf-content")
            upload = FakeUpload("upload.pdf", source_file, "application/pdf")

            config = load_config(
                docs_dir=str(docs_dir),
                chroma_dir=str(chroma_dir),
                prompt_path=str(prompt_path),
            )
            saved = app_mod._persist_uploaded_pdfs(config, [upload])
            self.assertEqual(saved[0].name, "upload.pdf")
            self.assertTrue((docs_dir / "upload.pdf").exists())
