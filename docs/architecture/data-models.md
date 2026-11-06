# Data Models

_Sharded from `../architecture.md`. Part of the [architecture index](./index.md)._

Canonical entities (fields summarized; full column definitions live in migrations). Every tenant-owned entity carries `tenant_id` and is tenant-scoped by the repository layer.

| Entity                            | Key fields                                                            | Relationships                        |
| --------------------------------- | --------------------------------------------------------------------- | ------------------------------------ |
| **Tenant**                  | id, name, configuration, policies                                     | 1—N User, Document, Equipment       |
| **User**                    | id, tenant_id, role, account_status                                   | N—1 Tenant                          |
| **Equipment**               | id, tenant_id, manufacturer, model, version/revision, asset_id        | N—M Document                        |
| **Document**                | id, tenant_id, title, source, type, rights/license                    | 1—N DocumentVersion; N—M Equipment |
| **DocumentVersion**         | id, document_id, revision, publication_date, effective_date, checksum | 1—N Section                         |
| **Section**                 | id, document_version_id, hierarchy, heading, page_range               | 1—N Chunk                           |
| **Chunk**                   | id, section_id, content, page_range, metadata                         | 1—1 Embedding                       |
| **Embedding**               | id, chunk_id, model_version, vector (pgvector)                        | N—1 Chunk                           |
| **IngestionJob**            | id, tenant_id, source, state, timestamps, error_info                  | —                                   |
| **QueryTrace**              | id, tenant_id, user_id, retrieval_ids, model, latency, cost           | —                                   |
| **EvaluationCase**          | id, dataset, question, relevant_evidence, expected_behavior           | —                                   |
| **AuditEvent**              | id, tenant_id, actor, operation, resource, timestamp                  | —                                   |
| **Conversation / Feedback** | id, tenant_id, user_id, messages, citations, rating, flags            | N—1 User                            |

**Design rule:** raw files, cleaned content, `DocumentVersion`, search index, and `Embedding` are stored so any one can be rebuilt from upstream without losing the others (NFR15).
