from __future__ import annotations

import hashlib
import json

from .config import AppConfig


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
