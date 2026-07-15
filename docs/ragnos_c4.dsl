workspace "RAGnos - Architecture C4" "Architecture C4 du prototype local RAGnos pour assistant RAG medical en reanimation." {

  model {
    closeRelative = person "Proche de patient" "Pose des questions generales sur la reanimation, les soins, les machines et le sejour hospitalier."
    operator = person "Operateur interne" "Prepare le corpus medical, lance l'ingestion, verifie l'etat du systeme et maintient le prototype."

    ragnos = softwareSystem "RAGnos" "Assistant conversationnel RAG local qui repond exclusivement a partir d'un corpus medical indexe." {
      chainlitUi = container "Interface Chainlit" "Interface web de chat, authentification locale, historique et commandes /upload, /refresh, /status." "Chainlit / Python"

      appRuntime = container "Application RAGnos" "Runtime applicatif : configuration, validation de readiness, orchestration du chat, ingestion, retrieval, generation, citations, healthcheck, benchmark et evals." "Python 3.11" {
        configComponent = component "Config" "Charge les valeurs par defaut, variables d'environnement, chemins, modeles et prompt." "src/ragnos/config.py"
        appComponent = component "Chainlit App" "Gere le cycle de chat, les commandes operateur, l'upload PDF/JSON, le refresh et le status." "src/ragnos/app.py"
        runtimeComponent = component "Runtime RAG" "Construit l'etat partage et execute les requetes avec cache, retrieval, generation et citations." "src/ragnos/runtime.py"
        documentsComponent = component "Documents" "Decouvre les PDF et JSON, calcule le fingerprint, charge les pages ou transcripts, decoupe et formate les chunks." "src/ragnos/documents.py"
        indexingComponent = component "Indexing" "Valide la readiness, cree les embeddings, ouvre Chroma et execute l'ingestion incrementale." "src/ragnos/indexing.py"
        catalogComponent = component "Catalog" "Lit et ecrit manifest.json, suit les documents indexes, hash, unites documentaires et chunk ids." "src/ragnos/catalog.py"
        cacheComponent = component "Cache" "Construit le namespace et les cles Redis pour eviter les reponses obsoletes." "src/ragnos/cache.py"
        promptComponent = component "Prompts" "Construit le template a partir du prompt medical limitant diagnostic, prescription et hors-corpus." "src/ragnos/prompts.py"
        healthComponent = component "Healthcheck" "Verifie prompt, corpus, index, Chroma, Redis et Ollama." "src/ragnos/health.py + healthcheck.py"
        evalComponent = component "Evals" "Execute les tests JSONL contre la pile locale RAG." "src/ragnos/evals.py"
        benchmarkComponent = component "Benchmark" "Mesure startup, retrieval, first token, generation, total et chunks utilises." "src/ragnos/benchmark.py"
      }

      chromaStore = container "Index vectoriel Chroma" "Stockage persistant des embeddings et metadonnees de chunks issus des documents PDF et JSON." "ChromaDB" {
        tags "Database"
      }

      redisCache = container "Cache Redis" "Cache optionnel des reponses rendues, namespace par fingerprint documentaire, prompt, modele et parametres RAG." "Redis" {
        tags "Database"
      }

      sqliteHistory = container "Historique Chainlit SQLite" "Persistance locale des conversations et reprise des threads depuis la barre laterale Chainlit." "SQLite" {
        tags "Database"
      }

      documentsDir = container "Corpus medical local" "Repertoire local contenant les PDF medicaux et transcripts JSON valides pour la reanimation." "File system" {
        tags "Folder"
      }

      chromaFiles = container "Etat d'index" "Repertoire chroma_data/ contenant l'index, .fingerprint et manifest.json." "File system" {
        tags "Folder"
      }

      promptFile = container "Prompt systeme" "Fichier .prompt imposant l'usage exclusif du contexte, le refus hors corpus et l'absence de diagnostic ou prescription." "Text file" {
        tags "File"
      }

      evalDataset = container "Jeu d'evaluation" "Fichier evals/regression.jsonl utilise pour les regressions locales." "JSONL" {
        tags "File"
      }
    }

    ollama = softwareSystem "Ollama" "Runtime local pour le modele de generation mistral et le modele d'embeddings nomic-embed-text." "Local service"

    closeRelative -> chainlitUi "Pose une question generale et consulte les reponses sourcees" "HTTPS local / navigateur"
    operator -> chainlitUi "Upload des PDF/JSON et utilise les commandes operateur" "HTTPS local / navigateur"
    operator -> appRuntime "Lance les CLI ingest, healthcheck, benchmark et evals" "PowerShell / uv"

    chainlitUi -> appRuntime "Transmet messages, uploads et commandes"
    chainlitUi -> appComponent "Transmet messages, uploads et commandes au composant Chainlit"
    chainlitUi -> closeRelative "Affiche les reponses, sources et rappels de prudence"
    chainlitUi -> sqliteHistory "Persiste et recharge les conversations"

    appRuntime -> promptFile "Charge le prompt systeme"
    appRuntime -> documentsDir "Lit et ecrit les documents uploades"
    appRuntime -> chromaFiles "Lit l'empreinte et le manifeste d'index"
    appRuntime -> chromaStore "Recherche les chunks pertinents et met a jour les embeddings"
    appRuntime -> redisCache "Lit et ecrit les reponses cachees"
    appRuntime -> ollama "Demande embeddings et generation de reponse"
    appRuntime -> evalDataset "Lit le dataset d'evaluation"

    appComponent -> configComponent "Charge et valide la configuration"
    appComponent -> indexingComponent "Valide la readiness et declenche l'ingestion apres upload ou refresh"
    appComponent -> runtimeComponent "Construit ou reutilise l'etat runtime et execute les questions"
    appComponent -> healthComponent "Affiche le status operateur"
    appComponent -> documentsDir "Persiste les documents uploades"
    appComponent -> chainlitUi "Confirme les changements de corpus et diffuse les reponses"

    runtimeComponent -> cacheComponent "Construit les cles de cache"
    runtimeComponent -> promptComponent "Construit le prompt final"
    runtimeComponent -> documentsComponent "Formate les chunks recuperes"
    runtimeComponent -> indexingComponent "Ouvre Chroma, embeddings et LLM"
    runtimeComponent -> redisCache "Recupere ou stocke une reponse"
    runtimeComponent -> chromaStore "Recupere les chunks top-k"
    runtimeComponent -> ollama "Genere la reponse streamee"
    runtimeComponent -> chainlitUi "Stream la reponse sourcee"

    indexingComponent -> documentsComponent "Liste, charge, decoupe et annote les PDF/JSON"
    indexingComponent -> catalogComponent "Compare le manifeste avec l'etat courant du corpus"
    indexingComponent -> chromaStore "Upsert ou delete les chunks"
    indexingComponent -> chromaFiles "Ecrit manifest.json et .fingerprint"
    indexingComponent -> ollama "Calcule les embeddings"

    healthComponent -> promptFile "Verifie la validite du prompt"
    healthComponent -> documentsDir "Verifie la presence du corpus"
    healthComponent -> chromaStore "Verifie l'ouverture de Chroma"
    healthComponent -> redisCache "Teste la connectivite"
    healthComponent -> ollama "Teste la disponibilite"

    evalComponent -> runtimeComponent "Execute les questions de regression"
    benchmarkComponent -> runtimeComponent "Mesure les temps de reponse"
  }

  views {
    systemContext ragnos "SystemContext" {
      include *
      autolayout lr
      title "C4 niveau 1 - Contexte systeme"
      description "RAGnos est un assistant local utilise par les proches de patients et maintenu par un operateur interne."
    }

    container ragnos "Containers" {
      include *
      autolayout lr
      title "C4 niveau 2 - Conteneurs"
      description "Vue des briques d'execution, de stockage et de fichiers utilisees par le prototype RAG local."
    }

    component appRuntime "Components" {
      include *
      autolayout lr
      title "C4 niveau 3 - Composants applicatifs Python"
      description "Vue des modules principaux sous src/ragnos/ et de leurs dependances."
    }

    dynamic appRuntime "QueryFlow" "Flux dynamique - Question RAG sourcee" {
      closeRelative -> chainlitUi "1. Pose une question generale sur la reanimation"
      chainlitUi -> appComponent "2. Transmet le message"
      appComponent -> runtimeComponent "3. Execute run_query"
      runtimeComponent -> cacheComponent "4. Calcule la cle de cache"
      runtimeComponent -> redisCache "5. Cherche une reponse cachee"
      runtimeComponent -> chromaStore "6. Recupere les chunks top-k si cache miss"
      runtimeComponent -> promptComponent "7. Construit le prompt avec le contexte"
      runtimeComponent -> ollama "8. Genere la reponse"
      runtimeComponent -> redisCache "9. Cache la reponse rendue avec le bloc Sources"
      runtimeComponent -> chainlitUi "10. Stream la reponse sourcee"
      chainlitUi -> closeRelative "11. Affiche reponse, sources et limites"
      autolayout lr
    }

    dynamic appRuntime "IngestFlow" "Flux dynamique - Ingestion incrementale PDF/JSON" {
      operator -> chainlitUi "1. Upload PDF/JSON ou demande /refresh"
      chainlitUi -> appComponent "2. Transmet les fichiers ou la commande"
      appComponent -> documentsDir "3. Persiste les documents uploades"
      appComponent -> indexingComponent "4. Lance ingest_corpus"
      indexingComponent -> documentsComponent "5. Liste, hash, charge et decoupe les PDF/JSON"
      indexingComponent -> catalogComponent "6. Compare manifest.json et documents courants"
      indexingComponent -> ollama "7. Calcule les embeddings des chunks nouveaux ou modifies"
      indexingComponent -> chromaStore "8. Upsert les nouveaux chunks et supprime les chunks obsoletes"
      indexingComponent -> chromaFiles "9. Ecrit manifest.json et .fingerprint"
      appComponent -> runtimeComponent "10. Invalide puis reconstruit l'etat runtime"
      appComponent -> chainlitUi "11. Confirme l'etat du corpus"
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
