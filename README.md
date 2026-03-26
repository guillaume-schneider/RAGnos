# RAGnos

Local RAG prototype built with Chainlit, Ollama, Chroma, and Redis.

The runtime code now lives under `src/ragnos/`. The root-level `main.py`, `ingest.py`, and `rag_core.py` files are compatibility wrappers so the existing commands still work.

## Repository layout

```text
src/ragnos/
  app.py        Chainlit runtime
  core.py       Shared RAG, ingest, cache, and config logic
  ingest.py     CLI entrypoint for index builds
docs/           Project documentation
docs-site/      Docusaurus documentation site
documents/      Source PDF corpus
tests/          Unit tests
main.py         Chainlit wrapper entrypoint
ingest.py       CLI wrapper entrypoint
rag_core.py     Compatibility wrapper for legacy imports
```

## Local workflow

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

4. Build or refresh the vector index:

```powershell
uv run python ingest.py
```

5. Start the Chainlit app:

```powershell
uv run chainlit run main.py
```

## Environment variables

- `DOCS_DIR`: PDF directory. Default: `./documents`
- `CHROMA_DIR`: persisted Chroma directory. Default: `./chroma_data`
- `REDIS_URL`: Redis connection string. Default: `redis://localhost:6379/0`
- `OLLAMA_BASE_URL`: Ollama base URL. Default: `http://localhost:11434`

## Notes

- Chat startup does not rebuild the index.
- If the index is missing or stale, the app will ask you to run `uv run python ingest.py`.
- Redis is optional. If Redis is unavailable, the app still answers queries without caching.

## Tests

Run the unit tests with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Documentation

- Technical reference: `docs/PROJECT_DOCUMENTATION.md`
- Assessment: `docs/ASSESSMENT.md`
- Docusaurus site: `docs-site/`
