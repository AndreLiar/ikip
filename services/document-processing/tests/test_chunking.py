"""Structure-aware chunking tests (Story 3.1, ADR 0019). Pure."""

from ikip_docproc.chunking import (
    chunk_document,
    chunk_regions,
    estimate_tokens,
    is_low_signal,
)


def test_chunks_follow_sections() -> None:
    text = (
        "3.1 Installation\n\n"
        "Mount the unit on the DIN rail and connect the supply.\n\n"
        "3.2 Fault Handling\n\n"
        "When fault code E42 appears, de-energize before servicing."
    )
    chunks = chunk_document(text)
    # one chunk per (short) section, each tagged with its heading
    headings = [c.section_heading for c in chunks]
    assert "3.1 Installation" in headings
    assert "3.2 Fault Handling" in headings
    # content stays within its section
    e42 = next(c for c in chunks if "E42" in c.content)
    assert e42.section_heading == "3.2 Fault Handling"


def test_long_section_is_subsplit_with_overlap() -> None:
    long_body = " ".join(
        f"Sentence number {i} about the maintenance procedure." for i in range(200)
    )
    text = f"5. Procedure\n\n{long_body}"
    chunks = chunk_document(text, max_tokens=100, overlap_tokens=20)
    assert len(chunks) > 1  # sub-split happened
    assert all(c.token_count <= 130 for c in chunks)  # bounded (+ small overlap)
    # overlap: the end of one chunk reappears at the start of the next
    joined = [c.content for c in chunks]
    assert any(
        joined[i].split()[-3:] == joined[i + 1].split()[:3]
        or set(joined[i].split()) & set(joined[i + 1].split())
        for i in range(len(joined) - 1)
    )


def test_each_chunk_has_ordinal_and_section_path() -> None:
    text = (
        "1. Alpha\n\nThe alpha subsystem controls the primary supply loop.\n\n"
        "2. Beta\n\nThe beta subsystem monitors the downstream pressure gauge."
    )
    chunks = chunk_document(text)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    assert all(c.section_path for c in chunks)


def test_degenerate_chunks_are_dropped() -> None:
    # Low-signal pieces (short title scrap + raw numeric table) never become chunks,
    # while real prose in the same document is kept. Dropped pieces leave no ordinal gap.
    text = (
        "1. Procedure\n\nDe-energize the unit and verify the lockout before servicing.\n\n"
        "TM-4_I-TWA\n\n"
        "0.000000E+00 -0.763068E-02 0.114000E+01 0.000000E+00 -0.763068E-02 0.114000E+01"
    )
    chunks = chunk_document(text)
    assert all("De-energize" in c.content for c in chunks)
    assert all("0.000000E+00" not in c.content for c in chunks)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_is_low_signal() -> None:
    assert is_low_signal("")  # empty
    assert is_low_signal("TM-4_I-TWA")  # short OCR title scrap
    assert is_low_signal("TECHNICAL\nMANUAL")  # too few words / too short
    assert is_low_signal("0.000000E+00 -0.763068E-02 0.114000E+01 0.0 -0.76 1.14")  # numeric table
    assert not is_low_signal(
        "De-energize the unit and verify the lockout before servicing the valve."
    )  # real procedure prose
    assert not is_low_signal(
        "L'assureur garantit le paiement des sommes dues au bénéficiaire désigné."
    )  # FR prose with accents


def test_empty_text_yields_no_chunks() -> None:
    assert chunk_document("") == []
    assert chunk_document("   \n\n  ") == []


def test_estimate_tokens() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1  # ~4 chars/token


def test_pdf_region_chunk_retains_page_and_normalized_bbox() -> None:
    chunks = chunk_regions(
        [
            {
                "page": 7,
                "text": "Fault E42 reset procedure: de-energize the unit before clearing the code.",
                "bbox": [0.1, 0.2, 0.8, 0.3],
            }
        ]
    )
    assert len(chunks) == 1
    assert chunks[0].page_start == chunks[0].page_end == 7
    assert chunks[0].regions == [{"page": 7, "bbox": [0.1, 0.2, 0.8, 0.3]}]
