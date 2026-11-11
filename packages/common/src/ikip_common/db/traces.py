"""Query-trace persistence + querying (Story 5.4, ADR 0013).

Writes a durable `query_trace` per query→answer and reads it back, tenant-scoped. The
query itself is stored as a sha256 hash (never raw text — AC4). `query_hash` makes a
given question correlatable across traces/conversations (AC3) without storing content.
"""

from __future__ import annotations

import hashlib
import uuid

from ikip_common.db.models import QueryTrace
from ikip_common.db.repository import TenantScopedRepository


def hash_query(query: str) -> str:
    """Stable id for a question (normalized: lowercase + stripped). Not reversible."""
    return hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()


class QueryTraceRepository(TenantScopedRepository[QueryTrace]):
    model = QueryTrace

    def record(
        self,
        *,
        operation: str,
        query: str,
        status: str,
        actor_user_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
        message_id: uuid.UUID | None = None,
        model_version: str | None = None,
        retrieved_chunk_ids: list[str] | None = None,
        latency_ms: float = 0.0,
        cost_usd: float = 0.0,
        trace_id: str | None = None,
    ) -> QueryTrace:
        row = QueryTrace(
            tenant_id=self.tenant_id,
            operation=operation,
            query_hash=hash_query(query),
            status=status,
            actor_user_id=actor_user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            model_version=model_version,
            retrieved_chunk_ids=retrieved_chunk_ids or [],
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            trace_id=trace_id,
        )
        self.session.add(row)
        return row

    def recent(self, *, limit: int = 100) -> list[QueryTrace]:
        return list(
            self.session.execute(
                self._scoped().order_by(QueryTrace.created_at.desc()).limit(limit)
            ).scalars()
        )

    def for_query(self, query: str, *, limit: int = 100) -> list[QueryTrace]:
        """All traces of a given question (by hash) for this tenant — AC3 queryability."""
        stmt = (
            self._scoped()
            .where(QueryTrace.query_hash == hash_query(query))
            .order_by(QueryTrace.created_at.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars())

    def for_conversation(self, conversation_id: uuid.UUID) -> list[QueryTrace]:
        stmt = (
            self._scoped()
            .where(QueryTrace.conversation_id == conversation_id)
            .order_by(QueryTrace.created_at.asc())
        )
        return list(self.session.execute(stmt).scalars())
