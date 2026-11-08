// TypeScript mirror of the FastAPI retrieval/ask contract (apps/api/.../retrieval.py).
// Hand-typed for the walking skeleton; a generated client from the OpenAPI schema
// (Story 4.1) is a follow-up.

export type SearchMode = 'lexical' | 'vector' | 'hybrid';

export interface Citation {
  chunk_id: string | null;
  document_id: string | null;
  document_version_id: string | null;
  revision: string | null;
  is_current: boolean | null;
  section_id: string | null;
  heading: string | null;
  hierarchy_path: string | null;
  page_start: number | null;
  page_end: number | null;
  score: number | null;
}

export interface RetrieveRequest {
  query: string;
  k?: number;
  mode?: SearchMode;
  current_only?: boolean;
  document_type?: string | null;
}

export interface RetrievedChunk {
  content: string;
  citation: Citation;
}

export interface RetrieveResponse {
  abstained: boolean;
  results: RetrievedChunk[];
}

export interface AskRequest {
  query: string;
  equipment_model?: string | null;
  revision?: string | null;
}

export interface AnsweredClaim {
  text: string;
  safety_critical: boolean;
  citations: Citation[];
}

export interface AskResponse {
  status: 'answered' | 'abstained';
  answer: string | null;
  claims: AnsweredClaim[];
  warnings: string[];
  abstention_reason: string | null;
  not_certified_notice: string;
  cache_hit: boolean;
}
