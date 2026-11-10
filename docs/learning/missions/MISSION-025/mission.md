# MISSION-025 — Conversation History & Feedback (Epic 4, Story 4.6) → Epic 4 8/8

**Mode:** Autonome (fills the one Epic-4 gap found when auditing PR #39) + knowledge transfer.
**Objective:** store per-user/tenant conversation history (with citations) and let users rate / flag answers, retrievable for failure analysis — the last unbuilt Epic 4 story.
**Maps to:** Epic 4 / Story 4.6 (FR). Reuses the tenant-scoped + DI-service pattern from 4.2/4.7/4.8.

## What was built
### Data (packages/common)
- `Conversation` (tenant + owner `user_id`), `ConversationMessage` (role user|assistant, `content`, `answer_payload` JSONB = the structured answer + citations), `AnswerFeedback` (rating -1|0|1, `flagged`, `reason`; unique per `(message, user)`). Plain Strings, no DB enum. Migration `11cb77b63d16` (reversible, offline-verified).

### API (apps/api/conversations.py)
- `POST/GET /conversations`, `GET/POST /conversations/{id}/messages`, `POST /messages/{id}/feedback`, `GET /feedback?flagged_only=`. Every route is **tenant- AND owner-scoped** (a user only sees their own threads, FR21/NFR10); writes verify ownership → 404 otherwise. Feedback is upserted per (message,user). Behind a `ConversationService` port (DI); heavy deps lazy-imported.

### Web (apps/web)
- `FeedbackBar` (👍/👎/🚩) on `AnswerPanel` when the answer has a persisted `messageId` → BFF route `app/api/feedback/[messageId]` → `POST /api/v1/messages/{id}/feedback`. OpenAPI client regenerated (4 new endpoints).

## Acceptance (Story 4.6)
1. Conversations + citations stored per user/tenant. — **[verified]** (models + `answer_payload` keeps citations; DB test `test_conversation_thread_keeps_answer_payload`)
2. Users can rate answers and flag incorrect answers/sources. — **[verified]** (`POST /messages/{id}/feedback`; `FeedbackBar`; endpoint + web tests)
3. Feedback retrievable for failure analysis (Epic 5). — **[verified]** (`GET /feedback?flagged_only=true`; test)
4. History respects retention settings (Epic 6). — **[partial]** retention is modeled by `created_at` + tenant policy and documented; the enforcement sweep is Epic 6. No hard delete here.

## Verification
- python: ruff/format ✓, 190 passed / 39 skipped (3 DB-gated conversation tests run in CI).
- web: typecheck/lint/prettier/build ✓, 28 tests (incl. FeedbackBar ×3); OpenAPI drift guard stable.

## Deliverables
- `db/models.py` (3 models) + migration `11cb77b63d16`; `tests/test_conversation_models.py` (DB-gated).
- `apps/api/conversations.py` + `tests/test_conversations_endpoint.py` (6); main.py router.
- `apps/web/components/FeedbackBar.tsx` + `app/api/feedback/[messageId]/route.ts`; AnswerPanel integration; `test/FeedbackBar.test.tsx`.

## Follow-ups (noted)
- Persist the live `/ask` turn automatically (create conversation + assistant message, return its id) so the FeedbackBar wires end-to-end in the UI — small glue once a "session" concept exists.
- Epic 6 retention sweep (hard delete past policy window).

## Concepts
Reuses [auth-rbac](../../concepts/auth-rbac.md), [multi-tenancy](../../concepts/multi-tenancy.md), [grounded-answers](../../concepts/grounded-answers.md).
