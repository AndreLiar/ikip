"""Exact-match answer cache (Story 3.7 layer 4, ADR 0009).

Caches a full `AnswerResult` under a key that is tenant-partitioned and encodes
equipment model + revision + the current document-version set (`cache.keys.answer_key`)
plus a per-tenant invalidation epoch. So:
  - a hit NEVER crosses tenants (NFR10);
  - a superseded version yields a different key → an obsolete answer is never served (FR14);
  - a hit returns the SAME result a cold run produced — including an abstention (AC5):
    abstained answers are cached and replayed identically, never silently "answered".

Fuzzy/semantic matching is out of scope (deferred). This module is heavy (imports the
grounded-answer graph); the cache port + keys stay light in `ikip_common.cache`.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterable

from ikip_common.cache.base import Cache
from ikip_common.cache.keys import answer_key, current_answer_epoch
from ikip_common.llm.answer import (
    AnsweredClaim,
    AnswerResult,
    ResolvedCitation,
    grounded_answer,
)
from ikip_common.llm.base import ChatClient
from ikip_common.llm.grounding import GroundingValidator
from ikip_common.llm.hybrid import RetrievalOutcome

DEFAULT_TTL_S = 3600


def _serialize(result: AnswerResult) -> str:
    return json.dumps(
        {
            "status": result.status,
            "answer": result.answer,
            "warnings": result.warnings,
            "abstention_reason": result.abstention_reason,
            "not_certified_notice": result.not_certified_notice,
            "claims": [
                {
                    "text": c.text,
                    "safety_critical": c.safety_critical,
                    "verdict": c.verdict,
                    "citations": [vars(cit) for cit in c.citations],
                }
                for c in result.claims
            ],
        }
    )


def _deserialize(payload: str) -> AnswerResult:
    d = json.loads(payload)
    claims = [
        AnsweredClaim(
            text=c["text"],
            safety_critical=c["safety_critical"],
            verdict=c["verdict"],
            citations=[ResolvedCitation(**cit) for cit in c["citations"]],
        )
        for c in d["claims"]
    ]
    return AnswerResult(
        status=d["status"],
        answer=d["answer"],
        claims=claims,
        warnings=d["warnings"],
        abstention_reason=d["abstention_reason"],
        not_certified_notice=d["not_certified_notice"],
    )


def cached_grounded_answer(
    question: str,
    *,
    cache: Cache,
    tenant_id: uuid.UUID,
    current_version_ids: Iterable[str],
    retrieve: Callable[[str], RetrievalOutcome],
    chat_client: ChatClient,
    validator: GroundingValidator | None = None,
    equipment_model: str | None = None,
    revision: str | None = None,
    ttl_s: int = DEFAULT_TTL_S,
) -> tuple[AnswerResult, bool]:
    """Return (result, cache_hit). On miss, run the grounded-answer graph and store the
    result (including abstentions) under a tenant/version-aware key."""
    epoch = current_answer_epoch(cache, tenant_id)
    key = answer_key(
        tenant_id,
        question,
        equipment_model=equipment_model,
        revision=revision,
        current_version_ids=current_version_ids,
        epoch=epoch,
    )
    hit = cache.get(key)
    if hit is not None:
        return _deserialize(hit), True

    result = grounded_answer(
        question, retrieve=retrieve, chat_client=chat_client, validator=validator
    )
    cache.set(key, _serialize(result), ttl_s=ttl_s)
    return result, False
