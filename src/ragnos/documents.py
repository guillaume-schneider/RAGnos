from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Sequence

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import AppConfig

SUPPORTED_DOCUMENT_SUFFIXES = {".pdf", ".json"}


def list_pdf_paths(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(folder.glob("*.pdf"))


def list_document_paths(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(
        (path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_DOCUMENT_SUFFIXES),
        key=lambda path: path.name.lower(),
    )


def get_docs_fingerprint(document_paths: Sequence[Path]) -> str:
    stat_parts: list[str] = []
    for document_path in document_paths:
        try:
            stat = document_path.stat()
        except FileNotFoundError:
            continue
        stat_parts.append(f"{document_path.name}:{stat.st_mtime_ns}:{stat.st_size}")
    raw = "|".join(stat_parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _mojibake_score(text: str) -> int:
    return text.count("Ã") + text.count("â") + text.count("\ufffd")


def _normalize_mojibake(text: str) -> str:
    if _mojibake_score(text) == 0:
        return text
    try:
        repaired = text.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return text
    if _mojibake_score(repaired) < _mojibake_score(text):
        return repaired
    return text


def _load_pdf(pdf_path: Path) -> list[Document]:
    loader = PyPDFLoader(str(pdf_path))
    pdf_docs = loader.load()
    for doc in pdf_docs:
        doc.metadata["source"] = str(pdf_path)
        doc.metadata.setdefault("source_type", "pdf")
    return pdf_docs


def _clean_json_string(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return _normalize_mojibake(value.strip())


def _load_json_document(json_path: Path) -> list[Document]:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return []

    title = _clean_json_string(payload.get("title"))
    content = _clean_json_string(payload.get("content"))
    if not content:
        return []

    author = _clean_json_string(payload.get("author"))
    url = _clean_json_string(payload.get("url"))
    topic = _clean_json_string(payload.get("topic"))
    source_type = _clean_json_string(payload.get("source_type")) or "json"

    header_parts = []
    if title:
        header_parts.append(f"Titre: {title}")
    if author:
        header_parts.append(f"Auteur: {author}")
    if topic:
        header_parts.append(f"Sujet: {topic}")
    if source_type:
        header_parts.append(f"Type de source: {source_type}")
    if url:
        header_parts.append(f"URL: {url}")

    page_content = "\n".join(header_parts + ["", content]).strip()
    return [
        Document(
            page_content=page_content,
            metadata={
                "source": str(json_path),
                "source_type": source_type,
                "page": "transcript" if source_type == "video_transcript" else "json",
                "title": title,
                "author": author,
                "url": url,
                "topic": topic,
            },
        )
    ]


def load_all_documents(folder: Path, document_paths: Sequence[Path] | None = None) -> tuple[list[Document], list[Path]]:
    resolved_document_paths = list(document_paths if document_paths is not None else list_document_paths(folder))
    docs: list[Document] = []

    for document_path in resolved_document_paths:
        suffix = document_path.suffix.lower()
        if suffix == ".pdf":
            docs.extend(_load_pdf(document_path))
        elif suffix == ".json":
            docs.extend(_load_json_document(document_path))

    return docs, resolved_document_paths


def load_all_pdfs(folder: Path, pdf_paths: Sequence[Path] | None = None) -> tuple[list[Document], list[Path]]:
    resolved_pdf_paths = list(pdf_paths if pdf_paths is not None else list_pdf_paths(folder))
    return load_all_documents(folder, resolved_pdf_paths)


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
        if str(page) in {"transcript", "json"}:
            location = f"section={page}"
        else:
            location = f"page={page}"
        chunks.append(f"[Chunk {index} | fichier={source} | {location}]\n{doc.page_content}")
    return "\n\n".join(chunks)
