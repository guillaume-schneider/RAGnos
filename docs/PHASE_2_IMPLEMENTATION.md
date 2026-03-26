# Phase 2 Implementation Summary

Date: 2026-03-26

## Goal

Phase 2 focused on stability and maintainability without changing the user-facing RAG behavior.

The main objectives were:

- split the backend logic into smaller modules
- make configuration explicit and validated
- make `.prompt` the source of truth for the system prompt
- add stronger automated tests
- add a local benchmark command for latency checks

## What Was Implemented

### 1. Modular package split

The previous shared logic concentrated in `src/ragnos/core.py` was split into dedicated modules:

- `src/ragnos/config.py`
- `src/ragnos/cache.py`
- `src/ragnos/documents.py`
- `src/ragnos/indexing.py`
- `src/ragnos/prompts.py`
- `src/ragnos/runtime.py`
- `src/ragnos/telemetry.py`
- `src/ragnos/benchmark.py`

Current responsibilities:

- `config.py`: defaults, env parsing, config validation, prompt loading
- `cache.py`: cache namespace and key generation
- `documents.py`: PDF discovery, fingerprinting, loading, chunk splitting, context formatting
- `indexing.py`: runtime readiness checks, Chroma helpers, Ollama helpers, ingest workflow
- `prompts.py`: prompt-file loading and prompt-template construction
- `runtime.py`: shared runtime state and query execution
- `telemetry.py`: structured JSON logging
- `benchmark.py`: local startup/query benchmark CLI

### 2. `core.py` converted into a compatibility facade

`src/ragnos/core.py` is no longer the main implementation module.

It now re-exports the expected helpers, constants, and dataclasses so older imports continue to work.

This preserves compatibility while allowing the real implementation to live in narrower modules.

### 3. Explicit configuration with validation

`load_config()` was expanded to support the full runtime configuration surface through:

- explicit function arguments
- environment variables
- code defaults

Precedence is:

1. explicit function args
2. environment variables
3. defaults

Supported environment variables now include:

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

Validation added:

- positive integers for `CACHE_TTL`, `CHUNK_SIZE`, `TOP_K`
- non-negative `CHUNK_OVERLAP`
- `CHUNK_OVERLAP < CHUNK_SIZE`
- non-empty model names and URLs
- valid prompt path and prompt content

### 4. `.prompt` became the prompt source of truth

The system prompt is now loaded from `.prompt` by default.

Implementation details:

- default prompt path: `./.prompt`
- prompt is loaded during config construction
- prompt text is stored on `AppConfig.prompt_text`
- cache namespacing still includes the prompt text
- invalid or missing prompt files fail fast

The `.prompt` file was also normalized into plain UTF-8 text instead of Python-style quoted lines.

### 5. Runtime/query path cleanup

`src/ragnos/app.py` now uses the modular services instead of importing everything from a monolithic core module.

The runtime still preserves the phase 1 behavior:

- startup validates readiness
- runtime state is reused per process
- Redis is optional
- cache hits are returned directly

Phase 2 also added explicit `first_token_ms` timing in the main query path logs.

### 6. Local benchmark command

A new benchmark command was added:

```powershell
uv run python benchmark.py --question "..." --repetitions 3
```

It measures:

- `startup_ms`
- `retrieval_ms`
- `first_token_ms`
- `generation_ms`
- `total_ms`
- `chunks_used`

Behavior:

- validates runtime readiness first
- builds runtime state once
- runs uncached query repetitions
- prints a human-readable summary to stdout

### 7. Root wrappers restored

To keep short commands and compatibility, these wrapper entrypoints were added or restored at the repository root:

- `main.py`
- `ingest.py`
- `benchmark.py`
- `rag_core.py`

This means these commands work:

```powershell
uv run chainlit run main.py
uv run python ingest.py
uv run python benchmark.py --question "..." --repetitions 3
```

### 8. Test suite expansion

The old single test file was replaced with a broader suite:

- `tests/test_config.py`
- `tests/test_prompts.py`
- `tests/test_indexing.py`
- `tests/test_cache.py`
- `tests/test_core_compat.py`
- `tests/test_benchmark.py`
- `tests/test_support.py`

Covered behavior:

- config precedence
- config validation errors
- prompt loading and prompt formatting
- fingerprint logic
- ingest no-op and rebuild behavior
- readiness validation
- cache namespace invalidation
- compatibility facade exports
- benchmark CLI smoke behavior

