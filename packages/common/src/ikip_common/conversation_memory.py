"""Conversational memory in the loop — query contextualization (ADR 0032 layer 1).

A follow-up like "and Q2?" or "what about the second one?" is unsearchable alone: its meaning
lives in the prior turns. This folds the recent thread (`ConversationMessage` history) + the
follow-up into a **standalone search query** (resolve pronouns/ellipsis) BEFORE retrieval.

Grounding-safe by construction: it rewrites only the *retrieval query* — generation still answers
the user's original question over the retrieved evidence, and memory is never passed as evidence
(ADR 0032: memory serves retrieval, never the answer). Falls back to the original question on any
failure. LLM call via the `ChatClient` port (FakeChatClient in CI).
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from ikip_common.llm.base import ChatClient, ChatMessage

_SYSTEM = (
    "You rewrite the user's latest message into ONE self-contained search query, using the prior "
    "conversation to resolve pronouns, ellipsis and references ('it', 'that one', 'and Q2?'). "
    "Preserve the intent exactly; add only context needed to make the query stand alone; do not "
    "answer it and do not invent facts. If the message is already self-contained, return it as is."
)

# Default number of prior (user, assistant) turns to fold in — enough for reference resolution,
# bounded to keep the prompt small + the signal recent.
DEFAULT_MAX_TURNS = 4


class StandaloneQuery(BaseModel):
    query: str


def _history_block(history: Sequence[tuple[str, str]]) -> str:
    lines = []
    for user_msg, assistant_msg in history:
        lines.append(f"User: {user_msg}")
        if assistant_msg:
            lines.append(f"Assistant: {assistant_msg}")
    return "\n".join(lines)


def contextualize_query(
    chat_client: ChatClient,
    question: str,
    history: Sequence[tuple[str, str]],
    *,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> str:
    """Fold the recent thread + the follow-up into a standalone retrieval query. Returns the
    original question unchanged when there is no history, or on any failure (retrieval never
    breaks)."""
    if not history:
        return question
    recent = list(history)[-max_turns:]
    try:
        out = chat_client.complete_structured(
            [
                ChatMessage(role="system", content=_SYSTEM),
                ChatMessage(
                    role="user",
                    content=(
                        f"Conversation so far:\n{_history_block(recent)}\n\n"
                        f"Latest message: {question}\n\nSelf-contained search query:"
                    ),
                ),
            ],
            StandaloneQuery,
        )
        return (out.query or "").strip() or question
    except Exception:  # noqa: BLE001 — retrieval must never break on a contextualization failure
        return question
