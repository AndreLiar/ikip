# LLD — Interface / Port Signatures

_The six infrastructure **ports** (ports & adapters, [ADR 0003](../../adr/0003-local-first-ports-and-adapters.md)). These signatures are the contract core logic depends on; each has a **local** and an **Azure** adapter. Design artifact — the authoritative version lives in `packages/common` at implementation. Signatures only, no bodies (that is adapter implementation)._

Conventions: Python 3.12 `Protocol`s, type hints at boundaries, no provider SDK types in the signatures (NFR12). `UUID`, `Vector = Sequence[float]`.

## ObjectStorage — raw/cleaned/curated artifacts (MinIO ↔ Azure Blob)
```python
class ObjectStorage(Protocol):
    def put(self, key: str, data: bytes, *, content_type: str | None = None) -> str: ...      # returns stored URI
    def get(self, key: str) -> bytes: ...
    def presigned_url(self, key: str, *, expires_s: int = 3600) -> str: ...                      # for the document viewer (FR23)
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...                                                      # retention workflow (Story 6.5)
```

## JobQueue — async ingestion work (Redis ↔ Azure Service Bus)
```python
class JobQueue(Protocol):
    def enqueue(self, topic: str, payload: Mapping[str, Any], *,
                idempotency_key: str | None = None, delay_s: int = 0) -> str: ...                # returns job id
    def consume(self, topic: str, *, group: str) -> Iterator["Job"]: ...
    def ack(self, job: "Job") -> None: ...
    def nack(self, job: "Job", *, requeue: bool = True) -> None: ...                             # requeue=False -> dead-letter (Story 2.6)
```

## VectorStore — ANN + hybrid retrieval surface (pgvector ↔ swappable)
```python
class RetrievalFilters(TypedDict, total=False):
    equipment_id: UUID
    manufacturer: str
    model: str
    revision: str
    only_current: bool            # version-aware: applicable vs obsolete (FR14)

class VectorStore(Protocol):
    def upsert(self, records: Sequence["VectorRecord"]) -> None: ...
    def search(self, query: Vector, *, tenant_id: UUID, top_k: int,
               filters: RetrievalFilters | None = None) -> list["VectorHit"]: ...                # tenant-scoped (NFR10)
    def lexical_search(self, query: str, *, tenant_id: UUID, top_k: int,
                       filters: RetrievalFilters | None = None) -> list["VectorHit"]: ...         # BM25-style (ADR 0004)
    def delete_by_chunk(self, chunk_ids: Sequence[UUID]) -> None: ...
```

## LLMClient — generation + embeddings (Azure OpenAI, pluggable — [ADR 0007](../../adr/0007-pluggable-llm-client-azure-openai.md))
```python
class LLMClient(Protocol):
    def embed(self, texts: Sequence[str], *, model_version: str) -> list[Vector]: ...
    def complete(self, messages: Sequence["ChatMessage"], *,
                 model: str, temperature: float = 0.0) -> "Completion": ...                       # returns text + usage/cost
    def stream(self, messages: Sequence["ChatMessage"], *,
               model: str, temperature: float = 0.0) -> Iterator["CompletionChunk"]: ...          # TTFT streaming (NFR2)
```

## SecretsProvider — config/secrets (.env ↔ Key Vault + managed identity)
```python
class SecretsProvider(Protocol):
    def get(self, name: str) -> str: ...                 # raises if missing
    def get_optional(self, name: str) -> str | None: ...
```

## PiiScrubber — PII detection/anonymization (Presidio, self-hosted; NFR16, Story 6.4)
```python
@dataclass(frozen=True)
class PiiEntity: type: str; start: int; end: int; score: float   # e.g. type="EMAIL_ADDRESS"

class PiiScrubber(Protocol):
    def detect(self, text: str, *, language: str = "en") -> list[PiiEntity]: ...
    def anonymize(self, text: str, *, language: str = "en") -> str: ...   # redact/mask detected PII
```
> Presidio is the default (open-source, local). Handles **PII only** — not harmful-content/prompt-injection moderation (that is own guardrails + optional Content Safety). Swappable behind the port (e.g., Azure AI Language PII as a paid alternative).

## Cache — layered cache ([ADR 0009](../../adr/0009-caching-strategy.md); Redis ↔ Azure Cache)
```python
class Cache(Protocol):
    def get(self, namespace: str, key: str) -> bytes | None: ...
    def set(self, namespace: str, key: str, value: bytes, *, ttl_s: int | None = None) -> None: ...
    def delete(self, namespace: str, key: str) -> None: ...
    def invalidate_namespace(self, namespace: str) -> None: ...        # bulk evict, e.g. on version supersession
```
> Answer/retrieval cache keys **must** be tenant-partitioned and encode equipment model + revision + current version set (ADR 0009 hard rules). Callers compose the key; the port stays generic. Invalidation on ingestion uses `invalidate_namespace` / `delete`.

## Telemetry — tracing/metrics (OpenTelemetry/Prometheus ↔ Azure Monitor)
```python
class Telemetry(Protocol):
    def span(self, name: str, **attributes: Any) -> ContextManager["Span"]: ...                   # feeds QueryTrace (FR30)
    def counter(self, name: str, value: float = 1.0, **labels: str) -> None: ...
    def histogram(self, name: str, value: float, **labels: str) -> None: ...                      # latency/cost (FR31)
```

## Supporting value types (design)
```python
@dataclass(frozen=True)
class VectorRecord: chunk_id: UUID; tenant_id: UUID; vector: Vector; model_version: str

@dataclass(frozen=True)
class VectorHit: chunk_id: UUID; score: float; document_version_id: UUID; page_start: int; section_id: UUID

@dataclass(frozen=True)
class ChatMessage: role: Literal["system","user","assistant"]; content: str

@dataclass(frozen=True)
class Completion: text: str; input_tokens: int; output_tokens: int; cost_usd: float
```

## Notes
- Signatures are intentionally **provider-neutral** — no `boto3`/`azure.*`/`openai` types leak across the port (enforced in coding standards). Adapters translate.
- Retrieval exposes **both** `search` (vector) and `lexical_search` so the retrieval service fuses + reranks above the port; swapping to a managed hybrid engine later is an adapter change ([ADR 0004](../../adr/0004-hybrid-retrieval-on-postgres.md) revisit triggers).
- Method-level error semantics, retry/backoff and pagination are adapter-internal (inside-the-box LLD) and finalized per story.
