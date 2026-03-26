---
id: architecture
title: Architecture
sidebar_position: 2
---

# Architecture

## High-level design

The project is organized around a single package:

- `src/ragnos/app.py`: Chainlit entrypoint logic and chat-serving runtime
- `src/ragnos/core.py`: shared configuration, ingestion, validation, cache, and model helpers
- `src/ragnos/ingest.py`: command-line entrypoint for building or refreshing the vector index

Compatibility wrappers remain at the repo root:

- `main.py`
- `ingest.py`
- `rag_core.py`

Supporting files:

- `README.md`: operator-focused quickstart
- `chainlit.md`: Chainlit welcome screen content
- `docs/PROJECT_DOCUMENTATION.md`: technical reference
- `tests/test_rag_core.py`: unit tests for the core ingestion and validation logic

## Component responsibilities

## `src/ragnos/app.py`

This module serves the application once an index already exists.

It provides:

- process-scoped runtime state
- Chainlit lifecycle hooks
- Redis-backed answer caching
- retrieval and generation flow
- user-facing startup validation messages

## `src/ragnos/core.py`

This module contains the reusable backend logic shared by the chat runtime and the ingest command.

It provides:

- environment-based configuration loading
- corpus discovery and fingerprinting
- index readiness validation
- PDF loading and chunk splitting
- Chroma build/open helpers
- Ollama model helpers
- prompt creation
- cache namespace and key generation
- ingest workflow helpers

## `src/ragnos/ingest.py`

This module is the manual entrypoint for index management.

It is responsible for:

- parsing CLI arguments
- loading configuration
- checking whether the existing index is already current
- rebuilding the Chroma index when the corpus fingerprint changes
- writing the corpus fingerprint marker
