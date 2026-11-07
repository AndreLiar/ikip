"""Deterministic fakes for the chat + grounding ports (Story 3.5).

No network, scripted behaviour, so the LangGraph answer flow is CI-testable end to
end — generation, grounding validation, abstention and the adversarial scenarios
(ambiguous / contradictory / obsolete / injected / no-evidence). Pure stdlib + pydantic.
"""

from __future__ import annotations

from collections.abc import Sequence

from ikip_common.llm.base import ChatMessage, SchemaT
from ikip_common.llm.schemas import ClaimVerdict, GroundedAnswer, GroundingResult


class FakeChatClient:
    """Returns a scripted `GroundedAnswer`. Records the messages it was given so tests
    can assert the prompt carried the evidence handles."""

    def __init__(self, answer: GroundedAnswer, *, model_version: str = "fake-chat") -> None:
        self._answer = answer
        self._model_version = model_version
        self.calls: list[list[ChatMessage]] = []

    @property
    def model_version(self) -> str:
        return self._model_version

    def complete_structured(
        self, messages: Sequence[ChatMessage], schema: type[SchemaT]
    ) -> SchemaT:
        self.calls.append(list(messages))
        if schema is not GroundedAnswer:
            raise TypeError(f"FakeChatClient scripted for GroundedAnswer, got {schema.__name__}")
        return self._answer  # type: ignore[return-value]


class FakeGroundingValidator:
    """Scripted grounding verdicts. `default` applies to any claim index not in
    `verdicts`; so `FakeGroundingValidator()` marks everything supported."""

    def __init__(
        self, verdicts: dict[int, str] | None = None, *, default: str = "supported"
    ) -> None:
        self._verdicts = verdicts or {}
        self._default = default

    def validate(self, claims, evidence) -> GroundingResult:  # noqa: ANN001
        return GroundingResult(
            verdicts=[
                ClaimVerdict(claim_index=i, verdict=self._verdicts.get(i, self._default))
                for i in range(len(claims))
            ]
        )
