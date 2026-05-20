from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Iterable

import chainlit as cl
from chainlit.context import context
from chainlit.user import User

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ragnos.cache import build_cache_namespace
from ragnos.config import AppConfig, ConfigError, INGEST_COMMAND, load_config
from ragnos.documents import list_pdf_paths
from ragnos.health import build_health_report, format_health_report
from ragnos.indexing import ingest_corpus, validate_runtime_readiness
from ragnos.local_history import LocalSQLiteDataLayer
from ragnos.runtime import RuntimeState, build_runtime_state, close_runtime_state, run_query
from ragnos.telemetry import log_event

PDF_ACCEPT = ["application/pdf"]
UPLOAD_MAX_FILES = 10
UPLOAD_MAX_SIZE_MB = 100
TRANSCRIPT_SESSION_KEY = "conversation_transcript"
TRANSCRIPT_STORAGE_DIR = Path(".files") / "transcripts"
HISTORY_DB_PATH = Path(".files") / "history.sqlite3"
LOCAL_AUTH_USERNAME = os.getenv("CHAINLIT_AUTH_USERNAME", "admin")
LOCAL_AUTH_PASSWORD = os.getenv("CHAINLIT_AUTH_PASSWORD", "ragnos")

try:
    CONFIG = load_config()
    CONFIG_ERROR: str | None = None
except ConfigError as exc:
    CONFIG = None
    CONFIG_ERROR = str(exc)


_runtime_lock = asyncio.Lock()
_runtime_state: RuntimeState | None = None
_history_data_layer = LocalSQLiteDataLayer(HISTORY_DB_PATH)


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


def _transcript_storage_key() -> str:
    session = getattr(context, "session", None)
    if session is None:
        return "default"

    candidates = [
        getattr(session, "thread_id_to_resume", None),
        getattr(session, "thread_id", None),
        getattr(session, "id", None),
    ]
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return "default"


def _transcript_file() -> Path:
    TRANSCRIPT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return TRANSCRIPT_STORAGE_DIR / f"{_transcript_storage_key()}.json"


