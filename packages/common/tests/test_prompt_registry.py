"""Versioned prompt/config registry + gates (Story 5.5) — pure, no network, no langgraph.

Covers: the shipped v1 artifact == BUILTIN_V1 (no silent drift), content hashing,
activate/rollback round-trip, the promotion gate (retrieval + groundedness + safety), and
the Langfuse-sync seam (a recording publisher stands in for the SDK).
"""

from __future__ import annotations

import pytest
from ikip_common.llm.prompts import (
    BUILTIN_V1,
    GateResult,
    PromotionBlockedError,
    PromptConfig,
    PromptConfigError,
    PromptPublisher,
    PromptRegistry,
    _builtin_variant,
    active_prompt_config,
    default_registry,
    evaluate_gates,
)


class _RecordingPublisher(PromptPublisher):
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    def publish(self, config: PromptConfig, *, label: str) -> None:
        self.published.append((config.version, label))


def _seed(tmp_path) -> PromptRegistry:
    reg = PromptRegistry(tmp_path)
    reg.write(BUILTIN_V1)
    reg.write(_builtin_variant("v2", generate_system="v2 system prompt"))
    reg.activate("v1")
    return reg


# --- shipped artifact integrity -------------------------------------------


def test_shipped_v1_matches_builtin() -> None:
    # v1 is the drift guard: the repo artifact must equal the code's BUILTIN_V1.
    assert default_registry().get("v1") == BUILTIN_V1


def test_active_is_v2_with_conflict_handling() -> None:
    # v2 was promoted (MISSION-033): it adds conflicting-sources handling to v1's prompt.
    reg = default_registry()
    assert reg.active_version() == "v2"
    v2 = reg.get("v2")
    assert active_prompt_config() == v2
    assert "conflict" in v2.generate_system.lower()
    # only the generate prompt changed vs v1; judge + notice + model are identical
    assert v2.judge_system == BUILTIN_V1.judge_system
    assert v2.not_certified_notice == BUILTIN_V1.not_certified_notice
    assert v2.generate_system != BUILTIN_V1.generate_system


def test_content_hash_is_version_independent_and_content_sensitive() -> None:
    same_text = _builtin_variant("v2")  # identical text, different version
    assert same_text.content_hash() == BUILTIN_V1.content_hash()
    changed = _builtin_variant("v3", judge_system="different judge")
    assert changed.content_hash() != BUILTIN_V1.content_hash()


# --- activate / rollback (AC4) --------------------------------------------


def test_activate_and_rollback_roundtrip(tmp_path) -> None:
    reg = _seed(tmp_path)
    assert reg.active().version == "v1"
    reg.activate("v2")
    assert reg.active().generate_system == "v2 system prompt"
    reg.activate("v1")  # rollback — artifacts are immutable, always reversible
    assert reg.active() == BUILTIN_V1


def test_unknown_version_raises(tmp_path) -> None:
    reg = _seed(tmp_path)
    with pytest.raises(PromptConfigError):
        reg.get("nope")


def test_missing_active_pointer_raises(tmp_path) -> None:
    reg = PromptRegistry(tmp_path)
    reg.write(BUILTIN_V1)
    with pytest.raises(PromptConfigError):
        reg.active_version()


# --- promotion gate (AC3) -------------------------------------------------


_GOOD_AGG = {
    "recall_at_k_mean": 0.8,
    "citation_grounding_coverage_mean": 0.97,
    "behavior_conformity": 1.0,
}


def test_evaluate_gates_requires_evidence_and_floors() -> None:
    # no eval aggregate -> retrieval/groundedness fail even if safety passes
    g = evaluate_gates(None, safety_passed=True)
    assert not g.passed and not g.retrieval and not g.groundedness and g.safety

    # good aggregate + safety -> all pass
    assert evaluate_gates(_GOOD_AGG, safety_passed=True).passed

    # weak retrieval -> retrieval gate fails
    weak = {**_GOOD_AGG, "recall_at_k_mean": 0.1}
    assert not evaluate_gates(weak, safety_passed=True).retrieval

    # safety failing -> blocked regardless of quality
    assert not evaluate_gates(_GOOD_AGG, safety_passed=False).passed


def test_promote_blocked_when_gates_fail(tmp_path) -> None:
    reg = _seed(tmp_path)
    pub = _RecordingPublisher()
    failing = GateResult(retrieval=True, groundedness=True, safety=False, details={})
    with pytest.raises(PromotionBlockedError):
        reg.promote("v2", gates=failing, publisher=pub)
    assert reg.active_version() == "v1"  # unchanged
    assert pub.published == []  # never synced on a blocked promotion


def test_promote_activates_and_syncs_when_gates_pass(tmp_path) -> None:
    reg = _seed(tmp_path)
    pub = _RecordingPublisher()
    gates = evaluate_gates(_GOOD_AGG, safety_passed=True)
    reg.promote("v2", gates=gates, publisher=pub, label="production")
    assert reg.active_version() == "v2"
    assert pub.published == [("v2", "production")]  # synced to the prompt backend (AC1)
