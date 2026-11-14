# Runbook — Verifying an answer isn't hallucinating

How to *know* (not hope) that an IKIP answer is grounded, not invented. IKIP gives you **three
layers**: prevention by construction, per-answer verification, and systemic measurement. The
ultimate ground truth is the **citation** (real source text), not any model's opinion.
See [ADR 0022](../adr/0022-grounded-answer-langgraph-gpt5-mini.md), [ADR 0016](../adr/0016-rag-evaluation-custom-plus-ragas.md),
concept [rag-evaluation-metrics](../learning/concepts/rag-evaluation-metrics.md), eval [MISSION-043](../learning/missions/MISSION-043/mission.md).

## Layer 1 — Prevention (how the system avoids hallucination by design)
- **Grounded-answer graph** builds the answer *from the retrieved evidence*, not the model's memory.
- **Grounding validator** (`LLMGroundingValidator`) scores each **claim** against its cited evidence →
  verdict `supported` / `partial` / `unsupported`; unsupported claims are dropped.
- **Abstention**: if evidence is insufficient the answer is `status="abstained"` ("insufficient evidence")
  — it does **not** fill the gap with invention.
- **Safety gate** (Story 5.3/6.3): a versioned critical set must hit 100% safe-abstention in CI; injection
  defenses wrap retrieved content. Safety-critical claims are flagged.
- Every answer carries a **"not certified" notice** + any **warnings** (partial support, injection).

## Layer 2 — Per-answer verification (what YOU check on a given answer)
Check, in order: **status → each claim's verdict → the cited evidence → the warnings.**

```bash
uv run --group embeddings --group doctor python - <<'PY'
import uuid
from sqlalchemy import text as sqltext
from ikip_common.db import make_session_factory
from ikip_common.llm import build_chat_client, build_embedding_client
from ikip_common.llm.answer import grounded_answer, make_hybrid_retrieve

TENANT = uuid.UUID("c0f90000-0000-4000-8000-0000000000a1")   # the tenant to query
Q = "What emergency shutdown procedures are described?"
sf = make_session_factory(); emb = build_embedding_client(); chat = build_chat_client()
with sf() as s:
    r = grounded_answer(Q, retrieve=make_hybrid_retrieve(s, TENANT, emb), chat_client=chat)
    print("STATUS:", r.status)                     # answered | abstained
    for i, c in enumerate(r.claims, 1):
        print(f"\nClaim {i} [verdict: {c.verdict}]{' SAFETY' if c.safety_critical else ''}")
        print("  claim:", c.text[:160])
        for ci in c.citations[:1]:                 # resolve citation -> real source text
            src = s.execute(sqltext("select content from chunk where id = cast(:id as uuid)"),
                            {"id": str(ci.chunk_id)}).scalar() if ci.chunk_id else None
            print(f"  evidence (doc {str(ci.document_id)[:8]} p{ci.page_start}):",
                  (src or "(unresolved)")[:200].replace(chr(10), " "))
    for w in r.warnings:
        print("  warning:", w)
PY
```

**How to read it:**
- `status = abstained` → the system refused (good: no invention). Trust the abstention.
- `verdict = supported` **and the cited evidence text matches the claim** → grounded. **Read the evidence** — that
  is the proof, not the model.
- `verdict = partial` / a `warning` → the claim **over-reaches** the evidence; the system says so instead of
  inventing. Treat that part as unconfirmed.
- No citation on a claim → do not trust that claim.

_Seen in practice (MISSION-043): for "detailed safety limits + shutdown procedures", 6/7 claims were `supported`
with matching source text (e.g. "hardwired Emergency Shutdown System … four-stage timed sequence" ← p60), and
claim 5 was flagged `partial` with the warning "evidence does not include the full step-by-step procedure" — the
over-reach was caught, not hallucinated._

## Layer 3 — Systemic measurement (quantify the hallucination rate)
`faithfulness` = fraction of claims supported by the retrieved context = **your hallucination meter**.

```bash
# custom deterministic metrics (free, gate every push): Recall@K + citation resolution
uv run python -m ikip_common.eval run
# Ragas LLM-judged (faithfulness / answer_relevancy / context_precision / context_recall / answer_correctness)
uv run --group ragas python -m ikip_common.eval ragas
```
- `faithfulness = 1.0` → no unsupported claims (measured on the gold set). `< 1.0` → a measurable hallucination
  rate (e.g. MISSION-043: law 1.00 vs NTRS 0.60). Wire a **per-corpus threshold as a regression gate** so a
  prompt/model/retrieval change can't silently lower faithfulness.
- Build a **per-corpus gold set** (question + reference answer); keep it versioned (`eval seed`).

## The honest limit (and the real guarantee)
The grounding validator and Ragas judge are **themselves LLMs** → self-consistency bias; they are not proof.
The **real guarantee is the citation**: every claim resolves to `chunk → section → document → version → page`,
so a human (or an auditor) can open the source and verify. **You don't trust — you verify (citations) and
measure (faithfulness in a gate).**

## Checklist
- [ ] `status` is `answered` (not abstained) for a question that *should* be answerable.
- [ ] Every kept claim has a **citation**, and its **source text matches** the claim.
- [ ] No `partial`/`unsupported` claim is relied on without checking the warning.
- [ ] Safety-critical claims (flagged) are double-checked against the source.
- [ ] `faithfulness` on the corpus gold set is above the agreed threshold (regression gate).
