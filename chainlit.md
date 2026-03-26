# RAGnos

This assistant answers questions only from the locally indexed PDF corpus.

## Before you start

1. Put PDF files in `documents/`
2. Run `uv run python ingest.py`
3. Start the app with `uv run chainlit run main.py`

## Runtime requirements

- Ollama must be running
- The `mistral` and `nomic-embed-text` models must be available
- Redis is optional, but it improves repeated-answer latency

## When documents change

This app does not rebuild the index during chat startup.

If you add, remove, or replace PDF files, run:

```powershell
uv run python ingest.py
```

Then start a new chat.
