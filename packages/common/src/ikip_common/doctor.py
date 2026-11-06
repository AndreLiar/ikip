"""Connectivity "doctor" (Story 1.2 AC2).

Verifies each configured managed backend and reports pass/fail per service,
WITHOUT printing secrets. Heavy clients are imported lazily (install the
`doctor` extra: `uv sync --extra doctor`); a missing client is reported as
SKIPPED rather than crashing.

Run:  uv run --group doctor python -m ikip_common.doctor
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from ikip_common.config import Settings, get_settings


@dataclass
class CheckResult:
    service: str
    ok: bool | None  # None = skipped
    detail: str

    def line(self) -> str:
        mark = "✅" if self.ok else ("⏭️ " if self.ok is None else "❌")
        return f"{mark} {self.service:<10} {self.detail}"


def _check_postgres(s: Settings) -> CheckResult:
    try:
        import psycopg
    except ImportError:
        return CheckResult("neon", None, "SKIPPED (install doctor extra)")
    try:
        with psycopg.connect(s.database_url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
                cur.execute("SELECT extname FROM pg_extension WHERE extname='vector';")
                has_vec = cur.fetchone() is not None
        return CheckResult("neon", True, f"connected; pgvector={'yes' if has_vec else 'absent'}")
    except Exception as e:  # noqa: BLE001 — surface any connectivity failure
        return CheckResult("neon", False, f"{type(e).__name__}: {e}")


def _check_r2(s: Settings) -> CheckResult:
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        return CheckResult("r2", None, "SKIPPED (install doctor extra)")
    try:
        client = boto3.client(
            "s3",
            endpoint_url=s.r2_endpoint,
            aws_access_key_id=s.r2_access_key_id.get_secret_value(),
            aws_secret_access_key=s.r2_secret_access_key.get_secret_value(),
            region_name=s.r2_region,
            config=Config(signature_version="s3v4"),
        )
        client.list_objects_v2(Bucket=s.r2_bucket, MaxKeys=1)
        return CheckResult("r2", True, f"bucket '{s.r2_bucket}' reachable")
    except Exception as e:  # noqa: BLE001
        return CheckResult("r2", False, f"{type(e).__name__}: {e}")


def _check_redis(s: Settings) -> CheckResult:
    try:
        import redis
    except ImportError:
        return CheckResult("redis", None, "SKIPPED (install doctor extra)")
    try:
        client = redis.from_url(s.redis_url, socket_timeout=10)
        client.ping()
        return CheckResult("redis", True, "PING ok")
    except Exception as e:  # noqa: BLE001
        return CheckResult("redis", False, f"{type(e).__name__}: {e}")


def _check_langfuse(s: Settings) -> CheckResult:
    if s.langfuse_public_key is None or s.langfuse_secret_key is None:
        return CheckResult("langfuse", None, "SKIPPED (keys not set)")
    try:
        import httpx
    except ImportError:
        return CheckResult("langfuse", None, "SKIPPED (install doctor extra)")
    try:
        resp = httpx.get(
            f"{s.langfuse_host}/api/public/health",
            auth=(
                s.langfuse_public_key.get_secret_value(),
                s.langfuse_secret_key.get_secret_value(),
            ),
            timeout=10,
        )
        ok = resp.status_code < 400
        return CheckResult("langfuse", ok, f"HTTP {resp.status_code}")
    except Exception as e:  # noqa: BLE001
        return CheckResult("langfuse", False, f"{type(e).__name__}: {e}")


def run_checks(settings: Settings | None = None) -> list[CheckResult]:
    s = settings or get_settings()
    return [_check_postgres(s), _check_r2(s), _check_redis(s), _check_langfuse(s)]


def main() -> int:
    print("IKIP connectivity doctor")
    print("-" * 50)
    results = run_checks()
    for r in results:
        print(r.line())
    print("-" * 50)
    failed = [r for r in results if r.ok is False]
    print("RESULT:", "ALL OK ✅" if not failed else f"{len(failed)} FAILED ❌")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
