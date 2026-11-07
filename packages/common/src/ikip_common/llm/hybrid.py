"""Hybrid retrieval: fuse lexical + vector, rerank, abstain (Story 3.4, ADR 0021).

Composes the two tenant-scoped `IkipRetriever` arms in LangChain `Document` space:
  1. **Fuse** both ranked lists with Reciprocal Rank Fusion (RRF) — rank-based, so
     BM25 `ts_rank` and cosine scores need no normalization. (RRF is exactly what
     LangChain's EnsembleRetriever does; it moved to a legacy compat package in
     LangChain 1.x, so we implement the ~15-line algorithm here, keeping full control
     of citations + thresholds.)
  2. **Rerank** via a pluggable `Reranker` port (`IdentityReranker` default; a
     cross-encoder adapter can slot in later without touching callers — ADR 0021).
  3. **Abstain** ("insufficient evidence") when nothing survives the per-arm score
     floors + filters (AC4).

Citations ride in each Document's `metadata` (set by `IkipRetriever`) and are
preserved through fusion + rerank (FR16). Filters/tenant scoping stay in our SQL.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from langchain_core.documents import Document
from sqlalchemy.orm import Session

from ikip_common.db.retrieval import DEFAULT_LIMIT, RetrievalFilters
from ikip_common.llm.base import EmbeddingClient
from ikip_common.llm.retriever import IkipRetriever

RRF_K = 60  # standard RRF dampening constant


@runtime_checkable
class Reranker(Protocol):
    """Reorders candidate documents by relevance to the query (request-time)."""

    def rerank(
        self, query: str, documents: Sequence[Document], *, top_k: int | None = None
    ) -> list[Document]: ...


class IdentityReranker:
    """No-op reranker: keeps RRF order, optionally truncating to top_k. Default seam
    where a cross-encoder / Cohere reranker can be dropped in later (ADR 0021)."""

    def rerank(
        self, query: str, documents: Sequence[Document], *, top_k: int | None = None
    ) -> list[Document]:
        docs = list(documents)
        return docs[:top_k] if top_k else docs


@dataclass
class RetrievalOutcome:
    """Result of a hybrid retrieval. `abstained` is the "insufficient evidence" path (AC4)."""

    documents: list[Document]
    abstained: bool
    reason: str | None = None


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[Document]], *, k: int = RRF_K
) -> list[Document]:
    """Fuse ranked Document lists by RRF: score(d) = Σ 1/(k + rank_i(d)). Dedupe by
    `chunk_id` metadata; the surviving Document keeps the best per-arm score and gains
    `metadata['rrf_score']`. Returns documents sorted by fused score desc."""
    fused: dict[str, Document] = {}
    scores: dict[str, float] = {}
    for docs in ranked_lists:
        for rank, doc in enumerate(docs):
            key = str(doc.metadata.get("chunk_id"))
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)  # rank is 0-based
            if key not in fused:
                fused[key] = doc
    ordered = sorted(
        fused.values(), key=lambda d: scores[str(d.metadata.get("chunk_id"))], reverse=True
    )
    for doc in ordered:
        doc.metadata["rrf_score"] = scores[str(doc.metadata.get("chunk_id"))]
    return ordered


def hybrid_retrieve(
    session: Session,
    tenant_id: uuid.UUID,
    query: str,
    embedding_client: EmbeddingClient,
    *,
    filters: RetrievalFilters | None = None,
    limit: int = DEFAULT_LIMIT,
    lexical_min_score: float | None = None,
    vector_min_score: float | None = None,
    reranker: Reranker | None = None,
    k: int = RRF_K,
) -> RetrievalOutcome:
    """Run both arms (tenant-scoped, filtered, floored), fuse with RRF, rerank, and
    abstain if nothing survives. Returns LangChain Documents with citations in metadata."""
    lexical = IkipRetriever(
        session=session,
        tenant_id=tenant_id,
        arm="lexical",
        limit=limit,
        filters=filters,
        min_score=lexical_min_score,
    )
    vector = IkipRetriever(
        session=session,
        tenant_id=tenant_id,
        arm="vector",
        limit=limit,
        embedding_client=embedding_client,
        filters=filters,
        min_score=vector_min_score,
    )
    lex_docs = lexical.invoke(query)
    vec_docs = vector.invoke(query)

    fused = reciprocal_rank_fusion([lex_docs, vec_docs], k=k)
    reranked = (reranker or IdentityReranker()).rerank(query, fused, top_k=limit)

    if not reranked:
        return RetrievalOutcome(documents=[], abstained=True, reason="insufficient evidence")
    return RetrievalOutcome(documents=reranked, abstained=False)
