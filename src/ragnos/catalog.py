from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


CATALOG_VERSION = 1
CATALOG_FILENAME = "manifest.json"


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    relative_path: str
    file_hash: str
    file_size: int
    modified_ns: int
    page_count: int
    chunk_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CorpusCatalog:
    version: int
    documents: dict[str, DocumentRecord]


def catalog_file(chroma_dir: Path) -> Path:
    return chroma_dir / CATALOG_FILENAME


def file_content_hash(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def build_document_record(docs_dir: Path, pdf_path: Path) -> DocumentRecord:
    stat = pdf_path.stat()
    relative_path = pdf_path.relative_to(docs_dir).as_posix()
    return DocumentRecord(
        relative_path=relative_path,
        file_hash=file_content_hash(pdf_path),
        file_size=stat.st_size,
        modified_ns=stat.st_mtime_ns,
        page_count=0,
        chunk_ids=[],
    )


def read_catalog(chroma_dir: Path) -> CorpusCatalog | None:
    path = catalog_file(chroma_dir)
    if not path.exists():
        return None

    payload = json.loads(path.read_text(encoding="utf-8"))
    documents = {
        relative_path: DocumentRecord(
            relative_path=relative_path,
            file_hash=details["file_hash"],
            file_size=details["file_size"],
            modified_ns=details["modified_ns"],
            page_count=details["page_count"],
            chunk_ids=list(details.get("chunk_ids", [])),
        )
        for relative_path, details in payload.get("documents", {}).items()
    }
    return CorpusCatalog(version=payload.get("version", CATALOG_VERSION), documents=documents)


def write_catalog(chroma_dir: Path, catalog: CorpusCatalog) -> None:
    payload = {
        "version": catalog.version,
        "documents": {
            relative_path: asdict(record)
            for relative_path, record in catalog.documents.items()
        },
    }
    catalog_file(chroma_dir).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
