workspace "RAGnos - Architecture C4" "Architecture C4 du prototype local RAGnos pour assistant juridique RAG." {

  model {
    consultant = person "Consultant juridique" "Pose des questions en langage naturel sur des jurisprudences, codes de loi et documents internes."
    operator = person "Opérateur interne" "Prépare le corpus PDF, lance l'ingestion, vérifie l'état du système et maintient le prototype."

    ragnos = softwareSystem "RAGnos" "Assistant conversationnel RAG local qui répond exclusivement à partir d'un corpus documentaire PDF indexé." {
      chainlitUi = container "Interface Chainlit" "Interface web de chat, authentification locale, historique et commandes /upload, /refresh, /status." "Chainlit / Python"

      appRuntime = container "Application RAGnos" "Runtime applicatif : configuration, validation de readiness, orchestration du chat, ingestion, retrieval, génération, citations, healthcheck, benchmark et evals." "Python 3.11" {
        configComponent = component "Config" "Charge les valeurs par défaut, variables d'environnement, chemins, modèles et prompt." "src/ragnos/config.py"
        appComponent = component "Chainlit App" "Gère le cycle de chat, les commandes opérateur, l'upload PDF, le refresh et le status." "src/ragnos/app.py"
        runtimeComponent = component "Runtime RAG" "Construit l'état partagé et exécute les requêtes avec cache, retrieval, génération et citations." "src/ragnos/runtime.py"
        documentsComponent = component "Documents" "Découvre les PDF, calcule le fingerprint, charge les pages, découpe et formate les chunks." "src/ragnos/documents.py"
        indexingComponent = component "Indexing" "Valide la readiness, crée les embeddings, ouvre Chroma et exécute l'ingestion incrémentale." "src/ragnos/indexing.py"
        catalogComponent = component "Catalog" "Lit et écrit manifest.json, suit les documents indexés, hash, pages et chunk ids." "src/ragnos/catalog.py"
        cacheComponent = component "Cache" "Construit le namespace et les clés Redis pour éviter les réponses obsolètes." "src/ragnos/cache.py"
        promptComponent = component "Prompts" "Construit le template de prompt à partir du prompt système." "src/ragnos/prompts.py"
        healthComponent = component "Healthcheck" "Vérifie prompt, corpus, index, Chroma, Redis et Ollama." "src/ragnos/health.py + healthcheck.py"
        evalComponent = component "Evals" "Exécute les tests JSONL contre la pile locale RAG." "src/ragnos/evals.py"
        benchmarkComponent = component "Benchmark" "Mesure startup, retrieval, first token, génération, total et chunks utilisés." "src/ragnos/benchmark.py"
      }

      chromaStore = container "Index vectoriel Chroma" "Stockage persistant des embeddings et métadonnées de chunks issus des PDF." "ChromaDB" {
        tags "Database"
      }

      redisCache = container "Cache Redis" "Cache optionnel des réponses rendues, namespacé par fingerprint documentaire, prompt, modèle et paramètres RAG." "Redis" {
        tags "Database"
      }

      sqliteHistory = container "Historique Chainlit SQLite" "Persistance locale des conversations et reprise des threads depuis la barre latérale Chainlit." "SQLite" {
        tags "Database"
      }

      documentsDir = container "Corpus PDF local" "Répertoire documents/ contenant les PDF juridiques fournis par l'utilisateur." "File system" {
        tags "Folder"
      }

      chromaFiles = container "État d'index" "Répertoire chroma_data/ contenant l'index, .fingerprint et manifest.json." "File system" {
        tags "Folder"
      }

      promptFile = container "Prompt système" "Fichier .prompt imposant l'usage exclusif du contexte fourni et le refus si l'information est absente." "Text file" {
        tags "File"
      }

      evalDataset = container "Jeu d'évaluation" "Fichier evals/regression.jsonl utilisé pour les régressions locales." "JSONL" {
        tags "File"
      }

    }

    ollama = softwareSystem "Ollama" "Runtime local pour le modèle de génération mistral et le modèle d'embeddings nomic-embed-text." "Local service"

    consultant -> chainlitUi "Pose des questions et consulte les réponses sourcées" "HTTPS local / navigateur"
    operator -> chainlitUi "Upload des PDF et utilise les commandes opérateur" "HTTPS local / navigateur"
    operator -> appRuntime "Lance les CLI ingest, healthcheck, benchmark et evals" "PowerShell / uv"

    chainlitUi -> appRuntime "Transmet messages, uploads et commandes"
    chainlitUi -> appComponent "Transmet messages, uploads et commandes au composant Chainlit"
    chainlitUi -> consultant "Affiche les réponses et sources"
    chainlitUi -> sqliteHistory "Persiste et recharge les conversations"

    appRuntime -> promptFile "Charge le prompt système"
    appRuntime -> documentsDir "Lit et écrit les PDF uploadés"
    appRuntime -> chromaFiles "Lit l'empreinte et le manifeste d'index"
    appRuntime -> chromaStore "Recherche les chunks pertinents et met à jour les embeddings"
    appRuntime -> redisCache "Lit et écrit les réponses cachées"
    appRuntime -> ollama "Demande embeddings et génération de réponse"
    appRuntime -> evalDataset "Lit le dataset d'évaluation"

    appComponent -> configComponent "Charge et valide la configuration"
    appComponent -> indexingComponent "Valide la readiness et déclenche l'ingestion après upload ou refresh"
    appComponent -> runtimeComponent "Construit ou réutilise l'état runtime et exécute les questions"
    appComponent -> healthComponent "Affiche le status opérateur"
    appComponent -> documentsDir "Persiste les PDF uploadés"
    appComponent -> chainlitUi "Confirme les changements de corpus et diffuse les réponses"

    runtimeComponent -> cacheComponent "Construit les clés de cache"
    runtimeComponent -> promptComponent "Construit le prompt final"
    runtimeComponent -> documentsComponent "Formate les chunks récupérés"
    runtimeComponent -> indexingComponent "Ouvre Chroma, embeddings et LLM"
    runtimeComponent -> redisCache "Récupère ou stocke une réponse"
    runtimeComponent -> chromaStore "Récupère les chunks top-k"
    runtimeComponent -> ollama "Génère la réponse streamée"
    runtimeComponent -> chainlitUi "Stream la réponse sourcée"

    indexingComponent -> documentsComponent "Liste, charge, découpe et annote les PDF"
    indexingComponent -> catalogComponent "Compare le manifeste avec l'état courant du corpus"
    indexingComponent -> chromaStore "Upsert ou delete les chunks"
    indexingComponent -> chromaFiles "Écrit manifest.json et .fingerprint"
    indexingComponent -> ollama "Calcule les embeddings"

    healthComponent -> promptFile "Vérifie la validité du prompt"
    healthComponent -> documentsDir "Vérifie la présence du corpus"
    healthComponent -> chromaStore "Vérifie l'ouverture de Chroma"
    healthComponent -> redisCache "Teste la connectivité"
    healthComponent -> ollama "Teste la disponibilité"

    evalComponent -> runtimeComponent "Exécute les questions de régression"
    benchmarkComponent -> runtimeComponent "Mesure les temps de réponse"
  }

  views {
    systemContext ragnos "SystemContext" {
      include *
      autolayout lr
      title "C4 niveau 1 - Contexte système"
      description "RAGnos est un assistant local utilisé par un consultant juridique et maintenu par un opérateur interne."
    }

    container ragnos "Containers" {
      include *
      autolayout lr
      title "C4 niveau 2 - Conteneurs"
      description "Vue des briques d'exécution, de stockage et de fichiers utilisées par le prototype RAG local."
    }

    component appRuntime "Components" {
      include *
      autolayout lr
      title "C4 niveau 3 - Composants applicatifs Python"
      description "Vue des modules principaux sous src/ragnos/ et de leurs dépendances."
    }

    dynamic appRuntime "QueryFlow" "Flux dynamique - Question RAG sourcée" {
      consultant -> chainlitUi "1. Pose une question juridique"
      chainlitUi -> appComponent "2. Transmet le message"
      appComponent -> runtimeComponent "3. Exécute run_query"
      runtimeComponent -> cacheComponent "4. Calcule la clé de cache"
      runtimeComponent -> redisCache "5. Cherche une réponse cachée"
      runtimeComponent -> chromaStore "6. Récupère les chunks top-k si cache miss"
      runtimeComponent -> promptComponent "7. Construit le prompt avec le contexte"
      runtimeComponent -> ollama "8. Génère la réponse"
      runtimeComponent -> redisCache "9. Cache la réponse rendue avec le bloc Sources"
      runtimeComponent -> chainlitUi "10. Stream la réponse sourcée"
      chainlitUi -> consultant "11. Affiche réponse et sources"
      autolayout lr
    }

    dynamic appRuntime "IngestFlow" "Flux dynamique - Ingestion incrémentale PDF" {
      operator -> chainlitUi "1. Upload PDF ou demande /refresh"
      chainlitUi -> appComponent "2. Transmet les fichiers ou la commande"
      appComponent -> documentsDir "3. Persiste les PDF uploadés"
      appComponent -> indexingComponent "4. Lance ingest_corpus"
      indexingComponent -> documentsComponent "5. Liste, hash, charge et découpe les PDF"
      indexingComponent -> catalogComponent "6. Compare manifest.json et documents courants"
      indexingComponent -> ollama "7. Calcule les embeddings des chunks nouveaux ou modifiés"
      indexingComponent -> chromaStore "8. Upsert les nouveaux chunks et supprime les chunks obsolètes"
      indexingComponent -> chromaFiles "9. Écrit manifest.json et .fingerprint"
      appComponent -> runtimeComponent "10. Invalide puis reconstruit l'état runtime"
      appComponent -> chainlitUi "11. Confirme l'état du corpus"
      autolayout lr
    }

    styles {
      element "Person" {
        shape Person
        background #084c61
        color #ffffff
      }

      element "Software System" {
        background #177e89
        color #ffffff
      }

      element "Container" {
        background #2d6a4f
        color #ffffff
      }

      element "Component" {
        background #40916c
        color #ffffff
      }

      element "Database" {
        shape Cylinder
        background #6c757d
        color #ffffff
      }

      element "Folder" {
        shape Folder
        background #8d99ae
        color #ffffff
      }

      element "File" {
        shape Box
        background #adb5bd
        color #000000
      }
    }
  }
}
