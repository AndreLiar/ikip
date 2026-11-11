# MISSION-026 — End-to-End Tracing (Epic 5, Story 5.4) → OTel→Langfuse + durable `query_trace`

**Mode:** Autonome (first Epic-5 story; greenfield — Langfuse was only config + a doctor health check) + knowledge transfer.
**Objective:** trace every query → chunks → model → answer so behaviour is debuggable and auditable: a durable, queryable `query_trace` row per `/ask`, correlatable to a Langfuse trace, storing IDs + metrics but **not** raw content (NFR16).
**Maps to:** Epic 5 / Story 5.4. Reuses the ports-&-adapters (ADR 0021) + DI-service pattern; realises the observability split of [ADR 0013](../../adr/0013-llmops-observability-otel-langfuse.md).

## What was built
### Telemetry port + adapters (packages/common/telemetry)
- `base.py` — `Telemetry`/`Span`/`SpanContext` Protocols. A `Span` carries `trace_id`, `set_metadata`, `set_cost`, `finish`; the port contract is "callers pass IDs + metadata, not raw prompts/content, unless `Settings.telemetry_capture_content`".
- `langfuse.py` — `LangfuseTelemetry` (lazy-imports the SDK; a span → a Langfuse trace via `start_span`/`update`/`end`). Only IDs/metadata attached by default (AC4).
- `fake.py` — `FakeTelemetry`/`FakeSpan` (in-memory, deterministic `trace_id`; marks `error` on exception, never suppresses) for hermetic tests.
- `__init__.py` — `NullTelemetry` no-op + `build_telemetry(settings)`: Langfuse when creds set, **else no-op**; and if creds are set but the optional `telemetry` dep group isn't installed, it degrades to no-op (tracing is best-effort — never crashes `/ask`).

### Durable trace (packages/common)
- `QueryTrace` model (`query_trace`): `actor_user_id`, `conversation_id`, `message_id`, `operation`, **`query_hash`** (sha256, not raw text), `model_version`, `retrieved_chunk_ids` (JSONB), `status`, `latency_ms`, `cost_usd`, `trace_id` (Langfuse correlation). Plain Strings/JSONB, no DB enum. Migration `f3b1094524b9` (reversible, offline-verified, applied to dev Neon).
- `db/traces.py` — `hash_query()` (normalized sha256) + `QueryTraceRepository` (tenant-scoped): `record`, `recent`, `for_query` (by hash — AC3), `for_conversation`.

### API wiring (apps/api)
- `observability.py` — DI providers `get_telemetry` (the port) + `get_trace_recorder` (`_DbTraceRecorder` → `QueryTraceRepository.record` + commit). Both are FastAPI deps so tests inject fakes (no DB, no Langfuse).
- `retrieval.py` `/ask` — wraps the answer in `telemetry.span("assistant.ask", tenant_id, operation="ask")`, measures `latency_ms`, estimates `cost_usd` (`estimate_cost_usd`), extracts `retrieved_chunk_ids` from the answer's citations, then records one `query_trace` row correlated by `span.trace_id`. Tracing/recording never changes the HTTP result.

### Config / governance
- `TELEMETRY_CAPTURE_CONTENT` (default **false**) added to `Settings` + `.env.example`: raw prompts/content reach Langfuse ONLY when explicitly enabled (NFR16). The durable `query_trace` never stores raw text regardless.

## Acceptance (Story 5.4)
1. `query_trace` records user, retrieval IDs, model, latency and cost. — **[verified]** (model + repo; `/ask` records actor/chunk-ids/latency/cost; DB test `test_record_stores_hash_not_raw_query`, endpoint test asserts a recorded trace).
2. Traces correlatable end-to-end (OTel→Langfuse). — **[verified]** the span's `trace_id` is stored on the row; `LangfuseTelemetry` maps a span → a Langfuse trace (SDK is OTel-backed). [untested live] — exercised with `FakeTelemetry`; a real Langfuse round-trip needs the `telemetry` group + creds.
3. Traces queryable for a given query/conversation. — **[verified]** `for_query` (by hash) + `for_conversation`; DB tests `test_for_query_correlates_by_hash`, `test_for_conversation_is_ordered_and_scoped`.
4. Sensitive content handling respects policy. — **[verified]** query stored as sha256 hash, not raw; `telemetry_capture_content` gates raw capture in Langfuse (default off); test asserts `E42` absent from the hash.

## Verification
- python: ruff ✓; `apps/api packages/common` → 134 passed / 41 skipped (telemetry port tests run everywhere; `query_trace` DB tests run on CI's ephemeral Neon branch).
- DB-gated `query_trace` tests are **not** run against dev Neon locally (they `create_all/drop_all` on `Base`) — CI runs them on a throwaway branch.
- Migration applied to dev Neon: `alembic current` → `f3b1094524b9`; `query_trace` present with 14 cols / 9 indexes.
- OpenAPI unchanged (`AskResponse` schema identical) → no client regen, drift guard stable.

## Deliverables
- `packages/common/telemetry/{base,fake,langfuse,__init__}.py`; `tests/test_telemetry.py`.
- `db/models.py::QueryTrace` + migration `f3b1094524b9`; `db/traces.py`; `tests/test_query_trace.py` (DB-gated).
- `apps/api/observability.py`; `retrieval.py` `/ask` tracing; `tests/test_retrieval_endpoint.py` (trace assertions).
- `config.py::telemetry_capture_content`; `.env.example`.

## Design notes / trade-offs
- **Durable row + Langfuse, not Langfuse alone:** Langfuse is the rich LLM/RAG trace UI, but it's an external SaaS. A tenant-scoped `query_trace` in Postgres gives queryable, EU-resident, framework-agnostic audit even if Langfuse is down/disabled — and is what Epic 5 evals/regression join against. `trace_id` links the two.
- **Hash, not raw query:** satisfies AC4/NFR16 while keeping AC3 queryability (same normalized question → same hash). Raw content is opt-in and lives only in Langfuse.
- **Best-effort tracing:** telemetry/recording wrap but never gate the answer; a missing SDK or creds degrades to no-op.

## Follow-ups (noted)
- Live Langfuse round-trip once the `telemetry` group + creds are provisioned (verify `trace_id` resolves in the Langfuse UI).
- Trace `/retrieve` too (same recorder, `operation="retrieve"`).
- Epic 5 5.1/5.2 (Ragas) + 5.5 regression gates will read `query_trace` + Langfuse.

## Concepts
Realises [ADR 0013](../../adr/0013-llmops-observability-otel-langfuse.md) (observability split) and [ADR 0021](../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md) (ports). Reuses [multi-tenancy](../../concepts/multi-tenancy.md).
