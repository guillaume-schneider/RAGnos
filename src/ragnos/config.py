from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .prompts import PromptError, load_prompt_text

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
DEFAULT_PROMPT_PATH = "./.prompt"
INGEST_COMMAND = "uv run python ingest.py"
BENCHMARK_COMMAND = 'uv run python benchmark.py --question "..." --repetitions 3'
HEALTHCHECK_COMMAND = "uv run python healthcheck.py"
EVALS_COMMAND = "uv run python evals.py --dataset evals/regression.jsonl"


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
    prompt_path: Path = Path(DEFAULT_PROMPT_PATH)
    prompt_text: str = ""


class ConfigError(ValueError):
    pass


def _pick_setting(explicit_value: object | None, env_name: str, default_value: object) -> object:
    if explicit_value is not None:
        return explicit_value
    env_value = os.getenv(env_name)
    if env_value is not None:
        return env_value
    return default_value


def _parse_non_empty_string(name: str, value: object) -> str:
    text = str(value).strip()
    if not text:
        raise ConfigError(f"{name} must be a non-empty string.")
    return text


def _parse_path(name: str, value: object) -> Path:
    text = _parse_non_empty_string(name, value)
    return Path(text)


def _parse_integer(name: str, value: object, *, minimum: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} must be an integer.") from exc

    if parsed < minimum:
        comparator = "greater than 0" if minimum == 1 else f"at least {minimum}"
        raise ConfigError(f"{name} must be {comparator}.")
    return parsed


def _load_prompt(prompt_path: Path, prompt_text: str | None) -> str:
    if prompt_text is not None:
        text = prompt_text.strip()
        if not text:
            raise ConfigError("prompt_text must not be empty when provided explicitly.")
        if "{context}" not in text:
            raise ConfigError("prompt_text must contain the {context} placeholder.")
        return text

    try:
        return load_prompt_text(prompt_path)
    except PromptError as exc:
        raise ConfigError(str(exc)) from exc


def load_config(
    *,
    docs_dir: str | Path | None = None,
    chroma_dir: str | Path | None = None,
    redis_url: str | None = None,
    ollama_base_url: str | None = None,
    cache_ttl: int | str | None = None,
    chunk_size: int | str | None = None,
    chunk_overlap: int | str | None = None,
    top_k: int | str | None = None,
    embedding_model: str | None = None,
    llm_model: str | None = None,
    prompt_path: str | Path | None = None,
    prompt_text: str | None = None,
) -> AppConfig:
    docs_dir_value = _parse_path("DOCS_DIR", _pick_setting(docs_dir, "DOCS_DIR", DEFAULT_DOCS_DIR))
    chroma_dir_value = _parse_path("CHROMA_DIR", _pick_setting(chroma_dir, "CHROMA_DIR", DEFAULT_CHROMA_DIR))
    redis_url_value = _parse_non_empty_string("REDIS_URL", _pick_setting(redis_url, "REDIS_URL", DEFAULT_REDIS_URL))
    ollama_base_url_value = _parse_non_empty_string(
        "OLLAMA_BASE_URL",
        _pick_setting(ollama_base_url, "OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL),
    )
    cache_ttl_value = _parse_integer("CACHE_TTL", _pick_setting(cache_ttl, "CACHE_TTL", DEFAULT_CACHE_TTL), minimum=1)
    chunk_size_value = _parse_integer(
        "CHUNK_SIZE",
        _pick_setting(chunk_size, "CHUNK_SIZE", DEFAULT_CHUNK_SIZE),
        minimum=1,
    )
    chunk_overlap_value = _parse_integer(
        "CHUNK_OVERLAP",
        _pick_setting(chunk_overlap, "CHUNK_OVERLAP", DEFAULT_CHUNK_OVERLAP),
        minimum=0,
    )
    top_k_value = _parse_integer("TOP_K", _pick_setting(top_k, "TOP_K", DEFAULT_TOP_K), minimum=1)
    embedding_model_value = _parse_non_empty_string(
        "EMBEDDING_MODEL",
        _pick_setting(embedding_model, "EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
    )
    llm_model_value = _parse_non_empty_string("LLM_MODEL", _pick_setting(llm_model, "LLM_MODEL", DEFAULT_LLM_MODEL))
    prompt_path_value = _parse_path("PROMPT_PATH", _pick_setting(prompt_path, "PROMPT_PATH", DEFAULT_PROMPT_PATH))

    if chunk_overlap_value >= chunk_size_value:
        raise ConfigError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE.")

    prompt_text_value = _load_prompt(prompt_path_value, prompt_text)

    return AppConfig(
        docs_dir=docs_dir_value,
        chroma_dir=chroma_dir_value,
        redis_url=redis_url_value,
        ollama_base_url=ollama_base_url_value,
        cache_ttl=cache_ttl_value,
        chunk_size=chunk_size_value,
        chunk_overlap=chunk_overlap_value,
        top_k=top_k_value,
        embedding_model=embedding_model_value,
        llm_model=llm_model_value,
        prompt_path=prompt_path_value,
        prompt_text=prompt_text_value,
    )
