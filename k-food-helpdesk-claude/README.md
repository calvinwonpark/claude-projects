# K-Food Helpdesk (Claude, Enterprise RAG)

Production-ready Claude + RAG implementation that keeps the same user UX as the Gemini version, with stronger reliability, safety, and observability controls for enterprise deployments.

## Architecture

```text
           +----------------------+
           |      Next.js Web     |
           |   (streaming chat)   |
           +----------+-----------+
                      |
                      v
           +----------------------+
           |   FastAPI Server     |
           |  - Auth toggle       |
           |  - Citation policy   |
           |  - Rerank + cache    |
           |  - Audit logging     |
           +----+------------+----+
                |            |
                v            v
      +----------------+   +------------------+
      | Anthropic API  |   | Embedding API    |
      | (Claude chat)  |   | gemini/openai/   |
      +----------------+   | local            |
                           +---------+--------+
                                     |
                                     v
                           +------------------+
                           | Postgres+pgvector|
                           | docs + audit_logs|
                           +------------------+
```

## Services

- **db**: Postgres + pgvector (`localhost:5434`)
- **server**: FastAPI (`localhost:8020`)
- **web**: Next.js (`localhost:3002`)
- **indexer**: ingestion + embedding writer

## Quick Start

1) Create env:
```bash
cp ENV_EXAMPLE.txt .env
```

2) Set keys (`ANTHROPIC_API_KEY` + embedding provider key)

3) Build and start:
```bash
docker compose up -d --build
```

4) Index data:
```bash
docker compose run --rm indexer
```

## Reliability & Safety

- **Strict citation policy** (`CITATION_MODE=strict` by default):
  - Keeps only valid citations that match retrieved doc IDs.
  - Refuses answer when evidence is insufficient or claims are uncited.
- **Lenient mode** (`CITATION_MODE=lenient`):
  - Returns response as `[Unverified]` if citations are weak/missing.
- **PII-safe logging** (`PII_REDACTION=true`):
  - Redacts email, phone, and card-like patterns before logging.
- **Audit logging**:
  - `audit_logs` table captures model, latency, token usage, retrieved/cited doc IDs, prompt hash, and auth user context.

## Endpoints

- `GET /` API index
- `GET /health`
- `GET /metrics` (request stats, p95 latency, cache hit rates)
- `GET /models` (Anthropic model availability cache + selected fallback chain)
- `POST /search`
- `POST /chat`
- `POST /chat/stream` (SSE)
- `GET /audit/recent?limit=50` (requires JWT auth or `X-API-Key: ADMIN_API_KEY`)

## Evals

Dataset and runner:
- `evals/test_cases.jsonl` (25+ bilingual cases)
- `evals/run_eval.py`

Run:
```bash
make eval
# or
python evals/run_eval.py
```

Outputs:
- terminal summary
- `evals/results.json`

Metrics:
- `retrieval_hit_rate`
- `citation_precision`
- `citation_recall`
- `groundedness_rate`
- retrieval/generation latency p50/p95

## Workshops

These workshop artifacts model how an Applied AI engineer can guide enterprise teams through discovery -> pilot -> evals -> rollout for this project:

- `workshops/customer_workshop_outline.md`
- `workshops/pilot_success_criteria.md`
- `workshops/demo_script.md`
- `workshops/failure_modes_and_mitigations.md`

## Enterprise Deployment Patterns

- **Auth mode**
  - `AUTH_MODE=none` (demo default)
  - `AUTH_MODE=jwt` enforces `Authorization: Bearer <token>` (HS256 via `JWT_SECRET`)
- **Audit access**
  - JWT in auth mode, or `ADMIN_API_KEY` via `X-API-Key`
- **Cost/latency controls**
  - model fallback chain + startup model validation
  - timeout guard: `REQUEST_TIMEOUT_MS`
  - embedding/retrieval caches with TTL and LRU bounds

## Reindexing

```bash
docker compose run --rm indexer
```

Indexer resets `docs` (`TRUNCATE ... RESTART IDENTITY`) for stable doc IDs.

## Make Targets

```bash
make up
make index
make logs
make down
make rebuild
make eval
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | - | Claude API key |
| `CLAUDE_PRIMARY_MODEL` | `claude-3-5-sonnet-latest` | Preferred model |
| `CLAUDE_FALLBACK_MODEL` | `claude-3-haiku-latest` | First fallback |
| `CLAUDE_MODEL_CANDIDATES` | list | Additional fallbacks |
| `REQUEST_TIMEOUT_MS` | `15000` | Timeout for Claude calls |
| `EMBEDDING_PROVIDER` | `gemini` | `gemini|openai|local` |
| `EMBEDDING_DIM` | `768` | Must match pgvector schema |
| `GEMINI_API_KEY` | - | Required when provider is gemini |
| `OPENAI_API_KEY` | - | Required when provider is openai |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model |
| `LOCAL_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Local embedding model |
| `AUTH_MODE` | `none` | `none|jwt` |
| `JWT_SECRET` | - | HS256 secret for JWT validation |
| `ADMIN_API_KEY` | empty | Optional admin key for `/audit/recent` |
| `PII_REDACTION` | `true` | Redact sensitive values in logs |
| `CITATION_MODE` | `strict` | `strict|lenient` |
| `SESSION_STORE_BACKEND` | `memory` | `memory|redis` |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection |
| `SESSION_MAX_TURNS` | `20` | Conversation memory bound |
| `RAG_TOP_K` | `8` | Retrieval size before rerank |
| `RAG_THRESHOLD` | `0.45` | Similarity threshold |
| `RAG_FALLBACK_FLOOR` | `0.15` | Score floor for fallback docs |
| `RAG_FALLBACK_MIN_DOCS` | `1` | Fallback minimum docs |
| `RAG_ENABLE_LEXICAL_FALLBACK` | `true` | Lexical fallback when vector retrieval misses |
| `RAG_MAX_CONTEXT_CHARS` | `6000` | Context budget |
| `RAG_SNIPPET_CHARS` | `400` | Per-snippet budget |
| `RERANK_MODE` | `heuristic` | `off|heuristic|llm` |
| `RERANK_TOP_N` | `6` | Context docs after rerank |
| `EMBEDDING_CACHE_SIZE` | `2048` | Embedding cache size |
| `EMBEDDING_CACHE_TTL_SECONDS` | `86400` | Embedding cache TTL |
| `RETRIEVAL_CACHE_SIZE` | `2048` | Retrieval cache size |
| `RETRIEVAL_CACHE_TTL_SECONDS` | `600` | Retrieval cache TTL |
