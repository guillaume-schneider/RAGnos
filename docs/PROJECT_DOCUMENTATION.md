# RAGnos Project Documentation

## Overview

RAGnos is a local Retrieval-Augmented Generation application built around Chainlit, Ollama, Chroma, and Redis. Its implementation is organized into small modules under `src/ragnos/`; `src/ragnos/core.py` provides a compatibility facade.

## Repository Structure

### Runtime code

- `src/ragnos/app.py`: Chainlit runtime and chat-serving flow
- `src/ragnos/benchmark.py`: local latency benchmark CLI
- `src/ragnos/cache.py`: cache namespace and key helpers
- `src/ragnos/catalog.py`: per-document manifest and file-hash tracking
- `src/ragnos/config.py`: config defaults, env parsing, prompt loading, validation
- `src/ragnos/core.py`: compatibility facade over the modular implementation
- `src/ragnos/documents.py`: corpus discovery, fingerprinting, loading, splitting, formatting
- `src/ragnos/evals.py`: local regression eval runner
- `src/ragnos/health.py`: health report helpers
- `src/ragnos/healthcheck.py`: healthcheck CLI
- `src/ragnos/indexing.py`: runtime readiness checks, ingest flow, Chroma helpers, model helpers
- `src/ragnos/ingest.py`: manual ingest CLI
- `src/ragnos/prompts.py`: prompt-file loading and prompt construction
- `src/ragnos/runtime.py`: process runtime state and query execution
- `src/ragnos/telemetry.py`: structured JSON logging

### Compatibility wrappers

- `main.py`
- `ingest.py`
- `benchmark.py`
- `healthcheck.py`
- `evals.py`
- `rag_core.py`

### Data and generated state

- `tools/extracts/`: source corpus, including PDF documents and JSON video transcripts
- `chroma_data/`: persisted Chroma index
- `chroma_data/.fingerprint`: corpus fingerprint marker
- `chroma_data/manifest.json`: per-document index manifest
- `.prompt`: default system prompt file
- `evals/regression.jsonl`: seed eval dataset

## Responsibilities

### `config.py`

Owns:

- configuration defaults
- env var parsing
- explicit override precedence
- numeric and string validation
- prompt path resolution and prompt text loading

### `documents.py`

Owns:

- corpus discovery
- corpus fingerprinting
- PDF and JSON loading
- chunk splitting
- retrieved-context formatting

### `indexing.py`

Owns:

- index marker helpers
- runtime readiness validation
- incremental upsert/delete planning per document
- Chroma open/build helpers
- Ollama model and embedding construction
- full ingest workflow

### `catalog.py`

Owns:

- per-document file hashing
- manifest read/write
- record structure for indexed files
- stable linkage between source files and chunk ids

### `runtime.py`

Owns:

- runtime state creation
- Redis availability detection
- cached and uncached query execution
- citation extraction and answer rendering
- first-token, retrieval, generation, and total timing capture

### `core.py`

Owns no primary implementation logic now. It re-exports the stable public helpers and constants so older imports continue to work.

### `health.py` and `healthcheck.py`

Own:

- prompt/docs/index readiness checks
- Redis and Ollama dependency checks
- operator-readable status summaries

### `evals.py`

Owns:

- JSONL eval dataset loading
- live local-stack regression execution
- pass/fail summary reporting

## Configuration Model

`load_config()` now supports explicit overrides, environment variables, and defaults with this precedence:

1. explicit function arguments
2. environment variables
3. in-code defaults

Supported environment variables:

- `DOCS_DIR`
- `CHROMA_DIR`
- `REDIS_URL`
- `OLLAMA_BASE_URL`
- `CACHE_TTL`
- `CHUNK_SIZE`
- `CHUNK_OVERLAP`
- `TOP_K`
- `EMBEDDING_MODEL`
- `LLM_MODEL`
- `PROMPT_PATH`

Validation rules:

- `CACHE_TTL`, `CHUNK_SIZE`, and `TOP_K` must be positive integers
- `CHUNK_OVERLAP` must be non-negative and smaller than `CHUNK_SIZE`
- model names and URLs must be non-empty
- `PROMPT_PATH` must exist, be valid UTF-8, be non-empty, and contain `{context}`

## Prompt Handling

`.prompt` is the source of truth for the system prompt.

The default prompt path is `./.prompt`. The prompt text is loaded during config creation and stored on `AppConfig.prompt_text`. That same text is reused for:

- prompt template construction
- cache namespace derivation
- compatibility exports through `ragnos.core`

## Runtime Pipeline

### Ingestion

Run:

```powershell
uv run python ingest.py
```

Flow:

1. Load config from env vars and CLI overrides.
2. Discover supported files in `DOCS_DIR`.
3. Compute a corpus fingerprint from file name, modification time, and size.
4. Compare current documents against `manifest.json`.
5. Skip unchanged files, upsert new/changed files, and delete removed-file chunks.
6. Fall back to a full rebuild only when the manifest or store is unusable.
7. Rewrite `manifest.json` and the corpus `.fingerprint`.

### Chat startup

Run:

```powershell
uv run chainlit run main.py
```

Flow:

1. Load and validate config, including `.prompt`.
2. Validate that `DOCS_DIR` exists and contains supported files, or offer upload if the corpus is empty.
3. Recompute the current corpus fingerprint.
4. Verify that `CHROMA_DIR` exists, contains index artifacts, and has a matching `.fingerprint`.
5. Expose in-chat `/upload`, `/refresh`, and `/status` commands.
6. Lazily build or reuse process-level runtime state.

The runtime state includes:

- app config
- docs fingerprint
- cache namespace
- Redis client and availability flag
- embeddings object
- vector store and retriever
- LLM instance
- prompt text and prompt template

### Query handling

For each message:

1. Normalize the question and derive a cache key from the current cache namespace.
2. Try Redis first when available.
3. On cache miss, retrieve top `k` chunks from Chroma.
4. Format the chunks into prompt context.
5. Stream the Ollama answer back to the UI.
6. Append a deterministic `Sources` block built from retrieved document metadata.
7. Cache the fully rendered answer and log timings.

## Benchmark Pipeline

Run:

```powershell
uv run python benchmark.py --question "..." --repetitions 3
```

Flow:

1. Load and validate config.
2. Validate runtime readiness.
3. Build runtime state once and measure `startup_ms`.
4. Run the same question `N` times with cache bypass enabled.
5. Report average `retrieval_ms`, `first_token_ms`, `generation_ms`, `total_ms`, and `chunks_used`.

## Compatibility Layer

The following commands are preserved:

- `uv run python ingest.py`
- `uv run chainlit run main.py`
- `uv run python benchmark.py --question "..."`
- `uv run python healthcheck.py`
- `uv run python evals.py --dataset evals/regression.jsonl`

The `rag_core.py` wrapper preserves legacy imports, while `src/ragnos/core.py` preserves the older helper surface inside the package.

## Test Coverage

The unit suite now covers:

- config precedence and validation
- prompt-file loading and prompt-template behavior
- fingerprinting
- incremental ingest no-op, update, delete, and rebuild paths
- runtime-readiness failure states
- cache namespace invalidation
- citation rendering
- `ragnos.core` compatibility exports
- benchmark CLI smoke behavior
- healthcheck CLI smoke behavior
- eval runner smoke behavior

## Reading Order

1. `README.md`
2. `docs/PROJECT_DOCUMENTATION.md`
3. `src/ragnos/config.py`
4. `src/ragnos/indexing.py`
5. `src/ragnos/runtime.py`
6. `src/ragnos/app.py`
