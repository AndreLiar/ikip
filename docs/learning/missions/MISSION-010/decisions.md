# MISSION-010 — Decisions

## D1 — Exact (checksum) + near (SimHash) dedup
- **Choice:** checksum (sha256) for exact; 64-bit SimHash + Hamming distance for near.
- **Why here:** a plain hash can't detect "similar" (one byte changes everything); SimHash gives small distance for small edits. Catches re-exports/minor-edit re-uploads.
- **Alternative:** MinHash/Jaccard shingles, or an embedding-cosine threshold.
- **Trade-off:** SimHash is cheap + storable as a short fingerprint; less precise than embedding similarity (fine here — real dup decisions, not ranking).
- **Switch when:** near-dup accuracy matters more → use embeddings (already computed in Epic 3) for the similarity check.

## D2 — New version supersedes; never delete (NFR15)
- **Choice:** `_add_version` flips the previous current version's `is_current=False` and keeps it; inserts the new version `is_current=True`.
- **Why here:** version-aware retrieval (FR14) needs "applicable vs obsolete"; preserving old versions keeps original evidence and enables reprocessing/compare. Hard delete only via retention (Story 6.5).

## D3 — Near-dup → new VERSION of the matched document
- **Choice:** if an incoming doc is near a tenant document, attach it as a new version rather than a new document.
- **Why here:** that's the semantics of "a revised manual" — same logical doc, new revision.
- **Trade-off:** a false near-match would wrongly merge two docs; threshold is conservative (≤3 bits) and tunable.

## D4 — Dedup scoped to the tenant
- **Choice:** checksum/fingerprint lookups go through the tenant-scoped repository.
- **Why here:** the same file across two customers is not a cross-tenant duplicate (NFR10). Tested.

## D5 — Reversible migration; dev-reset drops enum TYPES too
- **Bug hit:** a broken `downgrade` left orphaned Postgres enum types; re-`upgrade` failed "type already exists", and autogenerate then diffed against an empty DB and produced a migration recreating all tables.
- **Fix:** reset dev by dropping tables **and** enum types, re-apply the chain to the correct baseline, then autogenerate. Always drop enum types in `downgrade`.
- **Lesson:** `DROP TABLE` ≠ clean slate in Postgres with enums.
