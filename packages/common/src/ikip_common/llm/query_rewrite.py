"""Query rewriting for retrieval (ADR 0026 — the `analyze` seam).

A user's question is often a poor *search* query (typos, acronyms, vague wording). Rewrite it into
a retrieval-optimised query — fix typos, expand abbreviations, add domain terms/synonyms — WITHOUT
changing intent. Used **only to search**: generation still answers the user's *original* question
over the retrieved evidence, so the grounding/citation guarantees are untouched (this is why query
rewrite is a safer lever than context expansion — it can only change *what is retrieved*).

Opt-in behind the retriever port; falls back to the original query on any failure (never breaks
retrieval).
"""

from __future__ import annotations

from pydantic import BaseModel

from ikip_common.llm.base import ChatClient, ChatMessage

_SYSTEM = (
    "You rewrite a user's question into ONE search query that maximises document retrieval from a "
    "technical/industrial knowledge base. Fix typos, expand abbreviations/acronyms, and add key "
    "technical terms or synonyms likely to appear in the source documents. Preserve the user's "
    "intent exactly: do not answer it, and do not add constraints they did not imply. Output only "
    "the rewritten search query."
)


class RewrittenQuery(BaseModel):
    query: str


def rewrite_query(chat_client: ChatClient, query: str) -> str:
    """Return a retrieval-optimised rewrite of `query`, or the original on empty/failed output."""
    try:
        out = chat_client.complete_structured(
            [
                ChatMessage(role="system", content=_SYSTEM),
                ChatMessage(role="user", content=query),
            ],
            RewrittenQuery,
        )
        return (out.query or "").strip() or query
    except Exception:  # noqa: BLE001 — retrieval must never break on a rewrite failure
        return query
