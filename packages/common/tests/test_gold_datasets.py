"""Gold evaluation datasets (Story 5.1) — pure, no network.

Asserts the failure-mode dataset is well-formed and covers the required modes (AC1), each
case specifies question/evidence/expected behavior incl. abstention (AC2), and it is
versioned (AC3). Loadable by the documented `eval` command's gold loader (AC4).
"""

from __future__ import annotations

import json
from pathlib import Path

_FIXTURES = Path(__file__).parent / "fixtures" / "gold"
_REQUIRED_MODES = {
    "equipment_identifier",
    "outdated_manual",
    "conflicting_sources",
    "unanswerable",
    "table",
    "scanned_pdf",
    "malicious_document",
}


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text())


def test_failure_modes_dataset_covers_required_modes() -> None:
    doc = _load("failure_modes.json")
    assert doc["gold_set_version"]  # AC3: versioned
    categories = {c["category"] for c in doc["cases"]}
    assert _REQUIRED_MODES <= categories, f"missing modes: {_REQUIRED_MODES - categories}"


def test_every_case_is_well_formed_incl_abstention() -> None:
    doc = _load("failure_modes.json")
    behaviors = set()
    for c in doc["cases"]:
        assert c["case_key"] and c["question"] and c["category"]
        assert c["expected_behavior"] in {"answered", "abstained"}  # AC2
        if c["expected_behavior"] == "answered":
            assert c["relevant_chunk_ids"], f"{c['case_key']} answers but cites no evidence"
        behaviors.add(c["expected_behavior"])
    assert behaviors == {"answered", "abstained"}  # both represented (incl. abstention)


def test_loadable_by_eval_gold_loader() -> None:
    # the documented command (`python -m ikip_common.eval run --gold <file>`) uses this loader
    from ikip_common.eval.__main__ import _load_gold

    version, cases = _load_gold(str(_FIXTURES / "failure_modes.json"))
    assert version == "failure-modes-v1"
    assert len(cases) >= 7
    malicious = [c for c in cases if c.category == "malicious_document"]
    assert malicious and malicious[0].expected_behavior == "abstained"
    assert any(c.ground_truth for c in cases)  # Ragas reference answers present
