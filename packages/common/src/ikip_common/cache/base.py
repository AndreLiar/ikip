"""Cache port (Story 3.7, ADR 0009).

A small string KV interface with TTL + an atomic counter (for invalidation epochs).
The default adapter is Redis (local Docker ↔ Redis Cloud ↔ Azure Cache — a config
switch, ADR 0003); a `FakeCache` backs the same port for CI with no network. Values
are strings (callers JSON-encode). Keys carry all correctness context (tenant, version
set) — see `cache.keys`; the cache itself is dumb on purpose.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Cache(Protocol):
    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str, *, ttl_s: int | None = None) -> None: ...

    def delete(self, key: str) -> None: ...

    def incr(self, key: str) -> int:
        """Atomically increment an integer counter at `key` (starts at 0); return new value.
        Used for per-tenant invalidation epochs."""
        ...
