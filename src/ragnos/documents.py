from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Sequence

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import AppConfig


def list_pdf_paths(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(folder.glob("*.pdf"))


def get_docs_fingerprint(pdf_paths: Sequence[Path]) -> str:
    stat_parts: list[str] = []
    for pdf_path in pdf_paths:
        try:
            stat = pdf_path.stat()
        except FileNotFoundError:
            continue
        stat_parts.append(f"{pdf_path.name}:{stat.st_mtime_ns}:{stat.st_size}")
    raw = "|".join(stat_parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_all_pdfs(folder: Path, pdf_paths: Sequence[Path] | None = None) -> tuple[list[Document], list[Path]]:
    resolved_pdf_paths = list(pdf_paths if pdf_paths is not None else list_pdf_paths(folder))
    docs: list[Document] = []

    for pdf_path in resolved_pdf_paths:
        loader = PyPDFLoader(str(pdf_path))
        pdf_docs = loader.load()
        for doc in pdf_docs:
            doc.metadata["source"] = str(pdf_path)
        docs.extend(pdf_docs)

    return docs, resolved_pdf_paths


def split_documents(raw_docs: Sequence[Document], config: AppConfig) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
    )
    return splitter.split_documents(list(raw_docs))


def build_chunk_id(relative_path: str, file_hash: str, page: object, chunk_index: int) -> str:
    return f"{relative_path}:{file_hash}:{page}:{chunk_index}"


def annotate_splits(splits: Sequence[Document], relative_path: str, file_hash: str) -> list[str]:
    chunk_ids: list[str] = []
    for chunk_index, split in enumerate(splits):
        split.metadata["relative_source"] = relative_path
        split.metadata["file_hash"] = file_hash
        split.metadata["chunk_index"] = chunk_index
        page = split.metadata.get("page", "?")
        chunk_ids.append(build_chunk_id(relative_path, file_hash, page, chunk_index))
    return chunk_ids


def format_docs(docs: Sequence[Document]) -> str:
    chunks: list[str] = []
    for index, doc in enumerate(docs, start=1):
        source = Path(doc.metadata.get("source", "inconnu")).name
        page = doc.metadata.get("page", "?")
        chunks.append(f"[Chunk {index} | fichier={source} | page={page}]\n{doc.page_content}")
    return "\n\n".join(chunks)
