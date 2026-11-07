"""LLMGroundingValidator tests (Story 3.5) — pure, no network.

Uses a tiny stub chat client that returns a scripted GroundingResult and records the
judge prompt, so we assert the validator batches claims + feeds the cited evidence.
"""

from collections.abc import Sequence

from ikip_common.llm.base import ChatMessage, SchemaT
from ikip_common.llm.grounding import LLMGroundingValidator
from ikip_common.llm.schemas import Claim, ClaimVerdict, GroundingResult


class _StubJudge:
    model_version = "stub"

    def __init__(self, result: GroundingResult) -> None:
        self._result = result
        self.calls: list[list[ChatMessage]] = []

    def complete_structured(
        self, messages: Sequence[ChatMessage], schema: type[SchemaT]
    ) -> SchemaT:
        self.calls.append(list(messages))
        assert schema is GroundingResult
        return self._result  # type: ignore[return-value]


def test_validator_batches_claims_and_feeds_cited_evidence() -> None:
    judge = _StubJudge(
        GroundingResult(
            verdicts=[
                ClaimVerdict(claim_index=0, verdict="supported"),
                ClaimVerdict(claim_index=1, verdict="unsupported"),
            ]
        )
    )
    validator = LLMGroundingValidator(judge)
    claims = [
        Claim(text="E42 is overheat", evidence_markers=["E1"]),
        Claim(text="service yearly", evidence_markers=["E2"]),
    ]
    evidence = {"E1": "Fault E42: overheat.", "E2": "Lubrication only."}
    result = validator.validate(claims, evidence)

    assert len(result.verdicts) == 2
    assert len(judge.calls) == 1  # one batched call for all claims
    prompt = judge.calls[0][1].content
    assert "Fault E42: overheat." in prompt and "[claim 0]" in prompt


def test_validator_empty_claims_no_call() -> None:
    judge = _StubJudge(GroundingResult(verdicts=[]))
    assert LLMGroundingValidator(judge).validate([], {}).verdicts == []
    assert judge.calls == []
