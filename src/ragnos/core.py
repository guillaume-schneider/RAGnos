from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

DEFAULT_DOCS_DIR = "./documents"
DEFAULT_CHROMA_DIR = "./chroma_data"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_CACHE_TTL = 3600
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 100
DEFAULT_TOP_K = 4
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
DEFAULT_LLM_MODEL = "mistral"
INGEST_COMMAND = "uv run python ingest.py"

SYSTEM_PROMPT_TEXT = (
    "Tu es un assistant juridique strict et precis. "
    "Reponds uniquement avec les informations presentes dans le contexte fourni. "
    "Si l'information n'est pas trouvee, reponds exactement : "
    "'Je ne trouve pas cette information dans les documents fournis.'\n\n"
    "Contexte :\n{context}"
)


@dataclass(frozen=True, slots=True)
class AppConfig:
    docs_dir: Path
    chroma_dir: Path
    redis_url: str
    ollama_base_url: str
    cache_ttl: int = DEFAULT_CACHE_TTL
    chunk_size: int = DEFAULT_CHUNK_SIZE
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    top_k: int = DEFAULT_TOP_K
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    llm_model: str = DEFAULT_LLM_MODEL
    prompt_text: str = SYSTEM_PROMPT_TEXT


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


class IngestError(RuntimeError):
    pass


def load_config(
    *,
    docs_dir: str | None = None,
    chroma_dir: str | None = None,
    redis_url: str | None = None,
    ollama_base_url: str | None = None,
) -> AppConfig:
    return AppConfig(
        docs_dir=Path(docs_dir or os.getenv("DOCS_DIR", DEFAULT_DOCS_DIR)),
        chroma_dir=Path(chroma_dir or os.getenv("CHROMA_DIR", DEFAULT_CHROMA_DIR)),
        redis_url=redis_url or os.getenv("REDIS_URL", DEFAULT_REDIS_URL),
        ollama_base_url=ollama_base_url or os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL),
    )


def log_event(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False))


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
        if item.name != ".fingerprint":
            return True
    return False


def index_matches_fingerprint(config: AppConfig, docs_fingerprint: str) -> bool:
    return has_index_artifacts(config.chroma_dir) and read_index_fingerprint(config.chroma_dir) == docs_fingerprint


def validate_runtime_readiness(config: AppConfig) -> RuntimeValidation:
    if not config.docs_dir.exists():
        return RuntimeValidation(
            status="missing_docs_dir",
            message=f"âŒ Dossier introuvable : {config.docs_dir}",
        )

    pdf_paths = list_pdf_paths(config.docs_dir)
    if not pdf_paths:
        return RuntimeValidation(
            status="no_pdfs",
            message=(
                f"âŒ Aucun PDF trouve dans {config.docs_dir}\n"
                f"Ajoutez des PDF puis executez `{INGEST_COMMAND}`."
            ),
        )

    docs_fingerprint = get_docs_fingerprint(pdf_paths)

    if not config.chroma_dir.exists():
        return RuntimeValidation(
            status="missing_index",
            message=f"âŒ Index introuvable.\nExecutez `{INGEST_COMMAND}`.",
            docs_fingerprint=docs_fingerprint,
            pdf_count=len(pdf_paths),
        )

    if not has_index_artifacts(config.chroma_dir):
        return RuntimeValidation(
            status="empty_index",
            message=f"âŒ Index vide ou incomplet.\nExecutez `{INGEST_COMMAND}`.",
            docs_fingerprint=docs_fingerprint,
            pdf_count=len(pdf_paths),
        )

    existing_fingerprint = read_index_fingerprint(config.chroma_dir)
    if not existing_fingerprint:
        return RuntimeValidation(
            status="missing_fingerprint",
            message=f"âŒ Empreinte d'index introuvable.\nExecutez `{INGEST_COMMAND}`.",
            docs_fingerprint=docs_fingerprint,
            pdf_count=len(pdf_paths),
        )

    if existing_fingerprint != docs_fingerprint:
        return RuntimeValidation(
            status="stale_index",
            message=f"âŒ L'index est obsolete.\nExecutez `{INGEST_COMMAND}`.",
            docs_fingerprint=docs_fingerprint,
            pdf_count=len(pdf_paths),
        )

    return RuntimeValidation(
        status="ready",
        message="ok",
        docs_fingerprint=docs_fingerprint,
        pdf_count=len(pdf_paths),
    )


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


def create_embeddings(config: AppConfig) -> OllamaEmbeddings:
    return OllamaEmbeddings(
        model=config.embedding_model,
        base_url=config.ollama_base_url,
    )


def build_chroma_store(
    documents: Sequence[Document],
    embeddings: OllamaEmbeddings,
    persist_directory: Path,
) -> Chroma:
    return Chroma.from_documents(
        documents=list(documents),
        embedding=embeddings,
        persist_directory=str(persist_directory),
    )


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


def build_prompt(config: AppConfig) -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            ("system", config.prompt_text),
            ("human", "{input}"),
        ]
    )


def build_cache_namespace(config: AppConfig, docs_fingerprint: str) -> str:
    payload = json.dumps(
        {
            "docs_fingerprint": docs_fingerprint,
            "llm_model": config.llm_model,
            "prompt_text": config.prompt_text,
            "top_k": config.top_k,
            "chunk_size": config.chunk_size,
            "chunk_overlap": config.chunk_overlap,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_cache_key(question: str, cache_namespace: str) -> str:
    payload = f"{cache_namespace}:{question.strip().lower()}"
    return "rag:answer:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def format_docs(docs: Sequence[Document]) -> str:
    chunks: list[str] = []
    for index, doc in enumerate(docs, start=1):
        source = Path(doc.metadata.get("source", "inconnu")).name
        page = doc.metadata.get("page", "?")
        chunks.append(f"[Chunk {index} | fichier={source} | page={page}]\n{doc.page_content}")
    return "\n\n".join(chunks)


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


def ingest_corpus(config: AppConfig) -> IngestResult:
    if not config.docs_dir.exists():
        raise IngestError(f"Dossier introuvable : {config.docs_dir}")

    pdf_paths = list_pdf_paths(config.docs_dir)
    if not pdf_paths:
        raise IngestError(f"Aucun PDF trouve dans {config.docs_dir}")

    docs_fingerprint = get_docs_fingerprint(pdf_paths)
    if index_matches_fingerprint(config, docs_fingerprint):
        return IngestResult(
            status="up_to_date",
            docs_fingerprint=docs_fingerprint,
            pdf_count=len(pdf_paths),
            page_count=0,
            chunk_count=0,
        )

    raw_docs, _ = load_all_pdfs(config.docs_dir, pdf_paths)
    splits = split_documents(raw_docs, config)
    embeddings = create_embeddings(config)

    temp_dir = create_temp_build_directory(config.chroma_dir)

    try:
        build_chroma_store(splits, embeddings, temp_dir)
        replace_index_directory(temp_dir, config.chroma_dir)
        marker_file(config.chroma_dir).write_text(docs_fingerprint, encoding="utf-8")
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    return IngestResult(
        status="rebuilt",
        docs_fingerprint=docs_fingerprint,
        pdf_count=len(pdf_paths),
        page_count=len(raw_docs),
        chunk_count=len(splits),
    )

