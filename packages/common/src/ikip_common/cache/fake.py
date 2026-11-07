"""In-memory Cache for tests (Story 3.7). Deterministic, no network.

TTL is recorded but not expired by a clock (tests don't need time-travel); `incr`
is atomic enough for a single-threaded test. Enough to exercise key design,
hit/miss, tenant isolation and invalidation.
"""

from __future__ import annotations


class FakeCache:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self.ttls: dict[str, int | None] = {}

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def set(self, key: str, value: str, *, ttl_s: int | None = None) -> None:
        self._store[key] = value
        self.ttls[key] = ttl_s

    def delete(self, key: str) -> None:
        self._store.pop(key, None)
        self.ttls.pop(key, None)

    def incr(self, key: str) -> int:
        new = int(self._store.get(key, "0")) + 1
        self._store[key] = str(new)
        return new
