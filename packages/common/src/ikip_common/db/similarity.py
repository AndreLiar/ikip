"""Content fingerprinting for near-duplicate detection (Story 2.5). Pure.

- Exact duplicates are caught by `checksum` (sha256) — different story path.
- Near-duplicates (a manual re-exported, minor edits) share most content but not
  the exact bytes. We use a 64-bit **SimHash** over token shingles: similar text
  -> small Hamming distance between fingerprints.

Fingerprints are hex strings stored on `Document.content_fingerprint`; two docs
are near-duplicates if their Hamming distance <= `NEAR_DUP_MAX_DISTANCE`.
"""

from __future__ import annotations

import hashlib
import re

_HASH_BITS = 64
_TOKEN_RE = re.compile(r"\w+")
# Max differing bits (out of 64) to still count as a near-duplicate. Tunable.
NEAR_DUP_MAX_DISTANCE = 3


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _feature_hashes(text: str, shingle: int = 3) -> list[int]:
    toks = _tokens(text)
    if len(toks) < shingle:
        shingles = [" ".join(toks)] if toks else []
    else:
        shingles = [" ".join(toks[i : i + shingle]) for i in range(len(toks) - shingle + 1)]
    out = []
    for sh in shingles:
        h = int.from_bytes(hashlib.sha1(sh.encode()).digest()[:8], "big")
        out.append(h)
    return out


def simhash(text: str) -> str:
    """Return a 64-bit SimHash of `text` as a zero-padded hex string."""
    vector = [0] * _HASH_BITS
    feats = _feature_hashes(text)
    if not feats:
        return "0" * (_HASH_BITS // 4)
    for h in feats:
        for b in range(_HASH_BITS):
            vector[b] += 1 if (h >> b) & 1 else -1
    fingerprint = 0
    for b in range(_HASH_BITS):
        if vector[b] > 0:
            fingerprint |= 1 << b
    return f"{fingerprint:0{_HASH_BITS // 4}x}"


def hamming_distance(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def is_near_duplicate(a: str, b: str, *, max_distance: int = NEAR_DUP_MAX_DISTANCE) -> bool:
    return hamming_distance(a, b) <= max_distance