def _load_transcript_from_disk() -> list[dict[str, str]]:
    path = _transcript_file()
    if not path.exists():
        return []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(payload, list):
        return []

    transcript: list[dict[str, str]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        author = entry.get("author")
        content = entry.get("content")
        message_type = entry.get("type")
        if isinstance(author, str) and isinstance(content, str) and isinstance(message_type, str):
            transcript.append(
                {
                    "author": author,
                    "content": content,
                    "type": message_type,
                }
            )
    return transcript


def _save_transcript_to_disk(transcript: list[dict[str, str]]) -> None:
    _transcript_file().write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_transcript() -> list[dict[str, str]]:
    transcript = cl.user_session.get(TRANSCRIPT_SESSION_KEY, [])
    if isinstance(transcript, list) and transcript:
        return list(transcript)

    disk_transcript = _load_transcript_from_disk()
    if disk_transcript:
        cl.user_session.set(TRANSCRIPT_SESSION_KEY, disk_transcript)
    return disk_transcript


def _record_transcript_message(content: str, *, author: str, message_type: str) -> None:
    cleaned_content = content.strip()
    if not cleaned_content:
        return

    transcript = _get_transcript()
    entry = {
        "author": author,
        "content": cleaned_content,
        "type": message_type,
    }
    if transcript and transcript[-1] == entry:
        return

    transcript.append(entry)
    cl.user_session.set(TRANSCRIPT_SESSION_KEY, transcript)
    _save_transcript_to_disk(transcript)


async def _send_recorded_message(content: str, *, author: str | None = None, message_type: str = "assistant_message") -> None:
    sent_message = await cl.Message(content=content, author=author, type=message_type).send()
    _record_transcript_message(content, author=sent_message.author, message_type=message_type)


async def _replay_transcript() -> None:
    for entry in _get_transcript():
        await cl.Message(
            content=entry["content"],
            author=entry["author"],
            type=entry["type"],
        ).send()


def _thread_to_transcript(thread: dict | None) -> list[dict[str, str]]:
    if not thread:
        return []

    transcript: list[dict[str, str]] = []
    for step in thread.get("steps", []):
        step_type = step.get("type")
        if step_type not in {"user_message", "assistant_message"}:
            continue
        content = str(step.get("output") or "").strip()
        if not content:
            continue
        transcript.append(
            {
                "author": step.get("name") or ("User" if step_type == "user_message" else cl.config.ui.name),
                "content": content,
                "type": step_type,
            }
        )
    return transcript


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
        await _send_recorded_message("Aucun PDF recu. Utilisez /upload pour recommencer.")
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
        await _send_recorded_message("Aucun PDF disponible. Utilisez /upload pour ajouter des documents.")
        return None
    return await _reindex_and_reload(config, "Rafraichissement de l'index en cours...")


async def _handle_status_request(config: AppConfig) -> None:
    report = await build_health_report(config)
    await _send_recorded_message(format_health_report(report))


async def _initialize_session(*, restore_transcript: bool, replay_messages: bool, show_init_message: bool) -> bool:
    if restore_transcript and replay_messages and _get_transcript():
        await _replay_transcript()
        info_msg = None
    elif show_init_message:
        info_msg = await cl.Message(content="Initialisation du systeme RAG...").send()
    else:
        info_msg = None

    if CONFIG is None:
        if info_msg is None:
            await _send_recorded_message(_runtime_unavailable_message())
        else:
            info_msg.content = _runtime_unavailable_message()
            await info_msg.update()
        return False

    validation = validate_runtime_readiness(CONFIG)
    if validation.status in {"missing_docs_dir", "no_pdfs"}:
        if info_msg is None:
            await _send_recorded_message("Aucun corpus pret. Chargez des PDF pour demarrer.")
        else:
            info_msg.content = "Aucun corpus pret. Chargez des PDF pour demarrer."
            await info_msg.update()
        state = await _handle_upload_request(CONFIG)
        if state is None:
            return False
        pdf_count = len(list_pdf_paths(CONFIG.docs_dir))
        await _send_recorded_message(_ready_message(state, pdf_count))
        return True

    if not validation.is_ready or not validation.docs_fingerprint:
        content = validation.message + "\nUtilisez /refresh pour indexer le corpus existant."
        if info_msg is None:
            await _send_recorded_message(content)
        else:
            info_msg.content = content
            await info_msg.update()
        return False

    try:
        state = await get_runtime_state(CONFIG, validation.docs_fingerprint)
    except Exception as exc:
        log_event({"event": "runtime_init_failed", "error": str(exc)})
        content = f"Impossible d'ouvrir l'index local.\nExecutez `{INGEST_COMMAND}`."
        if info_msg is None:
            await _send_recorded_message(content)
        else:
            info_msg.content = content
            await info_msg.update()
        return False

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

    ready = _ready_message(state, validation.pdf_count)
    if info_msg is None:
        return True
    else:
        info_msg.content = ready
        await info_msg.update()
        _record_transcript_message(ready, author=info_msg.author, message_type=info_msg.type)
    return True


@cl.on_chat_start
async def on_chat_start() -> None:
    await _initialize_session(restore_transcript=False, replay_messages=False, show_init_message=True)


@cl.on_chat_resume
async def on_chat_resume(_thread: dict) -> None:
    transcript = _thread_to_transcript(_thread)
    cl.user_session.set(TRANSCRIPT_SESSION_KEY, transcript)
    if transcript:
        _save_transcript_to_disk(transcript)
    await _initialize_session(restore_transcript=False, replay_messages=False, show_init_message=False)


@cl.data_layer
def get_data_layer() -> LocalSQLiteDataLayer:
    return _history_data_layer


@cl.password_auth_callback
async def password_auth_callback(username: str, password: str) -> User | None:
    if username == LOCAL_AUTH_USERNAME and password == LOCAL_AUTH_PASSWORD:
        return User(identifier=username, display_name="Local Admin", metadata={"role": "operator"})
    return None


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
            await _send_recorded_message(validation.message + "\nUtilisez /upload ou /refresh.")
            return
        try:
            state = await get_runtime_state(CONFIG, validation.docs_fingerprint)
        except Exception as exc:
            log_event({"event": "runtime_init_failed", "error": str(exc)})
            await _send_recorded_message(f"Impossible d'ouvrir l'index local.\nExecutez `{INGEST_COMMAND}`.")
            return
        cl.user_session.set("runtime_state", state)

    if not question:
        await _send_recorded_message("Documents indexes. Posez maintenant votre question.")
        return

    _record_transcript_message(question, author="User", message_type="user_message")

    ui_msg = await cl.Message(content="").send()
    result = await run_query(state, question, stream_callback=ui_msg.stream_token)

    if result.cache_hit:
        ui_msg.content = result.answer
        await ui_msg.update()
        _record_transcript_message(result.answer, author=ui_msg.author, message_type=ui_msg.type)
        log_event(
            {
                "event": "cache_hit",
                "question": question,
                "docs_fingerprint": state.docs_fingerprint,
            }
        )
        return

    await ui_msg.update()
    _record_transcript_message(ui_msg.content, author=ui_msg.author, message_type=ui_msg.type)

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
