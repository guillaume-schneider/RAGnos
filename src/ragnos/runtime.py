from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Sequence

import redis.asyncio as redis
from langchain_core.documents import Document
from redis.exceptions import RedisError

from .cache import build_cache_key, build_cache_namespace
from .config import AppConfig
from .documents import format_docs
from .indexing import create_embeddings, create_llm, open_vectorstore
from .prompts import build_prompt
from .telemetry import log_event


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


@dataclass(frozen=True, slots=True)
class Citation:
    source: str
    page: str
    chunk_index: int
    source_type: str = ""


@dataclass(frozen=True, slots=True)
class QueryResult:
    answer: str
    docs: Sequence[Document]
    sources: list[str]
    citations: list[Citation]
    chunks_used: int
    retrieval_ms: float
    first_token_ms: float
    generation_ms: float
    total_ms: float
    cache_hit: bool


def build_citations(docs: Sequence[Document]) -> list[Citation]:
    seen: set[tuple[str, str, str]] = set()
    citations: list[Citation] = []

    for doc in docs:
        source = Path(doc.metadata.get("source", "inconnu")).name
        page = str(doc.metadata.get("page", "?"))
        chunk_index = int(doc.metadata.get("chunk_index", 0))
        source_type = str(doc.metadata.get("source_type", ""))
        key = (source, page, source_type)
        if key in seen:
            continue
        seen.add(key)
        citations.append(Citation(source=source, page=page, chunk_index=chunk_index, source_type=source_type))

    return citations


def render_citations(citations: Sequence[Citation]) -> str:
    if not citations:
        return ""

    lines = ["", "", "Sources:"]
    for citation in citations:
        if citation.source_type == "video_transcript" or citation.page == "transcript":
            location = "transcript video"
        elif citation.page == "json":
            location = "document JSON"
        else:
            location = f"page {citation.page}"
        lines.append(f"- {citation.source} ({location})")
    return "\n".join(lines)


def render_answer(answer_text: str, citations: Sequence[Citation]) -> str:
    return answer_text.rstrip() + render_citations(citations)


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


async def close_runtime_state(state: RuntimeState | None) -> None:
    if state is None or state.redis_client is None:
        return

    close_method = getattr(state.redis_client, "aclose", None)
    if close_method is None:
        close_method = getattr(state.redis_client, "close", None)
    if close_method is None:
        return

    result = close_method()
    if hasattr(result, "__await__"):
        await result


async def run_query(
    state: RuntimeState,
    question: str,
    *,
    use_cache: bool = True,
    stream_callback: Callable[[str], Awaitable[None]] | None = None,
) -> QueryResult:
    start_total = time.perf_counter()
    cache_key = build_cache_key(question, state.cache_namespace)

    if use_cache and state.redis_ok and state.redis_client:
        try:
            cached = await state.redis_client.get(cache_key)
            if cached:
                return QueryResult(
                    answer=cached,
                    docs=[],
                    sources=[],
                    citations=[],
                    chunks_used=0,
                    retrieval_ms=0.0,
                    first_token_ms=0.0,
                    generation_ms=0.0,
                    total_ms=(time.perf_counter() - start_total) * 1000,
                    cache_hit=True,
                )
        except RedisError as exc:
            log_event({"event": "redis_read_error", "error": str(exc)})

    retrieval_start = time.perf_counter()
    docs = await state.retriever.ainvoke(question)
    retrieval_ms = (time.perf_counter() - retrieval_start) * 1000

    context = format_docs(docs)
    final_prompt = state.prompt.invoke({"context": context, "input": question})

    llm_start = time.perf_counter()
    first_token_ms = 0.0
    answer = ""

    async for chunk in state.llm.astream(final_prompt):
        token = chunk.content or ""
        if not token:
            continue
        if first_token_ms == 0.0:
            first_token_ms = (time.perf_counter() - llm_start) * 1000
        answer += token
        if stream_callback:
            await stream_callback(token)

    citations = build_citations(docs)
    citation_block = render_citations(citations)
    rendered_answer = answer.rstrip() + citation_block
    if citation_block and stream_callback:
        await stream_callback(citation_block)

    generation_ms = (time.perf_counter() - llm_start) * 1000

    if use_cache and state.redis_ok and state.redis_client:
        try:
            await state.redis_client.set(cache_key, rendered_answer, ex=state.config.cache_ttl)
        except RedisError as exc:
            log_event({"event": "redis_write_error", "error": str(exc)})

    sources = sorted({citation.source for citation in citations})
    total_ms = (time.perf_counter() - start_total) * 1000

    return QueryResult(
        answer=rendered_answer,
        docs=docs,
        sources=sources,
        citations=citations,
        chunks_used=len(docs),
        retrieval_ms=retrieval_ms,
        first_token_ms=first_token_ms,
        generation_ms=generation_ms,
        total_ms=total_ms,
        cache_hit=False,
    )
