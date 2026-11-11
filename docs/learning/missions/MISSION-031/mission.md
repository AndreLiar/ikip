# MISSION-031 — Seed a real eval corpus so the live eval loop runs (Epic 5, Stories 5.1/5.2)

**Mode:** Autonome (the 🔴 item from the Epic-5 review) + knowledge transfer.
**Objective:** make the live eval loop (`eval run/ragas/compare`) actually executable by seeding a real evaluation corpus whose chunks back the gold dataset's evidence handles — the demonstrable thesis artifact (`comparison.json` + Langfuse scores).
**Maps to:** Epic 5 / Stories 5.1 (datasets) + 5.2 (Ragas/comparison).

## The gap it closes
`failure_modes.json` referenced SYMBOLIC handles (`c-e42`, `c-ocr-motor`…) that matched no ingested data, so `eval run` retrieved nothing and the live path was pure scaffolding. Now a small real corpus backs those handles.

## What was built
- **`eval/seed.py`** — `SeedDoc` + `EVAL_CORPUS` (8 realistic docs, one chunk each, aligned to the gold's evidence handles: a fault-code lookup, a **version-aware pair** (obsolete rev A + current rev B of one document), two **conflicting** current sources, a **table** row, an **OCR'd** line, and a **poisoned** doc). `seed_corpus(session, tenant_id, embedding_client)` creates the tenant + each Document/DocumentVersion and ingests through the REAL `index_version` (Section/Chunk/Embedding), returning `{symbolic_id: chunk_uuid}`. `resolve_gold_ids(gold, mapping)` rewrites `relevant_chunk_ids` symbolic→real and emits a runnable gold file (abstain cases stay empty).
- **CLI** `python -m ikip_common.eval seed --tenant <uuid> --out failure_modes.resolved.json` — one-time; then `eval run/ragas/compare --gold failure_modes.resolved.json` has real evidence to retrieve + judge.
- Port-injected (`Session` + `EmbeddingClient`) like the indexing it wraps: tests use `FakeEmbeddingClient`; the CLI injects the Azure client.

## Acceptance / verification
- ruff + format ✓; `pytest apps packages services` → 223 passed / 44 skipped.
- **Pure tests**: the corpus covers every evidence handle the gold references (no dangling handle); `resolve_gold_ids` rewrites handles and keeps abstain cases empty.
- **DB-gated test** (CI ephemeral Neon + `FakeEmbeddingClient`): `seed_corpus` ingests all docs through the real indexing path and returns a complete, tenant-scoped symbolic→chunk mapping (one chunk per doc).
### Live run — actually executed (2026-11-11)
Ran against **real Azure + dev Neon**:
- `eval seed --tenant e5a1d000…51` → **8 chunks ingested**, resolved gold emitted with real UUIDs. **[verified live]**
- `eval run --gold failure_modes.resolved.json` → **recall@k = 1.0** (retrieval found every seeded chunk → resolution works), citation_resolution = 1.0, grounding_coverage = 1.0, **behavior_conformity = 0.875** (7/8 — one case didn't behave as the gold expects: a real, useful eval signal), est. cost ≈ $0.0011, p50 latency ≈ 1.75 s. **[verified live]** — the custom half of the loop runs end-to-end on real data.
- `eval compare` (Ragas judged) → **BLOCKED by a ragas↔langchain-community incompatibility**: ragas (0.2.15 and 0.4.3) hard-imports `langchain_community.chat_models.vertexai`, removed in langchain-community ≥ 0.4; pinning lc-community back conflicts with our `langchain-core>=0.3` stack. This is the exact dependency-drift class the `RagasAdapter` contract test guards our mapping against — our code is correct; the ecosystem pin isn't resolved. **[blocked — follow-up]**

## How to produce the thesis artifact (documented runbook)
```
uv run --group embeddings python -m ikip_common.eval seed \
    --tenant <uuid> --out eval-results/failure_modes.resolved.json
uv run --group embeddings --group ragas python -m ikip_common.eval compare \
    --gold eval-results/failure_modes.resolved.json --tenant <uuid> --sample 5 --runs 3 \
    --out eval-results
```
→ `eval-results/comparison.json` (custom-vs-Ragas agreement/divergence/cost/variance) + Ragas scores attached to each case's Langfuse trace (Story 5.4 ↔ 5.2).

## Deliverables
- `eval/seed.py`; `eval/__main__.py` (`seed` subcommand + runbook in the CLI docstring).
- `tests/test_eval_seed.py` (pure + DB-gated).

## Follow-ups (noted)
- **Resolve the ragas↔langchain-community pin** (the live `compare` blocker): find a ragas release whose judge imports are compatible with `langchain-core>=0.3` (or add a `langchain-google-vertexai` shim / pin a compatible lc-community), then run `compare` and commit `comparison.json` as dissertation evidence. The seed + custom harness already run live; only the Ragas judge is blocked.
- Investigate the one `behavior_conformity` miss surfaced by the live run (which failure-mode case answered when it should have abstained, or vice-versa).
- Swap the OCR/table seed docs for genuinely ingested scanned-PDF/table artifacts (real extraction path) for a stronger signal.

## Concepts
Completes the eval loop of [[MISSION-029]] (Ragas) + [[MISSION-030]] (trace↔score↔config). Reuses the Epic-2↔3 indexing path (`index_version`).
