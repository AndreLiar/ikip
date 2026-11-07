# MISSION-017 — Decisions

## D1 — Deterministic baseline in 3.6; Ragas in Epic 5 (ADR 0016)
Story 3.6 is the quality baseline "before the UI". Deterministic metrics (Recall@K, citation
resolution, grounding coverage, behavior conformity, latency, est. cost) are fast/free/
reproducible → per-push gate. Ragas (LLM-judged faithfulness/relevancy) + the custom-vs-Ragas
comparison are costly/non-deterministic → Epic 5, as ADR 0016 already split. Not widening 3.6.

## D2 — `citation_grounding_coverage`, NOT `faithfulness` (mandatory distinction)
A deterministic check can verify a citation **resolves** to a retrieved chunk; it **cannot**
prove the chunk **entails** the claim. Naming it `faithfulness` would overstate it. We name it
`citation_grounding_coverage` (presence/resolution) and document the limit explicitly. Semantic
entailment (faithfulness) is LLM-judged in Epic 5. The Story 3.5 grounding judge is reused when
its results are available, but is **not** required for the deterministic CI gate.

## D3 — Separate retrieval and answer results
A bad Recall@K ≠ a bad answer. The harness records retrieval ids + recall separately from
citation/grounding/behavior, so a regression is attributable. Retrieval is captured via a
wrapping callable (no double retrieval).

## D4 — Three report artifacts; baseline promoted manually
`runs/<ts>.json` (history) + `latest.json` (last) + `baseline.json` (approved reference).
`write_run` never writes baseline; `promote` sets it explicitly. This prevents a degraded run
from silently becoming the reference. Regression = higher-is-better metric fell > tolerance
below baseline (`check` exits 1). `gold_set_version` separates a quality regression from a corpus change.

## D5 — `evaluation_case.expected_behavior` as String, not DB enum
Stored as `String(16)` (values from a Python `ExpectedBehavior` StrEnum) to avoid the recurring
Postgres enum-type migration trap (drop-type in downgrade). Simpler, trap-free migration.

## D6 — No LLM in the per-push gate
Determinism + cost: the gate runs the harness with a `FakeChatClient` over a versioned gold
fixture. Live evaluation (real Azure) is triggered separately via the CLI, with a versioned
dataset/config. Even at fixed temperature, remote LLM outputs aren't perfectly reproducible.
