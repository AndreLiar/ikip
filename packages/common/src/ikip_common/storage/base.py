"""ObjectStorage port (Story 2.1, ADR 0003).

Abstract interface for blob storage. The default adapter is Cloudflare R2
(S3-compatible, ADR 0014); MinIO/local can back the same port for offline tests,
and tests mock it so CI needs no live R2. Artifact tiers (raw/cleaned/curated)
are logically separated via key prefixes (NFR15).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable


class ArtifactTier(StrEnum):
    """Logical separation of stored artifacts (NFR15). Used as a key prefix."""

    raw = "raw"
    cleaned = "cleaned"
    curated = "curated"


@runtime_checkable
class ObjectStorage(Protocol):
    """Blob storage port. Keys are tier-prefixed by the caller via `tier_key`."""

    def put(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        """Store bytes at `key`; return the stored key."""
        ...

    def get(self, key: str) -> bytes:
        """Return the bytes at `key` (raises if absent)."""
        ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None:
        """Delete `key` (used by the retention workflow, Story 6.5)."""
        ...

    def presigned_url(self, key: str, *, expires_s: int = 3600) -> str:
        """Short-lived URL to read `key` directly (document viewer, FR23)."""
        ...


def tier_key(tier: ArtifactTier, *parts: str) -> str:
    """Build a tier-prefixed object key, e.g. tier_key(raw, tenant, doc) -> 'raw/tenant/doc'."""
    return "/".join([tier.value, *parts])
