"""Grounding validation: does each claim's evidence actually support it? (Story 3.5).

A valid citation handle ≠ a supported claim. After generation we check *semantic
support* (entailment), not just handle validity. The default `LLMGroundingValidator`
does this with a single batched LLM-judge call (ADR 0022): judging entailment against
provided text is a far more constrained task than open generation, so it is markedly
more reliable — and it needs no new dependency (reuses the ChatClient, ADR 0012).
A cross-encoder/NLI adapter can replace it behind this port later (ADR 0021).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ikip_common.llm.base import ChatClient, ChatMessage
from ikip_common.llm.schemas import Claim, GroundingResult

_JUDGE_SYSTEM = (
    "You are a strict grounding judge. For each claim, decide whether the cited "
    "evidence text ENTAILS it: 'supported' (fully entailed), 'partial' (only partly), "
    "or 'unsupported' (not entailed or evidence missing). Judge only against the "
    "evidence provided; never use outside knowledge. Return one verdict per claim, "
    "in order, by claim_index."
)


@runtime_checkable
class GroundingValidator(Protocol):
    """Verdicts that each claim is / isn't entailed by its cited evidence."""

    def validate(self, claims: Sequence[Claim], evidence: dict[str, str]) -> GroundingResult: ...


class LLMGroundingValidator:
    """Batched LLM-judge grounding validator (one call for all claims)."""

    def __init__(self, chat_client: ChatClient) -> None:
        self._chat = chat_client

    def validate(self, claims: Sequence[Claim], evidence: dict[str, str]) -> GroundingResult:
        if not claims:
            return GroundingResult(verdicts=[])
        lines: list[str] = []
        for i, claim in enumerate(claims):
            cited = {m: evidence.get(m, "<<missing>>") for m in claim.evidence_markers}
            cited_text = (
                "\n".join(f"  {m}: {t}" for m, t in cited.items()) or "  <<no evidence cited>>"
            )
            lines.append(f"[claim {i}] {claim.text}\nevidence:\n{cited_text}")
        messages = [
            ChatMessage(role="system", content=_JUDGE_SYSTEM),
            ChatMessage(role="user", content="\n\n".join(lines)),
        ]
        return self._chat.complete_structured(messages, GroundingResult)
