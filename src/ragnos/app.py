from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path
from typing import Iterable

import chainlit as cl

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ragnos.cache import build_cache_namespace
from ragnos.config import AppConfig, ConfigError, INGEST_COMMAND, load_config
from ragnos.documents import list_pdf_paths
from ragnos.health import build_health_report, format_health_report
from ragnos.indexing import ingest_corpus, validate_runtime_readiness
from ragnos.runtime import RuntimeState, build_runtime_state, close_runtime_state, run_query
from ragnos.telemetry import log_event

PDF_ACCEPT = ["application/pdf"]
UPLOAD_MAX_FILES = 10
UPLOAD_MAX_SIZE_MB = 100

try:
    CONFIG = load_config()
    CONFIG_ERROR: str | None = None
except ConfigError as exc:
    CONFIG = None
    CONFIG_ERROR = str(exc)


_runtime_lock = asyncio.Lock()
_runtime_state: RuntimeState | None = None


def _runtime_unavailable_message() -> str:
    if CONFIG_ERROR:
        return f"Configuration invalide : {CONFIG_ERROR}"
    return f"Impossible d'ouvrir l'index local.\nExecutez `{INGEST_COMMAND}`."


def _ready_message(state: RuntimeState, pdf_count: int) -> str:
    return (
        "Systeme pret.\n"
        f"- Redis : {'ON' if state.redis_ok else 'OFF'}\n"
        f"- PDFs : {pdf_count}\n"
        "- Index : ready\n"
        "- Commandes : /upload, /refresh, /status"
    )


async def get_runtime_state(config: AppConfig, docs_fingerprint: str) -> RuntimeState:
    global _runtime_state

    desired_namespace = build_cache_namespace(config, docs_fingerprint)
    if _runtime_state and _runtime_state.cache_namespace == desired_namespace:
        return _runtime_state

    async with _runtime_lock:
        if _runtime_state and _runtime_state.cache_namespace == desired_namespace:
            return _runtime_state

        _runtime_state = await build_runtime_state(config, docs_fingerprint)
        return _runtime_state


async def reset_runtime_state() -> None:
    global _runtime_state

    async with _runtime_lock:
        previous_state = _runtime_state
        _runtime_state = None

    await close_runtime_state(previous_state)


def _extract_pdf_uploads(elements: Iterable[object] | None) -> list[object]:
    uploads: list[object] = []
    for element in elements or []:
        path = getattr(element, "path", None)
        name = getattr(element, "name", "")
        mime = getattr(element, "mime", None) or getattr(element, "type", None)
        if not path:
            continue
        if mime == "application/pdf" or str(name).lower().endswith(".pdf"):
            uploads.append(element)
    return uploads


def _persist_uploaded_pdfs(config: AppConfig, uploads: Iterable[object]) -> list[Path]:
    config.docs_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []
    for upload in uploads:
        source_path = Path(getattr(upload, "path"))
        target_name = Path(getattr(upload, "name", source_path.name)).name
        target_path = config.docs_dir / target_name
        shutil.copyfile(source_path, target_path)
        saved_paths.append(target_path)
    return saved_paths


async def _ask_for_pdf_uploads() -> list[object]:
    response = await cl.AskFileMessage(
        content="Chargez un ou plusieurs PDF pour lancer ou enrichir le corpus local.",
        accept=PDF_ACCEPT,
        max_size_mb=UPLOAD_MAX_SIZE_MB,
        max_files=UPLOAD_MAX_FILES,
        timeout=180,
    ).send()
    return list(response or [])


async def _reindex_and_reload(config: AppConfig, initial_message: str) -> RuntimeState | None:
    progress = await cl.Message(content=initial_message).send()

    try:
        result = await asyncio.to_thread(ingest_corpus, config)
    except Exception as exc:
        log_event({"event": "ingest_failed", "error": str(exc)})
        progress.content = f"Echec de l'indexation : {exc}"
        await progress.update()
        return None

    await reset_runtime_state()
    validation = validate_runtime_readiness(config)
    if not validation.is_ready or not validation.docs_fingerprint:
        progress.content = validation.message
        await progress.update()
        return None

    state = await get_runtime_state(config, validation.docs_fingerprint)
    cl.user_session.set("runtime_state", state)

    progress.content = (
        "Indexation terminee.\n"
        f"- PDFs totaux : {result.pdf_count}\n"
        f"- PDFs indexes : {result.indexed_pdf_count}\n"
        f"- PDFs supprimes : {result.deleted_pdf_count}\n"
        f"- Chunks traites : {result.chunk_count}"
    )
    await progress.update()
    return state


