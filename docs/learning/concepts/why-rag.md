# Concept — Why RAG? (why the context window isn't enough)

_Write-once concept note. Frames Epic 3 (Retrieval & RAG). Answers: "why not just put all the documents in the prompt?"_

## First: what is a context window?
The **context window** is the LLM's **working memory for one request** — the maximum amount of text it can read *at once* (your question + the documents you give it + the answer it's writing). Everything must fit inside it.

- **Measured in tokens, not words.** A **token** ≈ a chunk of a word; rule of thumb **1 token ≈ ¾ of a word ≈ 4 characters**. A page of a manual ≈ ~500 tokens; a 100-page manual ≈ ~50,000 tokens.
- **The desk analogy.** Picture the LLM working at a **fixed-size desk** (the context window, e.g. 128k or 1M tokens). You lay on it: the question + the documents + it writes the answer there. It all has to fit at the same time. Pile on too many documents → it **overflows** (error) or you must remove things.
- **No memory between requests.** The desk is **wiped** after each call. The model only "knows" what is on the desk *right now* — it does not remember your previous question or documents.
- **Context window ≠ the model's knowledge.** A model has two sources of information:
  | Source | What it is |
  |---|---|
  | **Weights (training)** | what it learned during training — frozen, general, **no access to your private documents** |
  | **Context window** | what *you* put in at request time — your manuals, your question |

  Your industrial manuals are **not** in the weights (private, recent). The only way to make the model use them is to **put them in the context window** — which is exactly why "just put everything in" is tempting, and why it fails below.
- **Typical sizes (for scale):** common models ~**128,000 tokens** (~250 pages); the largest ~**1,000,000 tokens** (~2,000 pages ≈ **~20 manuals**).

## The naive idea
"LLMs have huge context windows now — why not stuff **all** the manuals into the prompt and ask the question?" If that worked, RAG wouldn't exist. It fails for seven reasons — the first four are general, the last three are specific to IKIP's value.

## 1. It doesn't fit (the physical wall)
Context windows are large but **finite**. The IKIP math:

| | Tokens |
|---|---|
| 1 manual (~100 pages) | ~50,000 |
| **MVP: 500 manuals** | **~25,000,000** |
| Later: 10,000 manuals | ~500,000,000 |

Even the largest context windows (~1M tokens) hold **~20 manuals** — the MVP corpus is **500**. It's ~25× too big from day one, 500× later. Impossible.

## 2. Cost
You pay **per token, per request**. Even if it fit, sending ~25M input tokens on every question costs **tens of dollars per question**. RAG sends only the relevant passages (~4k tokens) → **~$0.003**. Four orders of magnitude.

## 3. Latency (NFR2: TTFT < 5s)
More input tokens → slower to first token. A giant context takes seconds just to read, breaking the time-to-first-token target.

## 4. Quality DROPS with too much context ("lost in the middle")
The counter-intuitive one, and the most important: **more context often means worse answers**. LLM attention degrades over long inputs — models recall the start and end well but **"lose" information in the middle**. Burying the right E42 procedure inside 500 manuals makes the model **more** likely to miss it than if you hand it the **5 right passages**.

> Less-but-relevant beats more-but-buried.

## 5. Freshness & versioning (FR14)
Manuals change (revision A → B). "Everything in the prompt" means re-sending the whole corpus on every update, with **no way** to serve "the applicable revision, not the obsolete one". RAG filters by version **at retrieval time**.

## 6. Multi-tenant security (a hard blocker — NFR10, FR21)
You cannot put **all customers'** documents in one prompt — that's a guaranteed **cross-tenant leak**. RAG **authorizes before it retrieves**, so each tenant only ever sees its own documents.

## 7. Citations & abstention (IKIP's core value — FR16, FR17)
Dump 500 manuals and the model can't tell you **which document, which page** supports its answer. RAG knows exactly which passages it retrieved → **precise citations**, and can **abstain** when nothing relevant is found instead of hallucinating.

## The solution: RAG = "retrieve first, then give only the relevant bit"
```
question → RETRIEVE the ~5 relevant passages (out of ~400k chunks)
         → put ONLY those in the prompt (~4k tokens)
         → LLM answers, grounded, with citations (or abstains)
```

| | Everything in context | RAG |
|---|---|---|
| Fits? | ❌ ~25M tokens | ✅ ~4k tokens |
| Cost/question | tens of $ | ~$0.003 |
| Latency | slow | fast |
| Quality | degraded (buried) | focused |
| Multi-tenant | leaks | isolated |
| Version-aware | no | yes |
| Citations | no | yes |

## Analogy
- **Everything in the context** = handing a technician the **whole library** and saying "the answer's in there." Technically true, practically useless.
- **RAG** = a **librarian** who fetches the 3 right pages, lays them out, and says "here — page 142 of the manual, revision B."

## One sentence
The context window isn't enough because it's too small for the corpus, too costly and slow to fill, lower-quality when overfilled, and incapable of freshness, tenant isolation, and citations — exactly what makes IKIP trustworthy. Hence RAG (Epic 3).

## What this means for Epic 3
Everything in Epic 3 exists to make "retrieve the right few passages" work well:
- **chunking** (3.1) — split documents into retrievable, citable units;
- **embeddings** (3.2) — represent meaning for semantic search;
- **hybrid retrieval + rerank + filters** (3.3/3.4) — find the *right* passages (keyword + meaning + equipment/version);
- **LangGraph grounded answer** (3.5) — synthesize + cite, or abstain;
- **evaluation** (3.6) — prove retrieval quality (Recall@K, citation correctness).

## Related
- [pdf-extraction](./pdf-extraction.md) / [dedup-versioning](./dedup-versioning.md) (produce the curated, versioned content RAG retrieves) · [multi-tenancy](./multi-tenancy.md) (authorize-before-retrieve).
- Decisions: [ADR 0001](../../adr/0001-vector-store-pgvector.md) (pgvector), [ADR 0004](../../adr/0004-hybrid-retrieval-on-postgres.md) (hybrid retrieval), [ADR 0002](../../adr/0002-dual-orchestration-dagster-langgraph.md) (LangGraph). Explainer: [why-langgraph](../../architecture/why-langgraph.md).
