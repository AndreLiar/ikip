"""Live Azure grounded-answer test (Story 3.5) — real gpt-5.4-mini, no DB.

Skipped unless AZURE_OPENAI_* (chat) are configured. Exercises the real AzureChatClient
+ LLMGroundingValidator through the LangGraph flow with an in-memory retrieve stub, so
it validates structured output, reasoning_effort and the grounding judge end to end
without touching Postgres. Not in the fast CI `validate` job.
"""

import os

import pytest
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

pytest.importorskip("langgraph")

_CONFIGURED = all(
    os.environ.get(k)
    for k in (
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_API_VERSION",
        "AZURE_OPENAI_CHAT_DEPLOYMENT",
    )
)
pytestmark = pytest.mark.skipif(not _CONFIGURED, reason="AZURE_OPENAI_* chat not configured")


def _retrieve(docs):
    from ikip_common.llm.hybrid import RetrievalOutcome

    return lambda q: RetrievalOutcome(documents=docs, abstained=False)


def _doc(cid, content):
    from langchain_core.documents import Document

    return Document(
        page_content=content,
        metadata={
            "chunk_id": cid,
            "document_id": "d1",
            "document_version_id": "v1",
            "revision": "A",
            "is_current": True,
            "section_id": "s1",
            "heading": "3.2",
            "hierarchy_path": "3.2",
            "page_start": 142,
            "page_end": 142,
        },
    )


def test_live_grounded_answer_with_real_model() -> None:
    from ikip_common.llm import build_chat_client
    from ikip_common.llm.answer import grounded_answer

    docs = [
        _doc("c1", "Fault code E42 indicates the pump motor has overheated. Stop the pump."),
        _doc("c2", "Routine lubrication of bearings every 2000 hours."),
    ]
    chat = build_chat_client()
    out = grounded_answer("What does fault E42 mean?", retrieve=_retrieve(docs), chat_client=chat)

    assert out.status == "answered"
    assert out.claims, "expected at least one grounded claim"
    # every kept claim cites real retrieval metadata (server-resolved, FR16)
    for c in out.claims:
        assert c.citations
        assert all(cit.revision == "A" and cit.page_start == 142 for cit in c.citations)
    assert out.not_certified_notice


def test_live_abstains_on_irrelevant_evidence() -> None:
    from ikip_common.llm import build_chat_client
    from ikip_common.llm.answer import grounded_answer

    docs = [_doc("c1", "Routine lubrication of bearings every 2000 hours.")]
    chat = build_chat_client()
    out = grounded_answer(
        "What is the torque spec for the gearbox housing bolts?",
        retrieve=_retrieve(docs),
        chat_client=chat,
    )
    # evidence doesn't answer the question -> abstain, never invent (AC4)
    assert out.status == "abstained"
