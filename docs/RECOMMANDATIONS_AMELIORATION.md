# Recommandations D'Amelioration

Date: 2026-03-26

## Contexte

Cette note synthétise l'analyse du repository `RAGnos` apres revue de la structure du projet, des modules principaux, de l'outillage local, de la documentation et de la suite de tests.

Le projet est deja bien avance pour un prototype RAG local:

- architecture modulaire sous `src/ragnos/`
- ingestion incrementale par document
- wrappers CLI simples
- historique local via Chainlit + SQLite
- benchmark, healthcheck et evals deja presents
- suite de tests unitaires verte

Verification effectuee localement:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Resultat observe: 28 tests executes, 28 reussis.

## Etat Actuel

### Points forts

- La separation des responsabilites est nette entre `config.py`, `documents.py`, `indexing.py`, `runtime.py`, `health.py`, `evals.py` et `app.py`.
- L'ingestion incrementale evite deja le rebuild complet dans les cas simples.
- Le cache est mieux scope qu'un simple cache par question grace au namespace derive du fingerprint documentaire et de la config runtime.
- Les commandes operateur `/upload`, `/refresh` et `/status` rendent le prototype exploitable sans scripts annexes.
- La persistence locale des threads Chainlit apporte une vraie valeur pratique pour un usage local.
- La couverture unitaire est bonne pour un prototype de cette taille.

### Limites actuelles

- La configuration depend uniquement des variables d'environnement deja exportees dans le shell.
- L'historique de conversation est persiste a la fois dans SQLite et dans des transcripts JSON.
- Le pipeline de requete n'a pas encore de garde-fou fort quand la retrieval est vide ou faible.
- L'outillage projet reste minimal: pas de lint, pas de typecheck, pas de CI, packaging incomplet.
- Le durcissement securite reste tres prototype-oriented.

## Priorites D'Amelioration

### 1. Fiabiliser la configuration

Aujourd'hui, `load_config()` lit les valeurs via `os.getenv()` et les arguments explicites. Cela signifie que le fichier `.env` du repository n'est pas une vraie source de verite a lui seul si l'environnement n'a pas ete charge avant execution.

Impact:

- comportements differents selon le terminal utilise
- frustration operateur quand `.env` existe mais n'est pas pris en compte
- scripts locaux moins deterministes

Recommendation:

- adopter `python-dotenv` ou `pydantic-settings`
- charger explicitement `.env` au demarrage des CLI et de Chainlit
- documenter clairement la precedence:
  1. arguments explicites
  2. variables d'environnement
  3. `.env`
  4. defaults code

Gain attendu:

- configuration reproductible
- setup local plus robuste
- moins d'erreurs de demarrage

### 2. Supprimer la double persistence des conversations

Le projet persiste deja les threads via `LocalSQLiteDataLayer`, ce qui est coherent avec l'integration Chainlit. En parallele, `app.py` maintient aussi des transcripts JSON dans `.files/transcripts/`.

Observation importante:

- la logique de replay de transcript existe
- mais les appels actuels a `_initialize_session()` passent `restore_transcript=False` et `replay_messages=False`
- une partie de cette complexite semble donc inactive ou redondante

Recommendation:

- choisir SQLite comme source unique de verite pour l'historique
- supprimer les transcripts JSON si leur usage n'est pas justifie
- conserver uniquement une logique de resume basee sur le data layer Chainlit

Gain attendu:

- moins de code de synchronisation
- moins de risques d'incoherence entre deux stockages
- maintenance plus simple

### 3. Durcir le pipeline RAG au moment de la requete

`run_query()` execute la retrieval puis construit le prompt avec les chunks recuperes. La reponse est ensuite toujours deleguee au LLM, meme si aucun document pertinent n'est reellement disponible.

Risques:

- reponses peu fiables en cas de retrieval vide
- refus implicites dependants du prompt uniquement
- difficultes a mesurer la qualite reelle de la retrieval

Recommendation:

- ajouter un refus explicite si aucun document n'est trouve
- ajouter un score threshold ou une logique de filtration minimale
- tester une retrieval MMR ou un reranker seulement si le besoin qualite est confirme
- journaliser plus explicitement les cas `0 chunk` ou retrieval faible

Gain attendu:

- baisse du risque d'hallucination
- comportement plus previsible
- base plus saine pour les evals qualite

### 4. Fermer proprement les ressources Chroma dans le healthcheck

`build_health_report()` ouvre le vector store pour verifier Chroma, mais ne reutilise pas le helper de fermeture deja defini dans `indexing.py`.

