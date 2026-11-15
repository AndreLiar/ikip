"""Per-corpus faithfulness regression gate tests (ADR 0016). Pure — no network."""

import json
from pathlib import Path

from ikip_common.eval.faithfulness_gate import check_faithfulness, load_floors

_FLOORS = "packages/common/tests/fixtures/eval/faithfulness_floors.json"


def test_passes_when_at_or_above_floor() -> None:
    floors = load_floors(_FLOORS)
    r = check_faithfulness("law_fr-silver-v1", 1.0, floors)
    assert r.passed and r.floor == 0.85
    assert check_faithfulness("law_fr-silver-v1", 0.85, floors).passed  # exactly on the floor


def test_fails_when_below_floor() -> None:
    floors = load_floors(_FLOORS)
    r = check_faithfulness("assurance_fr-silver-v1", 0.70, floors)
    assert not r.passed
    assert "FAIL" in str(r) and "assurance_fr-silver-v1" in str(r)


def test_unknown_version_uses_default_floor() -> None:
    floors = load_floors(_FLOORS)
    r = check_faithfulness("brand-new-corpus", 0.79, floors)
    assert r.floor == floors.default == 0.80
    assert not r.passed


def test_every_known_gold_has_a_floor_at_or_below_its_measured_baseline() -> None:
    # The committed floors must sit BELOW the measured baseline (catch regressions, not noise).
    doc = json.loads(Path(_FLOORS).read_text())
    floors, measured = doc["floors"], doc["measured_baseline"]
    for version, base in measured.items():
        if version.startswith("_"):
            continue
        assert floors[version] <= base, f"{version} floor {floors[version]} above baseline {base}"