### 9. Documentation updates

The operator and technical docs were updated to match phase 2:

- `README.md`
- `docs/PROJECT_DOCUMENTATION.md`
- `chainlit.md`

## File Summary

### New modules

- `src/ragnos/config.py`
- `src/ragnos/cache.py`
- `src/ragnos/documents.py`
- `src/ragnos/indexing.py`
- `src/ragnos/prompts.py`
- `src/ragnos/runtime.py`
- `src/ragnos/telemetry.py`
- `src/ragnos/benchmark.py`

### Updated runtime files

- `src/ragnos/app.py`
- `src/ragnos/ingest.py`
- `src/ragnos/core.py`
- `src/ragnos/__init__.py`

### Root compatibility files

- `main.py`
- `ingest.py`
- `benchmark.py`
- `rag_core.py`

### Updated support files

- `.prompt`
- `README.md`
- `docs/PROJECT_DOCUMENTATION.md`
- `chainlit.md`

### Test files

- `tests/test_config.py`
- `tests/test_prompts.py`
- `tests/test_indexing.py`
- `tests/test_cache.py`
- `tests/test_core_compat.py`
- `tests/test_benchmark.py`
- `tests/test_support.py`

## How To Run The Project

### 1. Start Redis

```powershell
docker compose up -d redis
```

### 2. Make sure Ollama is running

Required models:

```powershell
ollama pull mistral
ollama pull nomic-embed-text
```

### 3. Build or refresh the index

```powershell
uv run python ingest.py
```

Optional overrides:

```powershell
uv run python ingest.py --docs-dir ./documents --chroma-dir ./chroma_data
```

### 4. Start the app

```powershell
uv run chainlit run main.py
```

### 5. Run the benchmark

```powershell
uv run python benchmark.py --question "Quel est l'article applicable ?" --repetitions 3
```

## How To Test Phase 2

### Unit tests

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

### Compile/import verification

Run:

```powershell
.\.venv\Scripts\python.exe -m py_compile main.py ingest.py benchmark.py rag_core.py src\ragnos\app.py src\ragnos\benchmark.py src\ragnos\cache.py src\ragnos\config.py src\ragnos\core.py src\ragnos\documents.py src\ragnos\indexing.py src\ragnos\ingest.py src\ragnos\prompts.py src\ragnos\runtime.py src\ragnos\telemetry.py
```

### CLI help checks

Run:

```powershell
.\.venv\Scripts\python.exe ingest.py --help
.\.venv\Scripts\python.exe benchmark.py --help
```

### Wrapper import check

Run:

```powershell
@'
import main
import rag_core
print("IMPORT_OK")
'@ | .\.venv\Scripts\python.exe -
```

### Manual app check

Recommended sequence:

1. Put one or more PDFs into `documents/`
2. Run `uv run python ingest.py`
3. Run `uv run chainlit run main.py`
4. Ask one question twice
5. Confirm the second answer returns normally from cache
6. Edit `.prompt` or replace a PDF
7. Run `uv run python ingest.py` again
8. Restart the app and confirm startup still succeeds

### Manual benchmark check

Run:

```powershell
uv run python benchmark.py --question "Votre question" --repetitions 3
```

Check that the command prints:

- `startup_ms`
- `retrieval_ms`
- `first_token_ms`
- `generation_ms`
- `total_ms`
- `chunks_used`

## Useful Commands

Show unit test results:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Rebuild the index:

```powershell
uv run python ingest.py
```

Start the app:

```powershell
uv run chainlit run main.py
```

Run a benchmark:

```powershell
uv run python benchmark.py --question "..." --repetitions 3
```

Show benchmark help:

```powershell
.\.venv\Scripts\python.exe benchmark.py --help
```

## Known Scope Boundaries

Phase 2 did not implement:

- citations in answers
- upload-triggered ingest
- incremental indexing
- evaluation datasets
- production observability

Those remain later-phase items.

## Conclusion

Phase 2 did not change the product direction, but it substantially improved the engineering base:

- clearer module boundaries
- stronger config behavior
- prompt source-of-truth cleanup
- local benchmarking support
- broader automated test coverage
- preserved compatibility for older commands and imports

This makes the codebase easier to extend in later phases without carrying the previous `core.py` concentration problem forward.
