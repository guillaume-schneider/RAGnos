---
id: intro
title: Introduction
sidebar_position: 1
---

# RAGnos

RAGnos is a local Retrieval-Augmented Generation application built around:

- Chainlit for the chat UI and lifecycle
- Ollama for local embeddings and generation
- Chroma for persistent vector storage
- Redis for response caching

The current codebase is package-first. The runtime implementation lives in `src/ragnos/`, while the root-level entrypoint files are kept as compatibility wrappers.

## Main modules

- `src/ragnos/app.py`: Chainlit runtime and chat-serving logic
- `src/ragnos/core.py`: shared config, ingestion, validation, cache, and model helpers
- `src/ragnos/ingest.py`: CLI entrypoint for building or refreshing the vector index

## Quick commands

```powershell
uv run python ingest.py
uv run chainlit run main.py
```
