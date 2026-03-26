# Phase 1 Implementation Summary

Date: 2026-03-26

## Goal

Phase 1 focused on the first practical improvement cycle for the local RAG stack:

- remove heavy ingest work from chat startup
- separate indexing from runtime serving
- make cache hits safer after corpus or config changes
- document the operator workflow clearly enough for local/internal use

This phase did not try to redesign the full architecture. It concentrated on response-time wins, safer runtime behavior, and a cleaner operational model.

## Scope Delivered

The following items from the phase 1 plan were implemented.

### 1. Manual ingest entrypoint

A dedicated CLI ingest flow is now provided through:

```powershell
uv run python ingest.py
```

Optional overrides are available:

```powershell
uv run python ingest.py --docs-dir ./documents --chroma-dir ./chroma_data
```

Current implementation:

- CLI parsing lives in `src/ragnos/ingest.py`
- the root `ingest.py` file remains as a compatibility wrapper
- ingest uses the shared logic in `src/ragnos/core.py`

### 2. Fingerprint-based no-op ingest

Before rebuilding, ingest computes a corpus fingerprint from the PDF file set and checks the current on-disk marker.

If the fingerprint matches and the persisted Chroma directory is already valid, ingest exits without reloading PDFs or rebuilding embeddings.

If the fingerprint differs, ingest:

1. loads the PDFs
2. splits them into chunks
3. builds a fresh Chroma store in a temporary directory
4. replaces the target persisted index
5. writes the new `.fingerprint` marker

This keeps rebuild behavior simple while avoiding unnecessary work when the corpus is unchanged.

### 3. Runtime state separated from ingest

Chat serving no longer owns the indexing workflow.

The app runtime now builds and reuses a process-scoped state in `src/ragnos/app.py`. That runtime state contains:

- loaded app configuration
- current docs fingerprint
- derived cache namespace
- Redis client and availability flag
- embeddings object
- opened Chroma vector store
- retriever
- LLM instance
- prompt text and compiled prompt object

The runtime state is initialized lazily and protected behind an async lock so the process does not rebuild the same resources for every user session.

### 4. Startup validation instead of auto-rebuild

`on_chat_start` now validates readiness instead of trying to parse PDFs and build the index in-app.

The validation checks:

- source PDF directory exists
- PDFs are present
- persisted Chroma directory exists
- the index directory is not empty
- the current corpus fingerprint matches the stored `.fingerprint`

If the index is missing or stale, the app stops with an actionable message and tells the operator to run:

```powershell
uv run python ingest.py
```

This is the main runtime behavior change introduced in phase 1.

### 5. Stronger cache namespacing

Cache keys are no longer scoped only by the user question.

The cache namespace now depends on:

- docs fingerprint
- LLM model name
- prompt text
- `TOP_K`
- `CHUNK_SIZE`
- `CHUNK_OVERLAP`

The final Redis key is built from:

- normalized question
- derived cache namespace

This reduces the risk of serving stale answers after:

- corpus updates
- prompt changes
- model changes
- retrieval parameter changes

### 6. Faster cache-hit delivery

Cached answers are now returned directly instead of being replayed character by character through the UI stream.

This improves perceived speed and removes unnecessary overhead on the cache-hit path.

### 7. Operator documentation refresh

The local workflow documentation was updated to match the new behavior:

- `README.md` explains the ingest-first workflow
- `chainlit.md` was updated away from default scaffolding
- `docs/PROJECT_DOCUMENTATION.md` documents the reorganized package layout and runtime pipeline

## Architectural Result

After phase 1, the project is organized around the `src/ragnos/` package:

- `src/ragnos/app.py`: Chainlit runtime and request handling
- `src/ragnos/core.py`: shared config, fingerprinting, ingest helpers, cache helpers, retrieval helpers
- `src/ragnos/ingest.py`: manual ingest command

Compatibility wrappers remain at the repository root:

- `main.py`
- `ingest.py`
- `rag_core.py`

This keeps existing commands working while moving the implementation into a package structure.

## New Runtime and Operator Flow

### Index build / refresh

1. Put PDFs in `documents/`
2. Run `uv run python ingest.py`
3. Wait for the persisted Chroma index and `.fingerprint` marker to be updated

### App startup

1. Run `uv run chainlit run main.py`
2. App validates the corpus and persisted index
3. If valid, the process warms the shared runtime state
4. If invalid, the app refuses startup work and tells the operator to run ingest

### Query handling

1. Build the cache key from the normalized question and current cache namespace
2. Check Redis if available
3. On cache miss, retrieve chunks from Chroma
4. Build prompt context and call the local LLM
5. Stream the generated answer
6. Store the final answer in Redis with TTL

## Verification Implemented

Phase 1 included test coverage for the core behavior introduced by the refactor.

`tests/test_rag_core.py` covers:

- fingerprint changes when file stats change
- ingest no-op when the fingerprint matches
- full rebuild when the fingerprint changes
- actionable startup validation for:
  - missing index
  - empty index
  - stale index
- cache namespace changes when prompt, model, fingerprint, or retrieval settings change

The workflow also included basic import/compile validation and CLI invocation checks during implementation.

## Practical Benefits

The main gains from phase 1 are operational and latency-related.

- Chat startup no longer pays the cost of PDF parsing and chunk preparation.
- Runtime services are reused within the process instead of being rebuilt per session.
- Cached answers are returned faster.
- Cache correctness is improved after document or configuration changes.
- Failure states are clearer for the operator.

For a local/internal deployment, this is a meaningful improvement even though the underlying retrieval and generation stack is unchanged.

## Deferred To Later Phases

Phase 1 intentionally did not implement the following items:

- incremental per-document indexing
- upload-triggered ingest
- prompt externalization as the single source of truth
- richer answer citations in the UI
- benchmark commands and evaluation datasets
- deeper module split beyond the current `core.py` concentration
- broader security hardening and operational observability

These remain valid next steps after the first performance and separation pass.

## Conclusion

Phase 1 moved the project from a prototype that mixed ingest and serving concerns into a cleaner local RAG workflow:

- ingest is explicit
- startup is lighter
- runtime state is shared
- cache behavior is safer
- operator instructions are clearer

It is still a small local system, but it now has a more defensible structure for future improvements.
