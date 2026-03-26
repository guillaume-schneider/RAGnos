from __future__ import annotations

import gc
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from langchain_chroma import Chroma
from langchain_ollama import ChatOllama, OllamaEmbeddings

from .catalog import CATALOG_VERSION, CorpusCatalog, DocumentRecord, build_document_record, read_catalog, write_catalog
from .config import AppConfig, INGEST_COMMAND
from .documents import annotate_splits, get_docs_fingerprint, list_pdf_paths, load_all_pdfs, split_documents


@dataclass(frozen=True, slots=True)
class RuntimeValidation:
    status: str
    message: str
    docs_fingerprint: str | None = None
    pdf_count: int = 0

    @property
    def is_ready(self) -> bool:
        return self.status == "ready"


@dataclass(frozen=True, slots=True)
class IngestResult:
    status: str
    docs_fingerprint: str
    pdf_count: int
    page_count: int
    chunk_count: int
    indexed_pdf_count: int = 0
    deleted_pdf_count: int = 0


class IngestError(RuntimeError):
    pass


def marker_file(chroma_dir: Path) -> Path:
    return chroma_dir / ".fingerprint"


def read_index_fingerprint(chroma_dir: Path) -> str | None:
    path = marker_file(chroma_dir)
    if not path.exists():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


def has_index_artifacts(chroma_dir: Path) -> bool:
    if not chroma_dir.exists() or not chroma_dir.is_dir():
        return False
    for item in chroma_dir.iterdir():
        if item.name not in {".fingerprint", "manifest.json"}:
            return True
    return False


def index_matches_fingerprint(config: AppConfig, docs_fingerprint: str) -> bool:
    return has_index_artifacts(config.chroma_dir) and read_index_fingerprint(config.chroma_dir) == docs_fingerprint


def validate_runtime_readiness(config: AppConfig) -> RuntimeValidation:
    if not config.docs_dir.exists():
        return RuntimeValidation(
            status="missing_docs_dir",
            message=f"Dossier introuvable : {config.docs_dir}",
        )

    pdf_paths = list_pdf_paths(config.docs_dir)
    if not pdf_paths:
        return RuntimeValidation(
            status="no_pdfs",
            message=(
                f"Aucun PDF trouve dans {config.docs_dir}\n"
                f"Ajoutez des PDF puis executez `{INGEST_COMMAND}`."
            ),
        )

    docs_fingerprint = get_docs_fingerprint(pdf_paths)

    if not config.chroma_dir.exists():
        return RuntimeValidation(
            status="missing_index",
            message=f"Index introuvable.\nExecutez `{INGEST_COMMAND}`.",
            docs_fingerprint=docs_fingerprint,
            pdf_count=len(pdf_paths),
        )

    if not has_index_artifacts(config.chroma_dir):
        return RuntimeValidation(
            status="empty_index",
            message=f"Index vide ou incomplet.\nExecutez `{INGEST_COMMAND}`.",
            docs_fingerprint=docs_fingerprint,
            pdf_count=len(pdf_paths),
        )

    existing_fingerprint = read_index_fingerprint(config.chroma_dir)
    if not existing_fingerprint:
        return RuntimeValidation(
            status="missing_fingerprint",
            message=f"Empreinte d'index introuvable.\nExecutez `{INGEST_COMMAND}`.",
            docs_fingerprint=docs_fingerprint,
            pdf_count=len(pdf_paths),
        )

    if existing_fingerprint != docs_fingerprint:
        return RuntimeValidation(
            status="stale_index",
            message=f"L'index est obsolete.\nExecutez `{INGEST_COMMAND}`.",
            docs_fingerprint=docs_fingerprint,
            pdf_count=len(pdf_paths),
        )

    return RuntimeValidation(
        status="ready",
        message="ok",
        docs_fingerprint=docs_fingerprint,
        pdf_count=len(pdf_paths),
    )


def create_embeddings(config: AppConfig) -> OllamaEmbeddings:
    return OllamaEmbeddings(
        model=config.embedding_model,
        base_url=config.ollama_base_url,
    )


