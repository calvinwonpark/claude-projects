# Demo Script (10-15 Minutes)

Goal: show recruiter-ready evidence of grounded helpdesk behavior, strict safety controls, and production observability.

## 0) Setup (2 min)

```bash
cd /Users/calvin.park/claude-projects/k-food-helpdesk-claude
cp ENV_EXAMPLE.txt .env
docker compose up -d --build
docker compose run --rm indexer
```

Open:
- Web app: `http://localhost:3002`
- API docs/health: `http://localhost:8020/health`
- Metrics: `http://localhost:8020/metrics`

Talk track:
- "This is a Claude + pgvector support system with strict citation policy and auditable outputs."

## 1) RAG + Strict Citation Query (2 min)

Prompt:
- "What is your refund policy for late deliveries? Please cite sources."

Expected output:
- answer grounded in policy docs
- valid citations corresponding to retrieved doc IDs
- no fabricated references

Talk track:
- "We optimize for trustworthy support answers, not unsupported confidence."

## 2) Different Intent Route (2 min)

Prompt:
- "Do you deliver to Gangnam after 10 PM, and what fees apply?"

Expected output:
- retrieval shifts to delivery/hours/fees docs
- concise policy-grounded response with citations

Talk track:
- "The retrieval context changes by intent, giving high-precision support answers."

## 3) Intentional Structured Operation / Tool-Style Behavior (2 min)

Prompt:
- "If delivery fee is 3,500 KRW and order is 22,000 KRW, what is total charge?"

Expected output:
- deterministic arithmetic in answer (or explicit policy-safe explanation)
- no unsupported assumptions beyond policy context

Talk track:
- "For bounded calculations, we want deterministic behavior and clear assumptions."

## 4) Inspect Retrieval Trace with `/search` (2 min)

```bash
curl -s -X POST http://localhost:8020/search \
  -H "Content-Type: application/json" \
  -d '{"query":"refund policy for late delivery"}' | jq
```

Expected output:
- top-k retrieved docs/snippets and scores
- evidence that answer grounding is reproducible

Talk track:
- "This endpoint is how we debug and tune retrieval quality with customer data."

## 5) Retrieval-Empty / Safe Fallback (2 min)

Prompt:
- "What is your policy for drone delivery in Jeju this weekend?"

Expected output:
- strict mode refusal or clarification when evidence is missing
- no fabricated policy claim

Talk track:
- "Safe failure is a feature: when evidence is missing, we refuse instead of hallucinating."

## 6) Metrics Walkthrough (1-2 min)

Open:
- `GET /metrics` (or `/api/metrics` if enabled)

Highlight:
- p50/p95 latency
- cache hit/miss
- request/error/timeout counters

Talk track:
- "These are the signals we use for pilot governance and cost management."

## 7) Eval Run and Summary (1-2 min)

```bash
make eval
cat evals/results.json
```

Expected output:
- summary metrics including:
  - `retrieval_hit_rate`
  - `citation_precision`
  - `groundedness_rate`
  - latency p50/p95

Talk track:
- "Evals are how we enforce regressions before rollout, not a one-time benchmark."

## Closing Line

- "This demo shows production habits: grounded answers, strict refusal policy, measurable reliability, and clear operating controls."

