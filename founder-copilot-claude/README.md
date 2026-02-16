# Founder Copilot (Claude)

Portfolio-grade multi-agent startup advisor for an Applied AI / Solutions Architect showcase.
It preserves routing trace + streaming UX + safety controls, and upgrades RAG from demo retrieval
to production-plausible `pgvector` retrieval with real embedding providers (no Vertex required).

## Architecture

```text
Web UI (SSE stream + cancellation)
        |
        v
FastAPI (`app/main.py`)
  - Claude provider (retry/fallback/stream)
  - Multi-agent router + routing trace
  - RAG retriever (`pgvector` + optional lexical fallback + rerank)
  - Citation validator (strict/lenient)
  - Safe tools + metrics + PII-safe audit logging
        |
        +--> Anthropic Messages API
        +--> Postgres + pgvector (`documents`, `audit_logs`)
        +--> Redis (rate limiting)
        +--> Indexer (`scripts/index_corpus.py`)
```

## Endpoints

- `GET /` chat UI
- `GET /health`
- `GET /models`
- `POST /search` retrieval debug
- `GET /api/metrics`
- `GET /metrics`
- `POST /chat` (JSON, non-streaming)
- `POST /chat/stream` (SSE)
- `GET /audit/recent?limit=50` (JWT or admin API key)
- `POST /reset`

## Setup

```bash
cp ENV_EXAMPLE.txt .env
docker compose up -d --build
make index
```

Open: `http://localhost:8030`

Default stack is local and low-cost:
- vector backend: Postgres + pgvector
- embeddings default: `local` sentence-transformers
- no Vertex AI dependencies

## Configuration

Configuration is centralized in `app/config.py` and loaded once from environment.

- **Router strategy**
  - `ROUTER_STRATEGY=auto` (default) selects by confidence:
    - winner_take_all: `max_conf >= 0.65` and `(max-second) >= 0.20`
    - consult_then_decide: `max_conf >= 0.45`
    - ensemble_vote: otherwise
  - explicit override: `winner_take_all|consult_then_decide|ensemble_vote`
- **Tool runtime loop**
  - `TOOL_MAX_ITERS=3`
  - `TOOL_TIMEOUT_MS=3000`
  - tool calls and tool results are fed back to Claude using Anthropic tool_result message format
- **Safety defaults**
  - `CITATION_MODE=strict`
  - `STRICT_STREAM_BUFFERED=true` (prevents draft-then-refusal UX in strict mode)
  - `PII_REDACTION=true`

## Evals (Real)

The eval harness runs against real retrieval and optionally real Claude generation.

Run:

```bash
make eval-retrieval   # cheap, retrieval-only
make eval             # full run (requires ANTHROPIC_API_KEY)
```

Outputs:
- `evals/results.json`
- summary metrics:
  - `retrieval_hit_rate`
  - `routing_accuracy`
  - `citation_precision` / `citation_recall`
  - `groundedness_rate`
  - `tool_correctness_rate`
  - retrieval/generation latency p50/p95
  - token usage (best effort in full mode)

## Reliability & Safety

- **Strict citations (`CITATION_MODE=strict`)**:
  - answer citations must be subset of retrieved `doc_id`
  - no citation fabrication
  - unsupported/uncited factual answer is refused with clarification prompt
- **Lenient citations (`CITATION_MODE=lenient`)**:
  - answer allowed but labeled `[Unverified]`
- **PII-safe logging (`PII_REDACTION=true`)**:
  - email/phone/card-like patterns are redacted before logging
- **Audit logs in Postgres**:
  - one row per chat request with model, selected_agent, retrieved/cited ids, latency, tokens, request_id

## Enterprise Deployment Patterns

- `AUTH_MODE=none|jwt`
- JWT mode validates Bearer token (`HS256`, `JWT_SECRET`)
- `ADMIN_API_KEY` override for audit access
- Structured JSON logs (SIEM-friendly)
- Tenant isolation pattern:
  - include tenant/user claims in JWT
  - add tenant_id columns + row-level filters in retrieval/audit queries
- Data governance:
  - deterministic indexing from `data/`
  - content hash dedupe to prevent duplicate embeddings

## Cost Controls

- `EVAL_MODE=retrieval_only` for cheap regression checks
- embedding caches (TTL + LRU-like bounded maps)
- query/retrieval cache hit rates surfaced in `/api/metrics`
- dedupe indexing by `content_hash` avoids re-embedding unchanged chunks

## Tradeoffs

- `pgvector` is simple/local-first; managed vector DB scales operationally better at high QPS.
- Local embeddings reduce API cost; OpenAI/Gemini embeddings often improve retrieval quality.
- Sonnet primary + Haiku fallback balances quality/latency, but increases behavior variance across model failover.
- Strict citation mode improves trustworthiness but can increase refusals on sparse corpora.

## Environment Variables (Key)

- **Core:** `ANTHROPIC_API_KEY`, `CLAUDE_PRIMARY_MODEL`, `CLAUDE_FALLBACK_MODEL`, `REQUEST_TIMEOUT_MS`
- **DB/vector:** `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `VECTOR_BACKEND`, `VECTOR_DIM`
- **Embeddings:** `EMBEDDING_PROVIDER=openai|gemini|local|hash`, provider-specific API keys/model names
- **Retrieval:** `RETRIEVAL_TOP_K`, `RETRIEVAL_MIN_SCORE`, `RETRIEVAL_ENABLE_LEXICAL_FALLBACK`, `RERANK_MODE`
- **Router:** `ROUTER_STRATEGY`, `ROUTER_AUTO_HIGH_CONF`, `ROUTER_AUTO_GAP`, `ROUTER_AUTO_MID_CONF`
- **Tool runtime:** `TOOL_MAX_ITERS`, `TOOL_TIMEOUT_MS`
- **Safety/security:** `CITATION_MODE`, `STRICT_STREAM_BUFFERED`, `AUTH_MODE`, `JWT_SECRET`, `ADMIN_API_KEY`, `PII_REDACTION`
