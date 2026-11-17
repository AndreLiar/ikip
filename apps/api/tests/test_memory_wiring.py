"""Memory wiring into /ask (ADR 0032 L1+L2). Hermetic: pure helpers + a fake session.

Covers the two correctness-critical seams: the conversational-history pairing/ownership gate
(`_load_history`) and the answer-cache context fingerprint (`_context_fingerprint`) that keeps a
memory-influenced answer from colliding with another user's answer to the same raw question.
"""

import uuid

from ikip_api.retrieval import _context_fingerprint, _load_history
from ikip_common.db.retrieval import RetrievalFilters

# --------------------------------------------------------------- _context_fingerprint (cache)


def test_fingerprint_none_when_no_history_and_no_memory() -> None:
    # Default filters (only the per-user ACL) + no history -> None -> cache key unchanged.
    base = RetrievalFilters(user_id=uuid.uuid4())
    assert _context_fingerprint([], base) is None


def test_fingerprint_set_when_history_present() -> None:
    base = RetrievalFilters(user_id=uuid.uuid4())
    fp = _context_fingerprint([("what is FY23 revenue?", "$383B")], base)
    assert fp is not None and len(fp) == 16


def test_fingerprint_set_when_memory_biases_filters() -> None:
    f = RetrievalFilters(user_id=uuid.uuid4(), document_type="manual")
    assert _context_fingerprint([], f) is not None


def test_fingerprint_differs_by_history_and_is_stable() -> None:
    base = RetrievalFilters(user_id=uuid.uuid4())
    a = _context_fingerprint([("q1", "a1")], base)
    a2 = _context_fingerprint([("q1", "a1")], base)
    b = _context_fingerprint([("q2", "a2")], base)
    assert a == a2  # deterministic
    assert a != b  # different thread -> different cache partition


def test_fingerprint_independent_of_user_id_only_filter() -> None:
    # user_id alone is the pre-memory default; it must not, by itself, produce a fingerprint
    # (that path is unchanged from before memory existed).
    assert _context_fingerprint([], RetrievalFilters(user_id=uuid.uuid4())) is None


def test_fingerprint_partitions_the_cache_when_decompose_is_active() -> None:
    # ADR 0033: a decomposed answer must not collide with a single-shot answer to the same question.
    base = RetrievalFilters(user_id=uuid.uuid4())
    assert _context_fingerprint([], base, decompose=False) is None  # off -> key unchanged
    assert _context_fingerprint([], base, decompose=True) is not None  # on -> partitioned


# --------------------------------------------------------------- _load_history (fake session)


class _Exec:
    def __init__(self, *, first=None, rows=None) -> None:  # noqa: ANN002
        self._first = first
        self._rows = rows or []

    def first(self):  # noqa: ANN201
        return self._first

    def all(self):  # noqa: ANN201
        return self._rows


class _FakeSession:
    """Returns the ownership row on the 1st execute, the message rows on the 2nd."""

    def __init__(self, *, owned: bool, rows) -> None:  # noqa: ANN001
        self._owned = owned
        self._rows = rows
        self._n = 0

    def execute(self, _stmt):  # noqa: ANN001, ANN201
        self._n += 1
        if self._n == 1:
            return _Exec(first=(uuid.uuid4(),) if self._owned else None)
        return _Exec(rows=self._rows)


_ROWS = [
    ("user", "q1"),
    ("assistant", "a1"),
    ("user", "q2"),
    ("assistant", "a2"),
]
_IDS = {"tenant_id": uuid.uuid4(), "user_id": uuid.uuid4(), "conversation_id": uuid.uuid4()}


def test_load_history_pairs_user_then_assistant_turns() -> None:
    session = _FakeSession(owned=True, rows=_ROWS)
    assert _load_history(session, **_IDS) == [("q1", "a1"), ("q2", "a2")]


def test_load_history_empty_when_conversation_not_owned() -> None:
    # NFR10: a conversation_id that isn't the caller's yields no history (never leaks another
    # user's thread into retrieval).
    session = _FakeSession(owned=False, rows=_ROWS)
    assert _load_history(session, **_IDS) == []


def test_load_history_bounded_to_last_4_turns() -> None:
    rows = []
    for i in range(10):
        rows += [("user", f"q{i}"), ("assistant", f"a{i}")]
    session = _FakeSession(owned=True, rows=rows)
    out = _load_history(session, **_IDS)
    assert len(out) == 4
    assert out[-1] == ("q9", "a9")  # most recent kept


def test_load_history_ignores_dangling_user_turn() -> None:
    # A trailing user turn with no assistant reply yet is not emitted as a pair.
    session = _FakeSession(owned=True, rows=[("user", "q1"), ("assistant", "a1"), ("user", "q2")])
    assert _load_history(session, **_IDS) == [("q1", "a1")]
