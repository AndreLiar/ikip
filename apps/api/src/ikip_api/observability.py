"""Observability wiring for the API (Story 5.4, ADR 0013).

DI providers for the `Telemetry` port (Langfuse when configured, else no-op) and a
`TraceRecorder` that writes the durable `query_trace` row. Both are FastAPI dependencies
so tests inject fakes (no DB, no Langfuse). The query itself is hashed, never stored raw
(AC4); only IDs + metadata are persisted.
"""

from __future__ import annotations

import uuid
from typing import Protocol


class TraceRecorder(Protocol):
    def record(
        self,
        *,
        tenant_id: uuid.UUID,
        operation: str,
        query: str,
        status: str,
        actor_user_id: uuid.UUID | None,
        conversation_id: uuid.UUID | None,
        message_id: uuid.UUID | None,
        model_version: str | None,
        retrieved_chunk_ids: list[str],
        latency_ms: float,
        cost_usd: float,
        trace_id: str | None,
    ) -> None: ...


def get_telemetry():  # noqa: ANN201 — Telemetry, avoid importing the port at module load
    from ikip_common.telemetry import build_telemetry

    return build_telemetry()


class _DbTraceRecorder:
    def record(
        self,
        *,
        tenant_id,
        operation,
        query,
        status,
        actor_user_id,
        conversation_id,
        message_id,
        model_version,
        retrieved_chunk_ids,
        latency_ms,
        cost_usd,
        trace_id,
    ) -> None:  # noqa: ANN001
        from ikip_common.db import make_session_factory
        from ikip_common.db.traces import QueryTraceRepository

        with make_session_factory()() as session:
            QueryTraceRepository(session, tenant_id).record(
                operation=operation,
                query=query,
                status=status,
                actor_user_id=actor_user_id,
                conversation_id=conversation_id,
                message_id=message_id,
                model_version=model_version,
                retrieved_chunk_ids=retrieved_chunk_ids,
                latency_ms=latency_ms,
                cost_usd=cost_usd,
                trace_id=trace_id,
            )
            session.commit()


def get_trace_recorder() -> TraceRecorder:
    return _DbTraceRecorder()
