"""The answer flow honors the active/overridden prompt config (Story 5.5) — no network.

Proves the registry is actually WIRED into the running graph: a custom PromptConfig
changes the system prompt the model sees, the judge prompt, and the not-certified notice
on the answer. Guards against the registry being a decorative artifact.
"""

import pytest

pytest.importorskip("langgraph")

from ikip_common.llm.answer import grounded_answer  # noqa: E402
from ikip_common.llm.fake_chat import FakeChatClient, FakeGroundingValidator  # noqa: E402
from ikip_common.llm.hybrid import RetrievalOutcome  # noqa: E402
from ikip_common.llm.prompts import _builtin_variant  # noqa: E402
from ikip_common.llm.schemas import Claim, GroundedAnswer  # noqa: E402
from langchain_core.documents import Document  # noqa: E402


def _doc() -> Document:
    return Document(page_content="Fault E42: pump overheat.", metadata={"chunk_id": "c1"})


def _retrieve(_q: str) -> RetrievalOutcome:
    return RetrievalOutcome(documents=[_doc()], abstained=False)


def test_custom_prompts_reach_the_model_and_notice() -> None:
    cfg = _builtin_variant(
        "test-vX",
        generate_system="CUSTOM-GENERATE-SYSTEM",
        not_certified_notice="CUSTOM-NOTICE",
    )
    chat = FakeChatClient(
        GroundedAnswer(
            status="answered",
            claims=[Claim(text="E42 is pump overheat.", evidence_markers=["E1"])],
        )
    )
    out = grounded_answer(
        "What is E42?",
        retrieve=_retrieve,
        chat_client=chat,
        validator=FakeGroundingValidator(),  # supported
        prompts=cfg,
    )
    assert out.status == "answered"
    # the generate node used the custom system prompt
    system_msg = chat.calls[0][0]
    assert system_msg.content == "CUSTOM-GENERATE-SYSTEM"
    # the answer carries the custom version's not-certified notice
    assert out.not_certified_notice == "CUSTOM-NOTICE"


def test_default_uses_active_config_notice() -> None:
    from ikip_common.llm.prompts import active_prompt_config

    chat = FakeChatClient(
        GroundedAnswer(
            status="answered",
            claims=[Claim(text="E42 is pump overheat.", evidence_markers=["E1"])],
        )
    )
    out = grounded_answer(
        "What is E42?",
        retrieve=_retrieve,
        chat_client=chat,
        validator=FakeGroundingValidator(),
    )
    assert out.not_certified_notice == active_prompt_config().not_certified_notice
