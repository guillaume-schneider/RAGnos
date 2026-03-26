# RAGnos Project Documentation

## Overview

RAGnos is a local Retrieval-Augmented Generation application built around Chainlit, Ollama, Chroma, and Redis.

The repository is organized around a `src/ragnos/` package:

- `src/ragnos/app.py`: Chainlit runtime and chat-serving flow
- `src/ragnos/core.py`: shared configuration, ingest, retrieval, cache, and model helpers
- `src/ragnos/ingest.py`: CLI entrypoint for building or refreshing the index

The root-level `main.py`, `ingest.py`, and `rag_core.py` files are thin wrappers kept for command and import compatibility.

## Repository structure

### Runtime code

- `src/ragnos/app.py`
- `src/ragnos/core.py`
- `src/ragnos/ingest.py`
- `src/ragnos/__init__.py`

### Project support files

- `README.md`: operator quickstart
- `chainlit.md`: Chainlit welcome content
- `docs/ASSESSMENT.md`: project assessment and roadmap
- `tests/test_rag_core.py`: unit tests for core logic

### Data and generated state

- `documents/`: source PDFs
- `chroma_data/`: persisted Chroma index
- `chroma_data/.fingerprint`: corpus fingerprint marker

## Responsibilities

### `src/ragnos/app.py`

This module serves the application once an index already exists.

It handles:

- Chainlit lifecycle hooks
- process-scoped runtime state
- Redis-backed answer caching
- retrieval and generation flow
- startup validation messaging

### `src/ragnos/core.py`

This module contains shared backend logic used by both the app runtime and ingest command.

It provides:

- environment-based configuration loading
- corpus discovery and fingerprinting
- runtime readiness checks
- PDF loading and chunk splitting
- Chroma build/open helpers
- Ollama embedding and chat model helpers
- prompt construction
- cache namespace and key generation
- index rebuild workflow helpers

### `src/ragnos/ingest.py`

This module is the manual CLI entrypoint for index management.

It is responsible for:

- parsing CLI arguments
- loading configuration
- deciding whether the current index is still valid
- rebuilding the Chroma index when the corpus changed
- logging and returning an ingest result

## Runtime pipeline

### Ingestion

Run:

```powershell
uv run python ingest.py
```

Flow:

1. Load config from environment variables and optional CLI overrides.
2. Discover PDFs in `DOCS_DIR`.
3. Compute a corpus fingerprint from file name, modification time, and size.
4. Skip rebuilding if the fingerprint matches the current on-disk index.
5. Otherwise load PDFs, split them into chunks, embed them, and build a fresh Chroma index in a temporary sibling directory.
6. Replace the target index directory and write the new `.fingerprint` marker.

### Chat startup

Run:

```powershell
uv run chainlit run main.py
```

Flow:

1. Validate that `DOCS_DIR` exists and contains PDFs.
2. Recompute the current corpus fingerprint.
3. Verify that `CHROMA_DIR` exists, contains index artifacts, and has a matching `.fingerprint`.
4. Lazily build or reuse process-level runtime state.

The runtime state includes:

- app config
- docs fingerprint
- cache namespace
- Redis client and availability flag
- embeddings object
- vector store and retriever
- LLM instance
- prompt text and template

### Query handling

For each message:

1. Normalize the question and build a cache key.
2. Try Redis first when available.
3. On cache miss, retrieve top `k` chunks from Chroma.
4. Format the chunks into prompt context.
5. Stream the Ollama answer back to the UI.
6. Cache the final answer and log timings.

## Compatibility layer

The root-level wrappers exist so these commands still work:

- `uv run python ingest.py`
- `uv run chainlit run main.py`

The `rag_core.py` wrapper also preserves older imports while the canonical implementation now lives in `src/ragnos/core.py`.

## Environment variables

- `DOCS_DIR`: PDF source directory
- `CHROMA_DIR`: persisted Chroma directory
- `REDIS_URL`: Redis connection string
- `OLLAMA_BASE_URL`: Ollama HTTP endpoint

## Reading order

1. `README.md`
2. `docs/PROJECT_DOCUMENTATION.md`
3. `src/ragnos/core.py`
4. `src/ragnos/ingest.py`
5. `src/ragnos/app.py`