def build_chroma_store(
    documents: Sequence[object],
    embeddings: OllamaEmbeddings,
    persist_directory: Path,
    ids: Sequence[str] | None = None,
) -> Chroma:
    vectorstore = Chroma(
        persist_directory=str(persist_directory),
        embedding_function=embeddings,
    )
    if documents:
        vectorstore.add_documents(documents=list(documents), ids=list(ids) if ids is not None else None)
    return vectorstore


def open_vectorstore(config: AppConfig, embeddings: OllamaEmbeddings) -> Chroma:
    return Chroma(
        persist_directory=str(config.chroma_dir),
        embedding_function=embeddings,
    )


def create_llm(config: AppConfig) -> ChatOllama:
    return ChatOllama(
        model=config.llm_model,
        temperature=0,
        base_url=config.ollama_base_url,
    )


def close_vectorstore(vectorstore: object | None) -> None:
    if vectorstore is None:
        return

    client = getattr(vectorstore, "_client", None)
    if client is not None:
        close = getattr(client, "close", None)
        if callable(close):
            close()

        clear_system_cache = getattr(client, "clear_system_cache", None)
        if callable(clear_system_cache):
            clear_system_cache()

    gc.collect()


def replace_index_directory(source_dir: Path, target_dir: Path) -> None:
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.move(str(source_dir), str(target_dir))


def create_temp_build_directory(chroma_dir: Path) -> Path:
    chroma_dir.parent.mkdir(parents=True, exist_ok=True)

    while True:
        candidate = chroma_dir.parent / f"{chroma_dir.name}-build-{uuid.uuid4().hex}"
        try:
            candidate.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        return candidate


def _current_document_records(config: AppConfig, pdf_paths: Sequence[Path]) -> dict[str, DocumentRecord]:
    return {
        pdf_path.relative_to(config.docs_dir).as_posix(): build_document_record(config.docs_dir, pdf_path)
        for pdf_path in pdf_paths
    }


def _needs_full_rebuild(config: AppConfig, catalog: CorpusCatalog | None) -> bool:
    if catalog is None or catalog.version != CATALOG_VERSION:
        return True
    return not has_index_artifacts(config.chroma_dir)


def _rebuild_full_index(
    config: AppConfig,
    pdf_paths: Sequence[Path],
    docs_fingerprint: str,
    current_records: dict[str, DocumentRecord],
) -> IngestResult:
    raw_docs, _ = load_all_pdfs(config.docs_dir, pdf_paths)
    splits = split_documents(raw_docs, config)

    all_chunk_ids: list[str] = []
    for pdf_path in pdf_paths:
        relative_path = pdf_path.relative_to(config.docs_dir).as_posix()
        record = current_records[relative_path]
        source_splits = [split for split in splits if Path(split.metadata.get("source", "")).resolve() == pdf_path.resolve()]
        chunk_ids = annotate_splits(source_splits, relative_path, record.file_hash)
        current_records[relative_path] = DocumentRecord(
            relative_path=record.relative_path,
            file_hash=record.file_hash,
            file_size=record.file_size,
            modified_ns=record.modified_ns,
            page_count=len([doc for doc in raw_docs if Path(doc.metadata.get("source", "")).resolve() == pdf_path.resolve()]),
            chunk_ids=chunk_ids,
        )
        all_chunk_ids.extend(chunk_ids)

    embeddings = create_embeddings(config)
    temp_dir = create_temp_build_directory(config.chroma_dir)
    temp_vectorstore: Chroma | None = None

    try:
        temp_vectorstore = build_chroma_store(splits, embeddings, temp_dir, ids=all_chunk_ids)
        close_vectorstore(temp_vectorstore)
        temp_vectorstore = None
        replace_index_directory(temp_dir, config.chroma_dir)
        write_catalog(config.chroma_dir, CorpusCatalog(version=CATALOG_VERSION, documents=current_records))
        marker_file(config.chroma_dir).write_text(docs_fingerprint, encoding="utf-8")
    except Exception:
        close_vectorstore(temp_vectorstore)
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    return IngestResult(
        status="rebuilt",
        docs_fingerprint=docs_fingerprint,
        pdf_count=len(pdf_paths),
        page_count=len(raw_docs),
        chunk_count=len(splits),
        indexed_pdf_count=len(pdf_paths),
        deleted_pdf_count=0,
    )


