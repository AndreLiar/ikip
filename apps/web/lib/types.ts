// Friendly aliases over the OpenAPI-generated schema (lib/api-schema.ts, Story 4.1).
// The schema is generated from the FastAPI contract (`pnpm gen:api`), so these types
// track the API automatically — no hand-maintained drift.

import type { components } from './api-schema';

type Schemas = components['schemas'];

export type Citation = Schemas['Citation'];
export type RetrieveRequest = Schemas['RetrieveRequest'];
export type RetrievedChunk = Schemas['RetrievedChunk'];
export type RetrieveResponse = Schemas['RetrieveResponse'];
export type AskRequest = Schemas['AskRequest'];
export type AnsweredClaim = Schemas['AnsweredClaimOut'];
export type AskResponse = Schemas['AskResponse'];
export type SourceUrlResponse = Schemas['SourceUrlResponse'];

// `mode` is an enum on RetrieveRequest; expose it as a named type for the UI selector.
export type SearchMode = NonNullable<RetrieveRequest['mode']>;
