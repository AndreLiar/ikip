"""ObjectStorage tests (Story 2.1 AC4). Hermetic: the S3 client is a fake
(moto-free, in-memory), so CI needs no live R2 and no secrets.
"""

import pytest
from botocore.exceptions import ClientError
from ikip_common.storage import ArtifactTier, R2ObjectStorage, tier_key


class FakeS3:
    """Minimal in-memory stand-in for the boto3 S3 client surface we use."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket, Key, Body, **kw):  # noqa: N803
        self.store[(Bucket, Key)] = Body

    def get_object(self, *, Bucket, Key):  # noqa: N803
        if (Bucket, Key) not in self.store:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")

        class _B:
            def __init__(self, b):
                self._b = b

            def read(self):
                return self._b

        return {"Body": _B(self.store[(Bucket, Key)])}

    def head_object(self, *, Bucket, Key):  # noqa: N803
        if (Bucket, Key) not in self.store:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {}

    def delete_object(self, *, Bucket, Key):  # noqa: N803
        self.store.pop((Bucket, Key), None)

    def generate_presigned_url(self, op, *, Params, ExpiresIn):  # noqa: N803
        return f"https://fake/{Params['Bucket']}/{Params['Key']}?exp={ExpiresIn}"


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> R2ObjectStorage:
    for k, v in {
        "DATABASE_URL": "postgresql://u:p@h/db",
        "R2_ACCOUNT_ID": "a",
        "R2_ENDPOINT": "https://a.r2.cloudflarestorage.com",
        "R2_BUCKET": "ikip-test",
        "R2_ACCESS_KEY_ID": "ak",
        "R2_SECRET_ACCESS_KEY": "sk",
        "REDIS_URL": "redis://localhost:6379/0",
        "JWT_SECRET": "x" * 32,
    }.items():
        monkeypatch.setenv(k, v)
    from ikip_common.config import get_settings

    get_settings.cache_clear()
    return R2ObjectStorage(client=FakeS3())


def test_tier_key_prefixes() -> None:
    assert tier_key(ArtifactTier.raw, "tenant", "doc.pdf") == "raw/tenant/doc.pdf"
    assert tier_key(ArtifactTier.curated, "x") == "curated/x"


def test_put_get_roundtrip(storage: R2ObjectStorage) -> None:
    key = tier_key(ArtifactTier.raw, "t1", "a.pdf")
    storage.put(key, b"hello", content_type="application/pdf")
    assert storage.get(key) == b"hello"


def test_exists_and_delete(storage: R2ObjectStorage) -> None:
    key = tier_key(ArtifactTier.raw, "t1", "b.pdf")
    assert storage.exists(key) is False
    storage.put(key, b"x")
    assert storage.exists(key) is True
    storage.delete(key)
    assert storage.exists(key) is False


def test_presigned_url(storage: R2ObjectStorage) -> None:
    url = storage.presigned_url("raw/t1/c.pdf", expires_s=120)
    assert "ikip-test/raw/t1/c.pdf" in url and "exp=120" in url
