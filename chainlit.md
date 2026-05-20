# RAGnos

This assistant answers questions only from the locally indexed PDF corpus.

## Before you start

1. Put PDF files in `documents/`
2. Define the system prompt in `.prompt`
3. Start the app with `uv run chainlit run main.py`

The app now uses a local login so conversation history can be persisted and reopened from the left sidebar.

Default local credentials:

- username: `admin`
- password: `ragnos`

## Runtime requirements

- Ollama must be running
- The `mistral` and `nomic-embed-text` models must be available
- Redis is optional, but it improves repeated-answer latency

## Useful commands

Rebuild the index:

```powershell
uv run python ingest.py
```

Run a healthcheck:

```powershell
uv run python healthcheck.py
```

Run the local benchmark:

```powershell
uv run python benchmark.py --question "Votre question" --repetitions 3
```

Run the seed eval suite:

```powershell
uv run python evals.py --dataset evals/regression.jsonl
```

## When documents or prompts change

This app supports in-chat management commands:

- `/upload`
- `/refresh`
- `/status`

You can still refresh from the terminal with:

```powershell
uv run python ingest.py
```

Answers include a `Sources` block built from the retrieved pages.

Conversations are stored locally and can be resumed from the sidebar history after login.
