# Project Assessment

Date: 2026-03-24

Update: the repository has since been reorganized into a `src/ragnos/` package. The architectural observations below still apply where noted, but file-path references to the old flat root layout should now be read as `src/ragnos/app.py`, `src/ragnos/core.py`, and `src/ragnos/ingest.py`, with root-level wrappers preserved for compatibility.

## Overview

This project is a solid local RAG prototype built around Chainlit, Ollama, Chroma, and Redis.
It already includes several good implementation choices:

- Persistent vector storage with Chroma
- A Redis cache layer with graceful fallback
- Document fingerprinting to detect source changes
- Structured JSON logging for startup and query timings
- A simple, readable end-to-end flow in a single file

In its current form, the project works well as a prototype or internal demo. The main constraint is that ingestion, indexing, chat startup, and runtime serving are still tightly coupled. That makes the application easy to understand, but it will slow down and become harder to evolve as document volume or usage increases.

## What Is Good Today

### Clear architecture for a prototype

The application is straightforward to follow. The lifecycle is simple:

1. Load PDFs
2. Split documents into chunks
3. Build or reuse a Chroma index
4. Create a retriever
5. Run a local LLM with retrieved context
6. Cache final answers in Redis

That is the right level of complexity for an initial version.

### Good practical choices

- The Chroma index is persisted instead of recreated every query.
- Redis is optional, and the app continues to work if Redis is unavailable.
- Fingerprinting avoids unnecessary rebuilds when the source documents have not changed.
- Retrieval and generation timings are logged, which gives a starting point for performance tuning.

## Main Weaknesses

### 1. Startup work is too heavy

The largest performance issue is that document loading and chunk creation happen during chat startup. Every new session still parses the PDFs and recreates the chunk list before deciding whether the index can be reused.

This means startup cost grows with document volume even when the vector store itself does not need to be rebuilt.

### 2. Reindexing is all-or-nothing

When documents change, the current approach deletes the existing Chroma data and rebuilds everything from scratch.

That is acceptable for a small demo corpus, but it does not scale. A single changed file should not force a complete re-embedding of all documents.

### 3. Cache invalidation is too weak

The cache key is based only on the normalized question.

That creates a correctness risk:

- If documents change, stale answers can still be served
- If the prompt changes, stale answers can still be served
- If the model changes, stale answers can still be served

The cache should be scoped to the document fingerprint, prompt version, and model name.

### 4. Core logic is still concentrated in one shared module

The repository layout is cleaner now, but `src/ragnos/core.py` still carries most of the shared backend concerns:

- configuration
- fingerprinting
- index validation
- PDF loading
- chunking
- vector store lifecycle
- prompt creation
- caching helpers
- logging helpers

This is better than the previous flat layout, but it is still the main concentration point for future maintenance risk.

### 5. Missing engineering support

There is currently no visible test suite, no benchmark flow, no evaluation dataset, and almost no project documentation.

That means improvements to speed or answer quality will be hard to validate safely.

## Response Time Improvements

### Highest-impact improvements

### Move ingestion out of chat startup

Create a separate ingestion path, for example:

- `ingest.py` for indexing documents manually
- or a background job triggered on upload

Chat startup should only:

- connect to Redis
- open the existing Chroma collection
- initialize the model
- expose the retriever

This will give the biggest improvement to perceived responsiveness.

### Keep shared resources warm

Redis, embeddings, the vector store, and the LLM should be initialized once per process when possible, not once per user chat session.

That reduces repeated initialization cost and makes latency more predictable.

### Make indexing incremental

Replace the full delete-and-rebuild flow with per-document tracking:

- hash each source document
- upsert only changed documents
- remove deleted documents from the index

This is the main scaling improvement for both latency and operational cost.

### Fix cache scope

Use a cache key built from:

- normalized question
- document fingerprint
- model name
- prompt version

This keeps cache hits valid after content or configuration changes.

### Stop streaming cache hits character by character

For cached answers, return the full cached content directly or stream it in larger chunks. Character-by-character replay adds overhead without adding value.

### Secondary performance improvements

- Tune chunk size and overlap with measurement instead of fixed assumptions
- Test `k` values beyond the current default
- Add first-token timing in addition to total generation timing
- Add optional reranking only if retrieval quality needs it
- Precompute document metadata useful for filtering and citations

## General Improvements

### Project structure

The first reorganization step is now done: the runtime code lives under `src/ragnos/`, and the root entrypoints are thin wrappers.

The next structural improvement would be splitting `src/ragnos/core.py` into narrower modules such as:

- `config.py`
- `ingestion.py`
- `retrieval.py`
- `cache.py`
- `prompts.py`

That would make the code easier to test and maintain.

### Prompt management

There is already an external `.prompt` file, but the application currently uses a hardcoded prompt in code.

The project should choose one source of truth for prompts. The cleanest option is to load the prompt from a dedicated file and version it explicitly.

### Better documentation

The repository needs:

- a real `README.md`
- setup instructions
- runtime prerequisites
- model requirements
- Redis usage notes
- document ingestion instructions
- a short architecture summary

### Better UI and product flow

The current Chainlit setup still looks like default scaffolding. The project would benefit from:

- a custom welcome screen
- explicit upload/index workflow
- visible sources and citations in answers
- a clearer status panel for index state, cache state, and model state

### Security and runtime hardening

The current configuration is still prototype-oriented. Before broader usage, review:

- open CORS policy
- permissive file upload settings
- chain-of-thought visibility
- error handling around local services
- limits for file size and accepted document types

## What Could Be Added

### Features with high practical value

- File upload that triggers indexing automatically
- Source citations with file name and page number in every answer
- Conversation memory for follow-up questions
- Metadata filters by document, category, or date
- Admin command to rebuild or refresh the index
- Health endpoint or status command for Redis, Ollama, and Chroma

### Features for quality

- Retrieval evaluation set with expected answers
- Prompt versioning
- Benchmark script for startup and query latency
- Retrieval diagnostics showing which chunks were selected
- Hallucination and refusal regression tests

### Features for scaling

- Multi-collection support
- Background ingestion queue
- User-level document spaces
- Role-based access control if documents become sensitive
- Alternative embedding or reranking strategies

## Recommended Roadmap

### Phase 1: Fast wins

1. Move ingestion out of chat startup
2. Strengthen the cache key
3. Load shared services once per process
4. Add a proper README
5. Replace default Chainlit content

### Phase 2: Stability

1. Split `src/ragnos/core.py` into narrower modules
2. Add tests for prompt behavior, cache correctness, and fingerprint logic
3. Add a benchmark command
4. Add explicit configuration via environment variables

### Phase 3: Product maturity

1. Add upload and indexing flow
2. Add citations in answers
3. Add incremental indexing
4. Add observability and health checks
5. Add evaluation datasets and regression tests

## Conclusion

This project has a good foundation. The current implementation is appropriate for a small local prototype, and the technology choices are reasonable.

The biggest improvement area is not the model itself but the application lifecycle around it. If ingestion is separated from chat serving, indexing becomes incremental, and caching is made safe, the project will feel much faster and will be easier to maintain.

The next best step is to optimize the architecture before adding many new features. That will improve both response time and future development speed.