Risques:

- handles fichiers gardes ouverts, surtout sous Windows
- verrous temporaires pendant certains tests ou rebuilds
- comportement local plus fragile

Recommendation:

- fermer explicitement le vector store ouvert par le healthcheck
- reutiliser `close_vectorstore()`
- ajouter un test de non-regression si necessaire

Gain attendu:

- meilleur comportement sous Windows
- moins d'effets de bord sur les operations d'indexation

### 5. Industrialiser un minimum le data layer SQLite

Le data layer local est utile et deja assez complet, mais la base ne prevoit pas encore:

- index SQL sur les tables les plus sollicitees
- mecanisme de migration de schema
- verification d'integrite ou maintenance simple

Recommendation:

- ajouter des index sur:
  - `threads.userId`
  - `steps.threadId`
  - `elements.threadId`
  - `feedbacks.forId`
- introduire une version de schema
- preparer un mecanisme simple de migration

Gain attendu:

- meilleure tenue a la charge locale
- evolution du schema plus sure
- navigation historique plus rapide

### 6. Completer l'outillage projet

Le `pyproject.toml` est encore minimal et l'experience developpeur reste inegale.

Manques principaux:

- `description` placeholder
- pas de `project.scripts`
- pas de lint
- pas de typecheck
- pas de CI
- wrappers racine encore bases sur injection manuelle de `sys.path`

Recommendation:

- ajouter `ruff`
- ajouter `mypy` ou `pyright`
- ajouter une CI GitHub Actions pour tests + lint
- definir des scripts de console propres
- nettoyer progressivement les wrappers de compatibilite quand ils ne seront plus necessaires

Gain attendu:

- meilleure confiance dans les changements
- standardisation du workflow de dev
- repository plus presentable

## Ajouts Utiles A Court Et Moyen Terme

### Gestion du corpus

Le produit gagnerait en exploitabilite avec des commandes ou vues supplementaires:

- `/list` pour lister les PDF indexes
- `/delete` pour retirer un document
- `/reindex <document>` pour cibler un fichier
- statistiques par document: pages, chunks, date d'indexation
- visualisation simple des sources disponibles

### Evals de meilleure qualite

Le runner d'evals actuel est pertinent pour un seed dataset, mais reste tres base sur des assertions de sous-chaines.

Ajouts recommandes:

- hit rate sur les sources attendues
- precision sur les citations
- cas negatifs et refus attendus
- budgets de latence maximum
- jeux de test de regression metier plus representatifs

### Tests d'integration opt-in

La suite actuelle est bonne, mais beaucoup de tests mockent les dependances lourdes, ce qui est normal pour de l'unitaire.

Il manque encore:

- tests reels avec Ollama
- tests reels avec Redis
- tests reels avec Chroma
- smoke test applicatif sur le cycle ingest -> query -> eval

Recommendation:

- separer clairement `unit` et `integration`
- activer les tests d'integration uniquement si les dependances locales sont disponibles

### Durcissement securite

Pour un usage strictement local, la configuration est acceptable. Pour une diffusion plus large, il faudra corriger:

- identifiants par defaut `admin` / `ragnos`
- `allow_origins = ["*"]`
- affichage du CoT en `full`
- politique d'upload tres permissive

## Roadmap Proposee

### Quick Wins

1. Charger explicitement `.env`
2. Supprimer la persistence JSON redondante des transcripts
3. Fermer proprement Chroma dans le healthcheck
4. Ajouter des index SQL a SQLite
5. Ajouter lint + CI

### Moyen terme

1. Ajouter les garde-fous retrieval dans `run_query()`
2. Enrichir les evals avec des metriques plus fiables
3. Ajouter des commandes de gestion du corpus
4. Remplacer les wrappers `sys.path` par des entrypoints propres

### Long terme

1. Ajouter une vraie suite d'integration locale
2. Introduire versionnement et migrations de schema SQLite
3. Ajouter des filtres metadata et outils de diagnostic retrieval
4. Durcir la securite si le projet sort du cadre purement local

## Conclusion

Le repository est deja au-dessus du niveau habituel d'un simple prototype RAG local. L'architecture est lisible, la modularisation est reelle et la base de tests donne de la confiance.

Les prochains gains les plus utiles ne sont pas dans un changement radical de stack, mais dans:

- la robustesse de la configuration
- la simplification de la persistence de conversation
- le durcissement du comportement RAG
- la qualite de l'outillage projet

Si ces points sont traites, le projet passera d'un bon prototype local a une base serieuse pour iteration produit.
