"""Redis adapter for the Cache port (Story 3.7, ADR 0009).

Lazy-imports `redis` (like boto3 in the R2 adapter) so the core package stays light.
Backend URL comes from Settings (`REDIS_URL`) — local Docker Redis, Redis Cloud, or
Azure Cache; a config switch, no code coupling. Same Redis also backs the JobQueue
(ADR 0003); keys here are namespaced by `cache.keys` so they never collide.
"""

from __future__ import annotations

from typing import Any

from ikip_common.config import Settings, get_settings


def _make_client(settings: Settings) -> Any:
    import redis

    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


class RedisCache:
    def __init__(self, settings: Settings | None = None, client: Any = None) -> None:
        self._settings = settings or get_settings()
        self._client = client or _make_client(self._settings)

    def get(self, key: str) -> str | None:
        return self._client.get(key)

    def set(self, key: str, value: str, *, ttl_s: int | None = None) -> None:
        self._client.set(key, value, ex=ttl_s)

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def incr(self, key: str) -> int:
        return int(self._client.incr(key))
