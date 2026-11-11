"""Multi-turn evaluation (Story 5.2, multi-turn gap).

Our answer flow + Ragas are single-turn. This evaluates short CONVERSATIONS by running the
turns sequentially and feeding each turn the prior (question, answer) as context (query
contextualization), then scoring the FINAL turn's behaviour. It reuses the single-turn
`grounded_answer` unchanged — so it measures whether a follow-up (pronouns/ellipsis) is
handled, without a native conversational retriever (that is a larger follow-up).

Pure contextualization (`contextualize`) is unit-testable; the run needs the graph.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class MultiTurnCase:
    case_key: str
    turns: list[str]  # the user questions, in order
    expected_behavior: str  # for the FINAL turn
    relevant_chunk_ids: list[str] = field(default_factory=list)
    ground_truth: str | None = None
    category: str = ""
    language: str = "en"


@dataclass
class MultiTurnResult:
    case_key: str
    language: str
    n_turns: int
    final_behavior: str
    behavior_match: bool
    final_answer: str


@dataclass
class MultiTurnReport:
    gold_set_version: str
    n_cases: int
    behavior_conformity: float
    by_language: dict
    cases: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


def load_multiturn(path: str | Path) -> tuple[str, list[MultiTurnCase]]:
    doc = json.loads(Path(path).read_text())
    cases = [
        MultiTurnCase(
            case_key=c["case_key"],
            turns=[t["question"] for t in c["turns"]],
            expected_behavior=c["expected_behavior"],
            relevant_chunk_ids=c.get("relevant_chunk_ids", []),
            ground_truth=c.get("ground_truth"),
            category=c.get("category", ""),
            language=c.get("language", doc.get("language", "en")),
        )
        for c in doc["cases"]
    ]
    return doc.get("gold_set_version", "unknown"), cases


def contextualize(history: Sequence[tuple[str, str]], question: str) -> str:
    """Fold prior (question, answer) turns into a standalone query so retrieval + the model
    can resolve a follow-up's pronouns/ellipsis. The last line is the actual question."""
    if not history:
        return question
    # Keep it a NATURAL standalone question — a raw "Conversation so far / Follow-up"
    # dump can trip the judge model's jailbreak/prompt-injection content filter. We fold
    # the prior topics in as context clauses instead.
    topics = "; ".join(q.rstrip("?. ") for q, _ in history)
    return f"{question} (earlier in this conversation we discussed: {topics})"


def evaluate_multiturn(
    cases: Sequence[MultiTurnCase],
    *,
    retrieve: Callable[[str], object],
    chat_client,  # noqa: ANN001 — ChatClient
    validator=None,  # noqa: ANN001 — GroundingValidator
    gold_set_version: str = "unknown",
) -> MultiTurnReport:
    from ikip_common.eval.harness import _mean
    from ikip_common.llm.answer import grounded_answer

    results: list[MultiTurnResult] = []
    for case in cases:
        history: list[tuple[str, str]] = []
        final = None
        behavior = "abstained"
        try:
            for question in case.turns:
                q = contextualize(history, question)
                final = grounded_answer(
                    q, retrieve=retrieve, chat_client=chat_client, validator=validator
                )
                history.append((question, final.answer or ""))
            behavior = final.status if final else "abstained"
        except Exception as exc:  # noqa: BLE001 — a judge/content-filter error IS an outcome
            # e.g. Azure content filter (jailbreak/injection) on a poisoned turn. Record it
            # as 'error' rather than crashing the whole run; it never silently "answers".
            behavior = "error"
            final = None
            history.append((case.case_key, f"<error: {type(exc).__name__}>"))
        results.append(
            MultiTurnResult(
                case_key=case.case_key,
                language=case.language,
                n_turns=len(case.turns),
                final_behavior=behavior,
                behavior_match=behavior == case.expected_behavior,
                final_answer=(final.answer if final else "") or "",
            )
        )
    langs = sorted({r.language for r in results})
    return MultiTurnReport(
        gold_set_version=gold_set_version,
        n_cases=len(results),
        behavior_conformity=_mean([1.0 if r.behavior_match else 0.0 for r in results]),
        by_language={
            lang: {
                "n": sum(1 for r in results if r.language == lang),
                "behavior_conformity": _mean(
                    [1.0 if r.behavior_match else 0.0 for r in results if r.language == lang]
                ),
            }
            for lang in langs
        },
        cases=[asdict(r) for r in results],
    )
