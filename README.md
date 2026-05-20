# RAGnos

Local RAG prototype built with Chainlit, Ollama, Chroma, and Redis.

The codebase is now organized around a modular `src/ragnos/` package. The root-level `main.py`, `ingest.py`, `benchmark.py`, and `rag_core.py` files are compatibility wrappers so the operator commands stay short.

## Repository Layout

```text
src/ragnos/
  app.py         Chainlit runtime
  benchmark.py   Local latency benchmark CLI
  cache.py       Cache namespace and key helpers
  catalog.py     Per-document index manifest helpers
  config.py      Config loading and validation
  core.py        Compatibility facade over the package modules
  documents.py   PDF discovery, fingerprinting, chunking, formatting
  evals.py       Local regression eval runner
  health.py      Health report helpers
  healthcheck.py Healthcheck CLI
  indexing.py    Index validation, ingest, vector store, and model helpers
  ingest.py      CLI entrypoint for index builds
  prompts.py     Prompt-file loading and prompt template construction
  runtime.py     Shared runtime state and query execution
  telemetry.py   JSON event logging
docs/            Project documentation
docs-site/       Docusaurus documentation site
documents/       Source PDF corpus
tests/           Unit tests
main.py          Chainlit wrapper entrypoint
ingest.py        CLI wrapper entrypoint
benchmark.py     Benchmark wrapper entrypoint
healthcheck.py   Healthcheck wrapper entrypoint
evals.py         Eval runner wrapper entrypoint
rag_core.py      Legacy import wrapper
```

## Local Workflow

1. Start Redis:

```powershell
docker compose up -d redis
```

2. Make sure Ollama is running and the required models are available:

```powershell
ollama pull mistral
ollama pull nomic-embed-text
```

3. Put your PDF files in `documents/`.

4. Make sure the system prompt is defined in `.prompt`.

5. Build or refresh the vector index:

```powershell
uv run python ingest.py
```

6. Start the Chainlit app:

```powershell
uv run chainlit run main.py
```

The app now uses a local login so Chainlit can persist and list conversation threads in the left sidebar.

Default local credentials:

- username: `admin`
- password: `ragnos`

You can override them with:

- `CHAINLIT_AUTH_USERNAME`
- `CHAINLIT_AUTH_PASSWORD`

Inside chat, the main operator commands are:

- `/upload`
- `/refresh`
- `/status`

## Benchmark

Run a local uncached latency benchmark with:

```powershell
uv run python benchmark.py --question "Quel est l'article applicable ?" --repetitions 3
```

This reports:

- `startup_ms`
- `retrieval_ms`
- `first_token_ms`
- `generation_ms`
- `total_ms`
- `chunks_used`

## Healthcheck

Run a local dependency and readiness check with:

```powershell
uv run python healthcheck.py
```

## Evals

Run the seed regression dataset with:

```powershell
uv run python evals.py --dataset evals/regression.jsonl
```

## Environment Variables

- `DOCS_DIR`: PDF directory. Default: `./documents`
- `CHROMA_DIR`: persisted Chroma directory. Default: `./chroma_data`
- `REDIS_URL`: Redis connection string. Default: `redis://localhost:6379/0`
- `OLLAMA_BASE_URL`: Ollama base URL. Default: `http://localhost:11434`
- `CACHE_TTL`: Redis cache TTL in seconds. Default: `3600`
- `CHUNK_SIZE`: chunk size used during splitting. Default: `800`
- `CHUNK_OVERLAP`: chunk overlap used during splitting. Default: `100`
- `TOP_K`: retriever `k` value. Default: `4`
- `EMBEDDING_MODEL`: Ollama embedding model. Default: `nomic-embed-text`
- `LLM_MODEL`: Ollama chat model. Default: `mistral`
- `PROMPT_PATH`: system prompt file. Default: `./.prompt`

## Notes

- `.prompt` is the source of truth for the system prompt.
- Chat startup can now onboard an empty workspace through PDF upload.
- `ingest.py` now updates the index incrementally and falls back to a full rebuild only when needed.
- If the index is missing or stale, the app will guide you toward `/upload` or `/refresh`.
- Redis is optional. If Redis is unavailable, the app still answers queries without caching.
- Answers now include a deterministic `Sources` block built from retrieved pages.
- Conversations are now persisted locally in `.files/history.sqlite3` and can be reopened from the Chainlit sidebar.

## Tests

Run the unit tests with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Documentation

- Technical reference: `docs/PROJECT_DOCUMENTATION.md`
- Assessment: `docs/ASSESSMENT.md`
- Improvement recommendations: `docs/RECOMMANDATIONS_AMELIORATION.md`
- Phase 1 summary: `docs/PHASE_1_IMPLEMENTATION.md`
- Docusaurus site: `docs-site/`