async def _handle_upload_request(config: AppConfig, uploads: list[object] | None = None) -> RuntimeState | None:
    resolved_uploads = uploads if uploads is not None else await _ask_for_pdf_uploads()
    if not resolved_uploads:
        await cl.Message(content="Aucun PDF recu. Utilisez /upload pour recommencer.").send()
        return None

    saved_paths = _persist_uploaded_pdfs(config, resolved_uploads)
    log_event(
        {
            "event": "upload_saved",
            "files": [path.name for path in saved_paths],
            "target_dir": str(config.docs_dir),
        }
    )

    return await _reindex_and_reload(config, f"{len(saved_paths)} PDF(s) recu(s), indexation en cours...")


async def _handle_refresh_request(config: AppConfig) -> RuntimeState | None:
    if not list_pdf_paths(config.docs_dir):
        await cl.Message(content="Aucun PDF disponible. Utilisez /upload pour ajouter des documents.").send()
        return None
    return await _reindex_and_reload(config, "Rafraichissement de l'index en cours...")


async def _handle_status_request(config: AppConfig) -> None:
    report = await build_health_report(config)
    await cl.Message(content=format_health_report(report)).send()


@cl.on_chat_start
async def on_chat_start() -> None:
    msg = await cl.Message(content="Initialisation du systeme RAG...").send()

    if CONFIG is None:
        msg.content = _runtime_unavailable_message()
        await msg.update()
        return

    validation = validate_runtime_readiness(CONFIG)
    if validation.status in {"missing_docs_dir", "no_pdfs"}:
        msg.content = "Aucun corpus pret. Chargez des PDF pour demarrer."
        await msg.update()
        state = await _handle_upload_request(CONFIG)
        if state is None:
            return
        pdf_count = len(list_pdf_paths(CONFIG.docs_dir))
        await cl.Message(content=_ready_message(state, pdf_count)).send()
        return

    if not validation.is_ready or not validation.docs_fingerprint:
        msg.content = validation.message + "\nUtilisez /refresh pour indexer le corpus existant."
        await msg.update()
        return

    try:
        state = await get_runtime_state(CONFIG, validation.docs_fingerprint)
    except Exception as exc:
        log_event({"event": "runtime_init_failed", "error": str(exc)})
        msg.content = f"Impossible d'ouvrir l'index local.\nExecutez `{INGEST_COMMAND}`."
        await msg.update()
        return

    cl.user_session.set("runtime_state", state)

    log_event(
        {
            "event": "startup_complete",
            "redis": state.redis_ok,
            "documents_count": validation.pdf_count,
            "docs_fingerprint": validation.docs_fingerprint,
            "index_mode": "reused",
        }
    )

    msg.content = _ready_message(state, validation.pdf_count)
    await msg.update()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    state: RuntimeState | None = cl.user_session.get("runtime_state")

    if CONFIG is None:
        await cl.Message(content=_runtime_unavailable_message()).send()
        return

    question = message.content.strip()

    if question == "/status":
        await _handle_status_request(CONFIG)
        return

    if question == "/upload":
        await _handle_upload_request(CONFIG)
        return

    if question == "/refresh":
        await _handle_refresh_request(CONFIG)
        return

    uploaded_pdfs = _extract_pdf_uploads(getattr(message, "elements", None))
    if uploaded_pdfs:
        state = await _handle_upload_request(CONFIG, uploads=uploaded_pdfs)
        if not question:
            return

    if state is None:
        validation = validate_runtime_readiness(CONFIG)
        if not validation.is_ready or not validation.docs_fingerprint:
            await cl.Message(content=validation.message + "\nUtilisez /upload ou /refresh.").send()
            return
        try:
            state = await get_runtime_state(CONFIG, validation.docs_fingerprint)
        except Exception as exc:
            log_event({"event": "runtime_init_failed", "error": str(exc)})
            await cl.Message(content=f"Impossible d'ouvrir l'index local.\nExecutez `{INGEST_COMMAND}`.").send()
            return
        cl.user_session.set("runtime_state", state)

    if not question:
        await cl.Message(content="Documents indexes. Posez maintenant votre question.").send()
        return

    ui_msg = await cl.Message(content="").send()
    result = await run_query(state, question, stream_callback=ui_msg.stream_token)

    if result.cache_hit:
        ui_msg.content = result.answer
        await ui_msg.update()
        log_event(
            {
                "event": "cache_hit",
                "question": question,
                "docs_fingerprint": state.docs_fingerprint,
            }
        )
        return

    await ui_msg.update()

    log_event(
        {
            "event": "rag_query",
            "question": question,
            "chunks_used": result.chunks_used,
            "sources": result.sources,
            "citations": [{"source": citation.source, "page": citation.page} for citation in result.citations],
            "retrieval_ms": round(result.retrieval_ms, 2),
            "first_token_ms": round(result.first_token_ms, 2),
            "llm_ms": round(result.generation_ms, 2),
            "total_ms": round(result.total_ms, 2),
            "cache_enabled": state.redis_ok,
            "docs_fingerprint": state.docs_fingerprint,
        }
    )
