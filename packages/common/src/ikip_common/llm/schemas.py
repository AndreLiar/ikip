"""Typed structured outputs for the grounded-answer graph (Story 3.5, ADR 0022).

The model emits **claims + evidence markers + warnings**, never free-form citations:
each `Claim` references opaque evidence handles (e.g. "E1") that the server mapped
to retrieved chunks. Citations are resolved server-side from trusted retrieval
metadata — the model can't fabricate a document reference, only pick a handle we
gave it (an unknown handle is treated as unsupported).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Claim(BaseModel):
    """One factual statement in the answer, tied to the evidence that supports it."""

    text: str = Field(description="A single factual statement, grounded in the evidence.")
    evidence_markers: list[str] = Field(
        default_factory=list,
        description="Evidence handles supporting this claim, e.g. ['E1','E3']. Only handles shown.",
    )
    safety_critical: bool = Field(
        default=False,
        description="True if this claim concerns safety (hazard, lockout, injury, damage).",
    )


class GroundedAnswer(BaseModel):
    """The model's structured answer. `status='abstained'` when the evidence is
    insufficient — the model must prefer this over guessing."""

    status: Literal["answered", "abstained"]
    claims: list[Claim] = Field(default_factory=list)
    warnings: list[str] = Field(
        default_factory=list,
        description="Safety warnings or uncertainties surfaced from the evidence.",
    )
    abstention_reason: str | None = Field(
        default=None, description="Why the answer abstained (set only when status='abstained')."
    )


class ClaimVerdict(BaseModel):
    """Grounding verdict for one claim against its cited evidence."""

    claim_index: int
    verdict: Literal["supported", "partial", "unsupported"]


class GroundingResult(BaseModel):
    """Output of the GroundingValidator: one verdict per claim (same order)."""

    verdicts: list[ClaimVerdict] = Field(default_factory=list)
