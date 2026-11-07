"""Cache key design (Story 3.7, ADR 0009). Pure — the correctness lives here.

For an answer/retrieval cache the KEY is a correctness feature, not a tuning detail:
  - **tenant-partitioned** → an entry is unreachable from another tenant (NFR10);
  - encodes **equipment model + revision + the current document-version set** →
    a superseded version produces a different key, so an obsolete answer is never
    served (FR14);
  - carries a per-tenant **epoch** so ingestion can invalidate all answers in bulk.

Normalization keeps "same question" stable without crossing semantic boundaries
(fuzzy/semantic matching is explicitly out of scope — deferred, ADR 0009).
"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Iterable

from ikip_common.cache.base import Cache

_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase + collapse whitespace + strip. Deterministic; NOT semantic."""
    return _WS.sub(" ", text.strip().lower())


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def version_fingerprint(current_version_ids: Iterable[str]) -> str:
    """Order-independent fingerprint of the current document-version set. Changes when
    a version is superseded → old answer keys become unreachable."""
    joined = "|".join(sorted(str(v) for v in current_version_ids))
    return _sha(joined) if joined else "none"


def query_embedding_key(query: str, model_version: str) -> str:
    """Layer 2: cache the query's embedding by (normalized query, model_version)."""
    return f"qemb:{model_version}:{_sha(normalize(query))}"


def _epoch_key(tenant_id: uuid.UUID) -> str:
    return f"ansepoch:{tenant_id}"


def current_answer_epoch(cache: Cache, tenant_id: uuid.UUID) -> int:
    raw = cache.get(_epoch_key(tenant_id))
    return int(raw) if raw else 0


def invalidate_tenant_answers(cache: Cache, tenant_id: uuid.UUID) -> int:
    """Bump the tenant's answer epoch → every existing answer key for this tenant
    becomes unreachable. Called by ingestion when a document_version is published."""
    return cache.incr(_epoch_key(tenant_id))


def answer_key(
    tenant_id: uuid.UUID,
    question: str,
    *,
    equipment_model: str | None,
    revision: str | None,
    current_version_ids: Iterable[str],
    epoch: int = 0,
) -> str:
    """Layer 4: exact-match answer cache key. Tenant-partitioned + version-aware + epoch."""
    vfp = version_fingerprint(current_version_ids)
    parts = [
        "ans",
        str(tenant_id),
        str(epoch),
        equipment_model or "-",
        revision or "-",
        vfp,
        _sha(normalize(question)),
    ]
    return ":".join(parts)
