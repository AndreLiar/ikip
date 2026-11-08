"""LangChain adapter over our business retrieval (Story 3.3, ADR 0021).

This is the single place LangChain enters the read path: `IkipRetriever` is a
`langchain_core` `BaseRetriever` that delegates to our tenant-scoped SQL
(`lexical_search` / `vector_search`) and maps each `SearchHit` to a LangChain
`Document` whose `metadata` carries the full citation (FR16). So rerankers,
`EnsembleRetriever` and LangGraph plug in on top — while tenant isolation and
citations stay structural in our SQL, never delegated to the framework.

Imports `langchain_core` at module load, so import this module only where the
`embeddings` dependency-group is installed (it is not auto-imported from
`ikip_common.llm`). The domain (`db/retrieval.py`) never imports LangChain.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from sqlalchemy.orm import Session

from ikip_common.db.retrieval import (
    DEFAULT_LIMIT,
    RetrievalFilters,
    SearchHit,
    lexical_search,
    vector_search,
)
from ikip_common.llm.base import EmbeddingClient


def hit_to_document(hit: SearchHit) -> Document:
    """Map a SearchHit to a LangChain Document, preserving the citation in metadata."""
    return Document(
        page_content=hit.content,
        metadata={
            "chunk_id": str(hit.chunk_id),
            "document_id": str(hit.document_id),
            "document_version_id": str(hit.document_version_id),
            "revision": hit.revision,
            "is_current": hit.is_current,
            "section_id": str(hit.section_id),
            "heading": hit.heading,
            "hierarchy_path": hit.hierarchy_path,
            "page_start": hit.page_start,
            "page_end": hit.page_end,
            "regions": hit.regions,
            "score": hit.score,
        },
    )


class IkipRetriever(BaseRetriever):
    """Tenant-scoped LangChain retriever backed by our SQL search.

    `arm="vector"` embeds the query (via our EmbeddingClient port) then runs pgvector
    HNSW search; `arm="lexical"` runs the `tsvector` full-text search. Either way the
    returned Documents keep the resolvable citation chain in `metadata`.
    """

    session: Session
    tenant_id: uuid.UUID
    arm: str = "vector"
    limit: int = DEFAULT_LIMIT
    embedding_client: EmbeddingClient | None = None
    filters: RetrievalFilters | None = None
    min_score: float | None = None

    # BaseRetriever is a pydantic model; our fields are non-pydantic types.
    model_config = {"arbitrary_types_allowed": True}

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        hits = self._search(query)
        return [hit_to_document(h) for h in hits]

    def _search(self, query: str) -> Sequence[SearchHit]:
        if self.arm == "lexical":
            return lexical_search(
                self.session,
                self.tenant_id,
                query,
                limit=self.limit,
                filters=self.filters,
                min_score=self.min_score,
            )
        if self.arm == "vector":
            if self.embedding_client is None:
                raise ValueError("vector arm requires an embedding_client")
            [query_vector] = self.embedding_client.embed([query])
            return vector_search(
                self.session,
                self.tenant_id,
                query_vector,
                model_version=self.embedding_client.model_version,
                limit=self.limit,
                filters=self.filters,
                min_score=self.min_score,
            )
        raise ValueError(f"unknown arm: {self.arm!r} (expected 'vector' or 'lexical')")
