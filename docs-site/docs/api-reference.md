---
id: api-reference
title: API Reference
sidebar_position: 4
---

# API Reference

## CLI reference

## `uv run python ingest.py`

Build or refresh the local vector index.

Arguments:

- `--docs-dir`: override the PDF corpus directory
- `--chroma-dir`: override the Chroma persistence directory

The wrapper delegates to `src/ragnos/ingest.py`.

## Environment variables

The runtime reads configuration through `load_config()` in `src/ragnos/core.py`.

## `DOCS_DIR`

- purpose: PDF source directory
- default: `./documents`

## `CHROMA_DIR`

- purpose: persistent Chroma directory
- default: `./chroma_data`

## `REDIS_URL`

- purpose: Redis connection string
- default: `redis://localhost:6379/0`

## `OLLAMA_BASE_URL`

- purpose: Ollama HTTP endpoint
- default: `http://localhost:11434`

## Data structures

## `AppConfig`

Central runtime configuration object.

## `RuntimeValidation`

Result object returned by `validate_runtime_readiness()`.

## `IngestResult`

Result object returned by `ingest_corpus()`.

## `RuntimeState`

Process-scoped runtime container used by `src/ragnos/app.py`.

## Function reference

Core helpers are implemented in `src/ragnos/core.py`.

Key groups:

- configuration and logging
- corpus and index helpers
- ingestion helpers
- model and prompt helpers
- cache and formatting helpers