def ingest_corpus(config: AppConfig) -> IngestResult:
    if not config.docs_dir.exists():
        raise IngestError(f"Dossier introuvable : {config.docs_dir}")

    pdf_paths = list_pdf_paths(config.docs_dir)
    if not pdf_paths:
        raise IngestError(f"Aucun PDF trouve dans {config.docs_dir}")

    docs_fingerprint = get_docs_fingerprint(pdf_paths)
    current_records = _current_document_records(config, pdf_paths)
    catalog = read_catalog(config.chroma_dir)

    if _needs_full_rebuild(config, catalog):
        return _rebuild_full_index(config, pdf_paths, docs_fingerprint, current_records)

    existing_records = catalog.documents
    deleted_paths = sorted(set(existing_records) - set(current_records))
    changed_paths = sorted(
        relative_path
        for relative_path, record in current_records.items()
        if relative_path not in existing_records or existing_records[relative_path].file_hash != record.file_hash
    )

    if not changed_paths and not deleted_paths and read_index_fingerprint(config.chroma_dir) == docs_fingerprint:
        return IngestResult(
            status="up_to_date",
            docs_fingerprint=docs_fingerprint,
            pdf_count=len(pdf_paths),
            page_count=0,
            chunk_count=0,
            indexed_pdf_count=0,
            deleted_pdf_count=0,
        )

    embeddings = create_embeddings(config)
    vectorstore = open_vectorstore(config, embeddings)
    updated_records = dict(existing_records)
    indexed_page_count = 0
    indexed_chunk_count = 0

    try:
        if deleted_paths:
            chunk_ids_to_delete = [
                chunk_id
                for relative_path in deleted_paths
                for chunk_id in existing_records[relative_path].chunk_ids
            ]
            if chunk_ids_to_delete:
                vectorstore.delete(ids=chunk_ids_to_delete)
            for relative_path in deleted_paths:
                updated_records.pop(relative_path, None)

        for relative_path in changed_paths:
            current_record = current_records[relative_path]
            existing_record = existing_records.get(relative_path)
            if existing_record and existing_record.chunk_ids:
                vectorstore.delete(ids=existing_record.chunk_ids)

            pdf_path = config.docs_dir / relative_path
            raw_docs, _ = load_all_pdfs(config.docs_dir, [pdf_path])
            splits = split_documents(raw_docs, config)
            chunk_ids = annotate_splits(splits, relative_path, current_record.file_hash)
            if splits:
                vectorstore.add_documents(list(splits), ids=chunk_ids)

            updated_records[relative_path] = DocumentRecord(
                relative_path=current_record.relative_path,
                file_hash=current_record.file_hash,
                file_size=current_record.file_size,
                modified_ns=current_record.modified_ns,
                page_count=len(raw_docs),
                chunk_ids=chunk_ids,
            )
            indexed_page_count += len(raw_docs)
            indexed_chunk_count += len(splits)
    finally:
        close_vectorstore(vectorstore)

    write_catalog(config.chroma_dir, CorpusCatalog(version=CATALOG_VERSION, documents=updated_records))
    marker_file(config.chroma_dir).write_text(docs_fingerprint, encoding="utf-8")

    return IngestResult(
        status="rebuilt",
        docs_fingerprint=docs_fingerprint,
        pdf_count=len(pdf_paths),
        page_count=indexed_page_count,
        chunk_count=indexed_chunk_count,
        indexed_pdf_count=len(changed_paths),
        deleted_pdf_count=len(deleted_paths),
    )
