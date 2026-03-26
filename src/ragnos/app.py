from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Any

import chainlit as cl
import redis.asyncio as redis
from redis.exceptions import RedisError

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ragnos.core import (
    AppConfig,
    INGEST_COMMAND,
    build_cache_key,
    build_cache_namespace,
    build_prompt,
    create_embeddings,
    create_llm,
    format_docs,
    load_config,
    log_event,
    open_vectorstore,
    validate_runtime_readiness,
)

CONFIG = load_config()


class RuntimeState:
    def __init__(
        self,
        *,
        config: AppConfig,
        docs_fingerprint: str,
        cache_namespace: str,
        redis_client: Any | None,
        redis_ok: bool,
        embeddings: Any,
        vectorstore: Any,
        retriever: Any,
        llm: Any,
        prompt_text: str,
        prompt: Any,
    ) -> None:
        self.config = config
        self.docs_fingerprint = docs_fingerprint
        self.cache_namespace = cache_namespace
        self.redis_client = redis_client
        self.redis_ok = redis_ok
        self.embeddings = embeddings
        self.vectorstore = vectorstore
        self.retriever = retriever
        self.llm = llm
        self.prompt_text = prompt_text
        self.prompt = prompt


_runtime_lock = asyncio.Lock()
_runtime_state: RuntimeState | None = None


async def build_runtime_state(config: AppConfig, docs_fingerprint: str) -> RuntimeState:
    redis_client = None
    redis_ok = False

    try:
        redis_client = redis.from_url(config.redis_url, decode_responses=True)
        await redis_client.ping()
        redis_ok = True
    except Exception as exc:
        log_event({"event": "redis_unavailable", "error": str(exc)})

    embeddings = create_embeddings(config)
    vectorstore = open_vectorstore(config, embeddings)
    retriever = vectorstore.as_retriever(search_kwargs={"k": config.top_k})
    llm = create_llm(config)
    prompt = build_prompt(config)

    return RuntimeState(
        config=config,
        docs_fingerprint=docs_fingerprint,
        cache_namespace=build_cache_namespace(config, docs_fingerprint),
        redis_client=redis_client,
        redis_ok=redis_ok,
        embeddings=embeddings,
        vectorstore=vectorstore,
        retriever=retriever,
        llm=llm,
        prompt_text=config.prompt_text,
        prompt=prompt,
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


@cl.on_chat_start
async def on_chat_start() -> None:
    msg = await cl.Message(content="â³ Initialisation du systeme RAG...").send()

    validation = validate_runtime_readiness(CONFIG)
    if not validation.is_ready or not validation.docs_fingerprint:
        msg.content = validation.message
        await msg.update()
        return

    try:
        state = await get_runtime_state(CONFIG, validation.docs_fingerprint)
    except Exception as exc:
        log_event({"event": "runtime_init_failed", "error": str(exc)})
        msg.content = f"âŒ Impossible d'ouvrir l'index local.\nExecutez `{INGEST_COMMAND}`."
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

    msg.content = (
        "âœ… Systeme pret.\n"
        f"- Redis : {'ON' if state.redis_ok else 'OFF'}\n"
        f"- PDFs : {validation.pdf_count}\n"
        "- Index : ready"
    )
    await msg.update()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    start_total = time.perf_counter()
    state: RuntimeState | None = cl.user_session.get("runtime_state")

    if state is None:
        validation = validate_runtime_readiness(CONFIG)
        if not validation.is_ready or not validation.docs_fingerprint:
            await cl.Message(content=validation.message).send()
            return
        try:
            state = await get_runtime_state(CONFIG, validation.docs_fingerprint)
        except Exception as exc:
            log_event({"event": "runtime_init_failed", "error": str(exc)})
            await cl.Message(content=f"âŒ Impossible d'ouvrir l'index local.\nExecutez `{INGEST_COMMAND}`.").send()
            return
        cl.user_session.set("runtime_state", state)

    question = message.content.strip()
    cache_key = build_cache_key(question, state.cache_namespace)
    ui_msg = await cl.Message(content="").send()

    if state.redis_ok and state.redis_client:
        try:
            cached = await state.redis_client.get(cache_key)
            if cached:
                ui_msg.content = cached
                await ui_msg.update()
                log_event(
                    {
                        "event": "cache_hit",
                        "question": question,
                        "docs_fingerprint": state.docs_fingerprint,
                    }
                )
                return
        except RedisError as exc:
            log_event({"event": "redis_read_error", "error": str(exc)})

    retrieval_start = time.perf_counter()
    docs = await state.retriever.ainvoke(question)
    retrieval_ms = (time.perf_counter() - retrieval_start) * 1000

    context = format_docs(docs)
    final_prompt = state.prompt.invoke({"context": context, "input": question})

    llm_start = time.perf_counter()
    answer = ""
    async for chunk in state.llm.astream(final_prompt):
        token = chunk.content or ""
        answer += token
        await ui_msg.stream_token(token)

    llm_ms = (time.perf_counter() - llm_start) * 1000
    await ui_msg.update()

    if state.redis_ok and state.redis_client:
        try:
            await state.redis_client.set(cache_key, answer, ex=state.config.cache_ttl)
        except RedisError as exc:
            log_event({"event": "redis_write_error", "error": str(exc)})

    total_ms = (time.perf_counter() - start_total) * 1000
    sources = sorted({Path(doc.metadata.get("source", "")).name for doc in docs})

    log_event(
        {
            "event": "rag_query",
            "question": question,
            "chunks_used": len(docs),
            "sources": sources,
            "retrieval_ms": round(retrieval_ms, 2),
            "llm_ms": round(llm_ms, 2),
            "total_ms": round(total_ms, 2),
            "cache_enabled": state.redis_ok,
            "docs_fingerprint": state.docs_fingerprint,
        }
    )
