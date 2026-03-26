---
id: pipeline
title: Pipeline
sidebar_position: 3
---

# Process and Pipeline

## 1. Ingestion pipeline

The ingestion pipeline is triggered manually through:

```powershell
uv run python ingest.py
```

### Ingestion flow

1. Load configuration from environment variables and optional CLI overrides.
2. Discover all PDF files in `DOCS_DIR`.
3. Compute a corpus fingerprint from each file's name, modification time, and size.
4. Check whether `CHROMA_DIR` already contains a matching index.
5. If the fingerprint matches, return `up_to_date` without rebuilding.
6. If not, load PDFs, split them, create embeddings, and build a fresh Chroma index.
7. Replace the target index directory and write the new `.fingerprint` marker.

## 2. Chat startup pipeline

When Chainlit starts a chat session, `on_chat_start()` in `src/ragnos/app.py` performs a lightweight readiness check.

### Startup flow

1. Validate that `DOCS_DIR` exists.
2. Validate that at least one PDF exists.
3. Recompute the current corpus fingerprint from file stats only.
4. Check that `CHROMA_DIR` exists and contains index artifacts.
5. Check that `.fingerprint` exists and matches the current corpus fingerprint.
6. If validation succeeds, initialize or reuse the process-scoped runtime state.

## 3. Question answering pipeline

The question-answering flow is handled by `on_message()` in `src/ragnos/app.py`.

### Query flow

1. Read the user's message text.
2. Build a cache key from the normalized question and runtime namespace.
3. If Redis is available, check for a cached answer.
4. On cache miss, retrieve the top `k` chunks from Chroma.
5. Format the retrieved chunks into a prompt context.
6. Run the local Ollama chat model in streaming mode.
7. Store the final answer in Redis and log timings.

## 4. Failure modes

The main expected failure modes are:

- missing PDF directory
- empty corpus
- missing Chroma index
- empty or incomplete Chroma index
- stale fingerprint after corpus changes
- unavailable Redis
- unavailable Ollama or invalid local model setup
