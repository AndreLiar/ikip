# MISSION-010 — Reproduction tutorial

Add document dedup + versioning to the data layer.

## Prerequisites
- MISSIONs 001–009; Neon dev branch; `uv`.

## Steps

1. **Models** (`db/models.py`) — `Document(UUIDPrimaryKey, TenantScoped, Timestamped, Base)` with `title/source/type/rights/content_fingerprint(indexed)`; `DocumentVersion(UUIDPrimaryKey, Timestamped, Base)` with `document_id(FK)`, `revision`, `checksum(indexed)`, `publication_date/effective_date`, `is_current(indexed)`, `curated_object_key`; `UniqueConstraint(document_id, revision)`.

2. **SimHash** (`db/similarity.py`) — `simhash(text)` (shingle each 3-word window, hash, vote per bit → 64-bit hex), `hamming_distance(a,b)`, `is_near_duplicate(a,b,max_distance=3)`.

3. **Repository** (`db/documents.py`) — `DocumentRepository(TenantScopedRepository[Document])`:
   - `find_by_checksum` (join version), `find_near_duplicate` (scan tenant docs by Hamming), `current_version`.
   - `ingest_version(...)`: raise `DuplicateDocumentError` on exact; near-dup → `_add_version` on the existing doc; else create doc + version.
   - `_add_version`: flip previous current `is_current=False` (keep it), insert new `is_current=True`.

4. **Migration** (DB must be at head first)
   ```bash
   cd packages/common
   uv run --project ../.. alembic upgrade head
   uv run --project ../.. alembic revision --autogenerate -m "add document and document_version"
   uv run --project ../.. alembic upgrade head
   uv run --project ../.. alembic downgrade -1 && uv run --project ../.. alembic upgrade head   # reversible
   ```

5. **Tests**
   ```bash
   uv run pytest apps packages services -q                 # SimHash runs; DB tests skip
   TEST_DATABASE_URL=<branch> uv run pytest packages/common/tests/test_documents.py -q
   ```
   Cover: new doc, exact-dup reject, near-dup supersession (both kept), unrelated → new doc, tenant-scoped.

## Common mistakes
- **Plain hash for "similar"** → use SimHash; one byte changes a normal hash entirely.
- **Deleting old versions** → flip `is_current`, keep the row (NFR15).
- **Autogenerate recreates all tables** → your DB wasn't at the right baseline; and orphaned enum types block re-upgrade. Reset drops tables **and** enum types.
- **Cross-tenant dedup** → do lookups through the tenant-scoped repo.

## Recovery
Additive; revert branch/commit. `alembic downgrade -1` removes the two tables. If the dev DB gets into a broken enum state: drop tables + enum types, re-apply the chain.
