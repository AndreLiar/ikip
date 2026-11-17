# MISSION-048 — Cross-encoder reranker: build the seam, weigh the value before paying for it

- **Mode:** Guidé (a dependency + architecture decision — torch/model weight vs measured headroom)
- **Date:** 2026-11-17
- **Related:** [ADR 0032 §3](../../adr/0032-memory-and-context-engineering.md) (context engineering — reranking) · [ADR 0021](../../adr/0021-reuse-langchain-behind-ports.md) (ports) · [MISSION-046](../MISSION-046/mission.md) (BM25 "not warranted" by measurement) · [MISSION-047](../MISSION-047/mission.md) (context-engineering A/B) · concept [hybrid-retrieval](../concepts/hybrid-retrieval.md)

## Objective
ADR 0032 §3 lists a cross-encoder reranker behind the existing `Reranker` port (identity →
cross-encoder) as a context-engineering lever. Before adding a **heavy dependency** (sentence-
transformers → torch) and a per-query inference cost, decide whether it's **worth it** given what we
have already measured — same discipline as MISSION-046 (BM25).

## The value question (answered before coding)
A cross-encoder scores the `(query, passage)` **pair jointly** (vs our bi-encoder embeddings, which
score them independently), so it ranks relevance more sharply — but at O(candidates) model calls, so
it runs only as a **reranker over the fused top-N**. Crucially, **it only reorders what retrieval
already found**: it helps *iff* the right chunk is retrieved but ranked too low; it can't rescue a
chunk that was never retrieved, and does nothing when ordering is already good.

What our measurements say about the **headroom**:
- NTRS recall@5 = **0.89**, faithfulness **0.89–0.99**, context_recall **0.94** (MISSION-047).
- FR corpora faithfulness ~**1.0** (MISSION-045).
- A *free* reorder (litm) already bought **+0.076** faithfulness (MISSION-047).
- Track record: auto-merge, window, contract, query-rewrite, dedup — **none beat baseline** when
  measured.

→ The right chunks are mostly already retrieved **and** mostly already well-ordered, so a reranker's
room to help on this gold is **small and uncertain**. The cost (torch dep, download, per-query CPU
latency; MiniLM is EN-only so FR would force a bigger multilingual model) is **certain**. Uncertain
small benefit vs. certain heavy cost.

## Decision — build the seam, defer the dependency (design-only)
Implement `CrossEncoderReranker` behind the `Reranker` port **with an injectable `score_fn`**, so the
reorder logic + the A/B wiring are **pure and fully tested with zero new dependency**. The live-model
path lazy-imports `sentence-transformers` (deliberately **not** a declared dependency-group) and
raises a clear, actionable error if absent. We pay the torch/model cost **only if** a live A/B is
later judged worth running.

- `ikip_common.rerank.CrossEncoderReranker` — reorders fused candidates by `(query, passage)` score;
  **reorder-only** (every Document keeps its metadata → citation/grounding guarantee intact,
  ADR 0022); stamps `metadata['cross_encoder_score']` for observability.
- `make_hybrid_retrieve(..., reranker=…)` threads the port into `hybrid_retrieve` (default stays
  `IdentityReranker`).
- eval CLI `--reranker {identity,cross-encoder} [--reranker-model …]` on `run`/`ragas`/`compare`,
  recorded under `config.reranker` — the A/B is ready to run the instant a model is chosen.
- 9 pure tests (injected score_fn): reorder-by-score, top_k truncation, score-stamp without touching
  the citation, empty-safe, pair construction, Reranker-port conformance, clear error on the missing
  optional dep, and the `make_hybrid_retrieve` forwarding.

## Why design-only (not "go anyway", not "skip")
- **Go anyway** would spend a heavy, certain cost against a small, uncertain gain — against the
  project's measured-first discipline, and likely to join the "didn't beat baseline" list.
- **Skip entirely** throws away a cheap, reusable seam + the ability to measure later for free.
- **Design-only** keeps the option open at **zero committed cost**: the port + instrument exist; the
  dependency decision is deferred to the moment there's a measured reason to pay for it.

## Honest limits / next step
- The reorder logic is proven; the **live model is unmeasured** (no dep installed). To run the A/B:
  `pip install sentence-transformers`, then `eval compare --runs 3 --reranker cross-encoder …`
  (serial — the MISSION-047 429 lesson) vs baseline.
- MiniLM is **English**; an FR run needs a multilingual model (e.g. `BAAI/bge-reranker-v2-m3`) — pass
  `--reranker-model`.
- Expected outcome, stated up front for honesty: given the headroom above, the reranker **may well
  not clear the bar** either — and documenting *that* would be as valuable as a win (cf. MISSION-046).

## See also
`ikip_common/rerank.py` · `packages/common/tests/test_rerank.py`. Keeps [ADR 0032 §3](../../adr/0032-memory-and-context-engineering.md)'s reranker lever **opt-in + A/B-gated** without paying for it before it's justified.
