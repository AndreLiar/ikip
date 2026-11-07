# Concept — Object storage (blobs, S3 abstraction, artifact tiers)

_Write-once concept note. First used by [MISSION-006](../missions/MISSION-006/mission.md). Reused whenever files are stored/served._

## What object storage is (and isn't)
Object storage holds **blobs** (files) by **key** (a string path), not rows. It's for large, immutable-ish artifacts: PDFs, extracted text, images. It is **not** a database — no joins, no transactions; you `put`/`get`/`delete` by key and list by prefix. IKIP keeps **files** in object storage (Cloudflare R2) and **metadata** in Postgres (Neon) — each in the tool built for it (NFR15).

## The S3 API as a lingua franca
"S3" is Amazon's object-storage API, now a de-facto standard many providers implement. **Cloudflare R2 is S3-compatible**, so the same client (`boto3`) talks to it by just changing the endpoint + credentials. That's why one adapter covers R2 (prod/dev) and MinIO (local/offline) — same API.

## The port: don't bind to a vendor
IKIP hides storage behind the **`ObjectStorage` port** (a `Protocol`): `put / get / exists / delete / presigned_url`. Core code depends on the port, not boto3/R2 ([ADR 0003](../../adr/0003-local-first-ports-and-adapters.md)). Benefits:
- swap R2 ↔ MinIO ↔ Azure Blob by changing the adapter, not the callers;
- **tests mock the port** (a fake in-memory S3) → hermetic, no live service, no secrets in CI.

```python
class ObjectStorage(Protocol):
    def put(self, key, data, *, content_type=None) -> str: ...
    def get(self, key) -> bytes: ...
    def exists(self, key) -> bool: ...
    def delete(self, key) -> None: ...
    def presigned_url(self, key, *, expires_s=3600) -> str: ...
```

## Artifact tiers via key prefixes (NFR15)
Raw, cleaned and curated artifacts are **logically separated** so reprocessing never destroys original evidence. IKIP does this with a **key prefix** per tier:
`raw/<tenant>/<doc>` · `cleaned/…` · `curated/…` (`ArtifactTier` + `tier_key(...)`). You can reprocess `raw → curated` without touching `raw`.

## Presigned URLs (serving files safely)
To let a browser open a PDF **directly** from storage without proxying it through the API, the server generates a **presigned URL**: a time-limited signed link (`expires_s`). The bucket stays **private**; access is granted per-object, per-request, and expires. This is how the document viewer opens the cited page (FR23) — **after** authorizing the user.

## Rules to remember
1. Files → object storage; metadata/relationships → Postgres. Don't store blobs in the DB.
2. Depend on the `ObjectStorage` port, never on boto3 directly.
3. Separate tiers by prefix; never overwrite `raw`.
4. Buckets are private; serve with short-lived presigned URLs, and authorize first.
5. Keys are not secrets but can leak structure — don't put sensitive data in key names.

## Related
- [ADR 0014](../../adr/0014-cloudflare-r2-object-storage.md) (R2) · [ADR 0003](../../adr/0003-local-first-ports-and-adapters.md) (ports) · [config-12-factor](./config-12-factor.md) (credentials).
- Controlled-storage security (private buckets, presigned, lifecycle): Story 6.4.
