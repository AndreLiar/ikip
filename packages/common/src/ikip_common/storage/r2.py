"""Cloudflare R2 adapter for the ObjectStorage port (Story 2.1, ADR 0014).

S3-compatible via boto3. Credentials come from Settings (.env / Key Vault) — never
hard-coded. MinIO backs the same S3 API for offline tests by pointing the endpoint
at a local MinIO; tests normally mock the port instead of hitting a live service.
"""

from __future__ import annotations

from typing import Any

from ikip_common.config import Settings, get_settings


def _make_client(settings: Settings) -> Any:
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint,
        aws_access_key_id=settings.r2_access_key_id.get_secret_value(),
        aws_secret_access_key=settings.r2_secret_access_key.get_secret_value(),
        region_name=settings.r2_region,
        config=Config(signature_version="s3v4"),
    )


class R2ObjectStorage:
    """ObjectStorage implementation backed by Cloudflare R2 (S3)."""

    def __init__(self, settings: Settings | None = None, client: Any = None) -> None:
        self._settings = settings or get_settings()
        self._bucket = self._settings.r2_bucket
        self._client = client or _make_client(self._settings)

    def put(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        extra = {"ContentType": content_type} if content_type else {}
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, **extra)
        return key

    def get(self, key: str) -> bytes:
        resp = self._client.get_object(Bucket=self._bucket, Key=key)
        return resp["Body"].read()

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def presigned_url(self, key: str, *, expires_s: int = 3600) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_s,
        )
