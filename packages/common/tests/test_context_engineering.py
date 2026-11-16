"""Context-engineering transform tests (ADR 0032 layer 3). Pure — tiny fake docs, base-env safe."""

from dataclasses import dataclass, field

from ikip_common.context_engineering import (
    ContextBudget,
    apply_token_budget,
    dedup_documents,
    engineer_context,
    estimate_tokens,
    reorder_lost_in_the_middle,
)


@dataclass
class _Doc:
    """Structural stand-in for a LangChain Document (page_content + metadata)."""

    page_content: str
    metadata: dict = field(default_factory=dict)


def _doc(cid: str, text: str) -> _Doc:
    return _Doc(page_content=text, metadata={"chunk_id": cid})


# --------------------------------------------------------------------------------- default no-op


def test_default_budget_is_identity() -> None:
    docs = [_doc("a", "alpha"), _doc("b", "beta"), _doc("c", "gamma")]
    out = engineer_context(docs)
    assert [d.metadata["chunk_id"] for d in out] == ["a", "b", "c"]
    assert out == docs  # same objects, order untouched


# ------------------------------------------------------------------------------------- dedup


def test_dedup_drops_near_duplicates_keeping_higher_ranked() -> None:
    d1 = _doc("a", "the pump pressure must stay below 5 bar during operation")
    d2 = _doc("b", "the pump pressure must stay below 5 bar during operation today")  # ~dup of d1
    d3 = _doc("c", "lubricate the bearing every 500 hours of runtime")
    out = dedup_documents([d1, d2, d3], threshold=0.8)
    ids = [d.metadata["chunk_id"] for d in out]
    assert ids == ["a", "c"]  # b dropped as near-dup; the higher-ranked "a" survives with citation
    assert out[0].metadata == {"chunk_id": "a"}  # citation preserved (original doc, not merged)


def test_dedup_keeps_distinct_chunks() -> None:
    out = dedup_documents(
        [_doc("a", "pump pressure limit"), _doc("b", "bearing lubrication")], threshold=0.9
    )
    assert [d.metadata["chunk_id"] for d in out] == ["a", "b"]


# ------------------------------------------------------------------------------------- budget


def test_token_budget_keeps_strongest_until_full() -> None:
    # estimate_tokens = len//4. "x"*40 -> 10 tokens each.
    docs = [_doc("a", "x" * 40), _doc("b", "y" * 40), _doc("c", "z" * 40)]
    out = apply_token_budget(docs, max_tokens=22)  # fits a(10)+b(10)=20, c would make 30 > 22
    assert [d.metadata["chunk_id"] for d in out] == ["a", "b"]


def test_token_budget_always_keeps_first_doc() -> None:
    # Even if the top doc alone exceeds the budget, keep it — abstention stays the retriever's call,
    # the budget must not silently empty the evidence.
    docs = [_doc("a", "x" * 400), _doc("b", "y" * 4)]
    out = apply_token_budget(docs, max_tokens=5)
    assert [d.metadata["chunk_id"] for d in out] == ["a"]


def test_estimate_tokens_monotonic() -> None:
    assert estimate_tokens("x" * 4) == 1
    assert estimate_tokens("x" * 40) == 10
    assert estimate_tokens("") == 1  # floor of 1, never 0


# ------------------------------------------------------------------- lost-in-the-middle reorder


def test_reorder_puts_strongest_at_edges() -> None:
    # input is descending relevance: a(best) .. e(worst)
    docs = [_doc(c, c) for c in "abcde"]
    out = [d.metadata["chunk_id"] for d in reorder_lost_in_the_middle(docs)]
    # strongest at both ends, weakest in the middle
    assert out[0] == "a"
    assert out[-1] == "b"
    assert out[len(out) // 2] == "e"  # the least relevant lands in the middle
    assert set(out) == set("abcde")  # same set, pure reshuffle


# ----------------------------------------------------------------------------- full pipeline


def test_engineer_context_applies_dedup_then_budget_then_reorder() -> None:
    d1 = _doc("a", "pump pressure stays below five bar during normal operation")
    d2 = _doc("b", "pump pressure stays below five bar during normal operation")  # exact dup of a
    d3 = _doc("c", "lubricate the main bearing every five hundred hours")
    d4 = _doc("d", "replace the inlet filter at each scheduled maintenance window")
    budget = ContextBudget(dedup=True, max_tokens=1000, lost_in_the_middle=True)
    out = [d.metadata["chunk_id"] for d in engineer_context([d1, d2, d3, d4], budget)]
    assert "b" not in out  # dedup removed the duplicate
    assert set(out) == {"a", "c", "d"}  # survivors kept, all citations intact
    assert out[0] == "a"  # strongest stays at the front edge after reorder
