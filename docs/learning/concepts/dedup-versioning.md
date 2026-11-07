# Concept — Deduplication & document versioning

_Write-once concept note. First used by [MISSION-010](../missions/MISSION-010/mission.md). Reused wherever documents enter the knowledge base._

## Why this stage exists
The same manual gets re-ingested, re-exported, lightly edited. Without dedup you'd index the same content many times (noise, cost, contradictory hits). Without versioning you'd lose the fact that "revision B supersedes A" — which is central to IKIP's **version-aware retrieval** (serve the applicable revision, FR14). So each incoming document is checked for duplicates and either **rejected**, folded into an **existing document as a new version**, or stored as a **new document**.

## Two kinds of duplicate (different tools)
| Kind | Detection | Example |
|---|---|---|
| **Exact** | **checksum** (sha256 of bytes) — identical files | the same PDF uploaded twice |
| **Near** | **SimHash** fingerprint + Hamming distance | a manual re-exported, a few edited lines |

- **Exact** is cheap and certain: same checksum → duplicate → skip.
- **Near** needs a *fuzzy* signal. A plain hash changes completely on one byte, so it's useless here. **SimHash** maps similar text to *similar* 64-bit fingerprints: small edits → small **Hamming distance** (differing bits). Two docs within a threshold (e.g. ≤ 3 bits) are near-duplicates.

### How SimHash works (short)
Tokenize → make overlapping **shingles** (3-word windows) → hash each → for each of 64 bit positions, add +1/−1 depending on the bit → the sign of each position gives the final fingerprint bit. Shared shingles dominate the vote, so similar documents converge to similar fingerprints.

## Versioning: supersede, never delete (NFR15)
A `Document` has many `DocumentVersion`s. Adding a version:
1. flips the previous current version's `is_current = False`,
2. inserts the new version with `is_current = True`,
3. **keeps the old version row** (and its curated artifact) — original evidence is preserved so we can reprocess/compare and serve "what was valid then" vs "now".

`(document_id, revision)` is unique; `is_current` is indexed (retrieval filters on it). Hard deletion happens only via the retention workflow (Story 6.5), not here.

## The decision flow (IKIP)
```
incoming (checksum, fingerprint, revision)
  exact dup (checksum exists)?  ── yes ─▶ reject (DuplicateDocumentError)
          │ no
  near dup (fingerprint close to an existing doc)? ── yes ─▶ new VERSION of that doc (supersede)
          │ no
  new DOCUMENT + first version
```

## Tenant isolation still holds
Dedup is **within a tenant**: the same checksum in tenant B is *not* a duplicate of tenant A's — the repository is tenant-scoped, so lookups never cross tenants (NFR10). Tested explicitly.

## Rules to remember
1. Exact dup → checksum; near dup → SimHash + Hamming threshold. Don't use a plain hash for "similar".
2. New version **supersedes** (`is_current` flip), never deletes the old (NFR15).
3. `(document_id, revision)` unique; filter retrieval on `is_current`.
4. Dedup is tenant-scoped.
5. The near-dup threshold is tunable; test with both near and far examples.

## Lesson (ops): migrations leave enum types behind
Resetting a dev DB by dropping tables is **not** enough — Postgres enum **types** persist and a re-`upgrade` fails "type already exists". A broken downgrade can orphan them. Fix: drop the enum types too (and always put the enum-type drop in `downgrade`). Keep a dev-reset that drops tables **and** types.

## Related
- [data-validation](./data-validation.md) (produces curated text to fingerprint) · [multi-tenancy](./multi-tenancy.md) (scoping) · [object-storage](./object-storage.md) (versioned curated artifacts).
- Data model: `docs/architecture/lld/data-schema.md`. Story 2.5; enables version-aware retrieval (Epic 3, FR14).
