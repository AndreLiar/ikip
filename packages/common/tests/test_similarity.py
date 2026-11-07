"""SimHash near-duplicate tests (Story 2.5). Pure — no DB."""

from ikip_common.db.similarity import hamming_distance, is_near_duplicate, simhash


def test_identical_text_same_fingerprint() -> None:
    t = "Maintenance procedure for pump S7-1500 fault code E42."
    assert simhash(t) == simhash(t)
    assert hamming_distance(simhash(t), simhash(t)) == 0


def test_minor_edit_is_near_duplicate() -> None:
    a = "Maintenance procedure for pump S7-1500 fault code E42. " * 5
    b = a + "Updated footer note added in revision B."  # small change
    assert is_near_duplicate(simhash(a), simhash(b))


def test_different_text_not_near_duplicate() -> None:
    a = "Installation guide for the Schneider breaker, torque specifications."
    b = "Troubleshooting ABB drive fault codes and reset procedures entirely."
    assert not is_near_duplicate(simhash(a), simhash(b))


def test_fingerprint_is_16_hex_chars() -> None:
    fp = simhash("anything")
    assert len(fp) == 16
    int(fp, 16)  # valid hex
