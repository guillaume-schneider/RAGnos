# RAGnos

RAGnos est un assistant documentaire local destine a l'information generale des proches de patients hospitalises en reanimation. Il interroge un corpus de documents medicaux valides (PDF et transcriptions pedagogiques) et affiche les sources utilisees dans chaque reponse.

Le projet ne fournit ni diagnostic, ni prescription, ni information sur la situation particuliere d'un patient. Les questions individuelles doivent etre adressees a l'equipe soignante.

## Fonctionnement

Le corpus est indexe localement, puis les passages les plus pertinents sont recuperes pour construire une reponse sourcee. La pile technique repose sur Chainlit, Ollama, Chroma, Redis (optionnel) et SQLite pour l'historique local.

## Prerequis

- Python et `uv`
- Ollama, avec les modeles configures
- Docker Desktop, si le cache Redis est utilise

## Demarrage

1. Demarrer Redis (facultatif) :

```powershell
docker compose up -d redis
```

2. Telecharger les modeles configures par defaut :

```powershell
ollama pull mistral
ollama pull nomic-embed-text
```

3. Placer les documents PDF et les transcriptions JSON dans `tools/extracts/`.

4. Verifier le prompt systeme dans `.prompt`.

5. Construire ou mettre a jour l'index :

```powershell
uv run python ingest.py
```

6. Lancer l'application :

```powershell
uv run chainlit run main.py
```

Les identifiants locaux par defaut sont `admin` / `ragnos`. Ils peuvent etre remplaces avec `CHAINLIT_AUTH_USERNAME` et `CHAINLIT_AUTH_PASSWORD`.

## Commandes dans l'application

- `/upload` : ajouter des documents au corpus ;
- `/refresh` : actualiser l'index apres une modification du corpus ;
- `/status` : afficher l'etat des dependances et de l'index.

## Verification et evaluation

```powershell
uv run python healthcheck.py
uv run python evals.py --dataset evals/regression.jsonl
uv run python benchmark.py --question "Pourquoi parle-t-on de coma artificiel ?" --repetitions 3
```

Les tests unitaires peuvent etre executes avec :

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Configuration

| Variable | Role | Valeur par defaut |
| --- | --- | --- |
| `DOCS_DIR` | Repertoire du corpus | `./tools/extracts` |
| `CHROMA_DIR` | Repertoire de l'index | `./chroma_data` |
| `REDIS_URL` | Connexion Redis | `redis://localhost:6379/0` |
| `OLLAMA_BASE_URL` | Adresse d'Ollama | `http://localhost:11434` |
| `LLM_MODEL` | Modele de generation | `mistral` |
| `EMBEDDING_MODEL` | Modele d'embeddings | `nomic-embed-text` |
| `TOP_K` | Nombre de passages recuperes | `4` |
| `CHUNK_SIZE` | Taille des fragments | `800` |
| `CHUNK_OVERLAP` | Chevauchement des fragments | `100` |
| `CACHE_TTL` | Duree du cache, en secondes | `3600` |
| `PROMPT_PATH` | Fichier de prompt | `./.prompt` |

## Organisation

```text
src/ragnos/      Application et pipeline d'indexation
tools/extracts/  Corpus medical local
evals/            Jeu d'evaluation
tests/            Tests unitaires
docs/             Documentation technique et rapport de projet
docs-site/        Site de documentation
```

Pour la documentation technique et le pipeline, consulter `docs/PROJECT_DOCUMENTATION.md`.
