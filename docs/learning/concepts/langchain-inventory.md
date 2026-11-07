# Concept — Inventaire LangChain : ce qu'on utilise, ce qu'on écarte

_Note de référence (write-once). Inventaire concret des briques LangChain/LangGraph du projet, conforme à l'[ADR 0021](../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md). Complément opérationnel de [rag-orchestration](./rag-orchestration.md). Vérifié dans le code (`grep langchain|langgraph` sur `*/src`)._

> **Principe directeur (ADR 0021)** — On réutilise les composants matures de LangChain **derrière nos ports** ; le **domaine ne dépend jamais de LangChain**, et on ne lui délègue **jamais** les invariants métier : schéma relationnel, **citations** (FR16), **isolation tenant** (NFR10), **versioning** (FR14) restent dans notre SQL.

## ✅ Briques LangChain réellement utilisées

| Brique | Paquet | Où (fichier) | Derrière quel port / rôle |
|---|---|---|---|
| `AzureOpenAIEmbeddings` | `langchain-openai` | `llm/azure.py` | port `EmbeddingClient` — embeddings 512-dim (3.2) |
| `AzureChatOpenAI` + `.with_structured_output()` | `langchain-openai` | `llm/chat_azure.py` | port `ChatClient` — génération en sortie typée (3.5) |
| `langchain_core.documents.Document` | `langchain-core` | `llm/hybrid.py`, `llm/answer.py`, `llm/retriever.py` | monnaie d'échange du read path (citations dans `metadata`) |
| `BaseRetriever` (+ `CallbackManagerForRetrieverRun`) | `langchain-core` | `llm/retriever.py` | `IkipRetriever` expose NOTRE SQL comme retriever LangChain (3.3) |
| `langgraph.graph.StateGraph` / `END` | `langgraph` | `llm/answer.py` | orchestration request-time du grounded-answer (3.5) |

**C'est tout — 5 briques**, toutes dans `packages/common/src/ikip_common/llm/` (+ import **paresseux** dans l'endpoint `apps/api/src/ikip_api/retrieval.py` pour que `create_app()` s'importe sans le groupe `embeddings` dans le CI rapide).

## 🔧 Ce qu'on a implémenté nous-mêmes (pas LangChain)

| Besoin | Décision |
|---|---|
| Fusion RRF | fait maison (~15 lignes) — `EnsembleRetriever` a migré dans un paquet legacy en LangChain 1.x |
| Reranking | notre port `Reranker` + `IdentityReranker` (cross-encoder/Cohere déféré) |
| Recherche lexicale | SQL `tsvector`/GIN — pas `BM25Retriever` (en mémoire, non tenant-aware) |
| Stockage vectoriel | notre table `Embedding` + pgvector — pas `PGVector`/`PGVectorStore` |
| Cache | notre port `Cache` + Redis — pas le cache LangChain |

## 🚫 Briques LangChain volontairement écartées (ADR 0021)

- **`PGVector` / `PGVectorStore`** → casserait la chaîne de citations + l'isolation tenant structurelle (gardé « à évaluer » plus tard).
- **`BM25Retriever`** → en mémoire, pas multi-tenant.
- **`EnsembleRetriever`** → remplacé par notre RRF.
- **Agents / tools / memory LangChain** → pas encore (viendront si un flux agentique le justifie).

## Pourquoi c'est défendable (thèse)

La valeur n'est pas « utiliser LangChain partout » ni « tout réécrire », mais **mettre chaque dépendance là où elle gagne sa place** :
- LangChain **orchestre des étapes LLM** (embeddings, chat structuré, graphe LangGraph) → actif réutilisé.
- Ce qui porte la **sécurité / la gouvernance des données** (requête hybride, isolation tenant, citations, versioning, cache) reste **notre SQL derrière nos ports** → jamais délégué à un framework qui le cacherait.

## Voir aussi
- Décision : [ADR 0021](../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md) · orchestration : [rag-orchestration](./rag-orchestration.md).
- Concepts liés : [embeddings](./embeddings.md) · [retrieval](./retrieval.md) · [hybrid-retrieval](./hybrid-retrieval.md) · [grounded-answers](./grounded-answers.md) · [caching](./caching.md).
