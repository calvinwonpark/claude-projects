# Demo Script (10-15 Minutes)

Goal: recruiter-friendly walkthrough showing grounded multi-agent behavior, tool discipline, and observability.

## 0) Setup (2 min)

Run:

```bash
cp ENV_EXAMPLE.txt .env
docker compose up -d --build
make index
```

Open:
- App UI: `http://localhost:8030`
- Metrics UI/API: `http://localhost:8030/metrics` and `http://localhost:8030/api/metrics`

Talk track:
- "This is a Claude-based founder copilot with router, retrieval, tool loop, and auditable traces."

## 1) Investor Question (RAG + Strict Citations) (2 min)

Prompt:
- "How should I frame traction for angel investors in the first pitch?"

Expected output:
- cites retrieved docs (e.g., `[doc:<id>]`)
- no unsupported factual claims in strict mode
- response references investor framing/KPI docs

Talk track:
- "I am showing grounded generation. The answer must map to retrieved sources, not model memory."

## 2) Tech Architecture Question (Different Route) (2 min)

Prompt:
- "What API architecture pattern should we pick for fast iteration and reliability?"

Expected output:
- selected agent shifts toward tech domain
- routing strategy visible in `routing_trace`

Talk track:
- "The router is not cosmetic. It changes reasoning context and retrieval domain."

## 3) Intentional Tool Call (Unit Economics / Structured Calc) (2 min)

Prompt:
- "Estimate a simple unit economics scenario: ARPU 29, COGS 8, support 5. What is contribution margin?"

Expected output:
- tool call appears in `routing_trace.tool_calls_made` when policy allows
- output is explicit about demo/stub verification if applicable

Talk track:
- "Tools are gated and bounded. We do not invoke tools by default; only when intent justifies it."

## 4) Show Routing Trace and Explain Decision (2 min)

How:
- Use API for inspectable JSON:

```bash
curl -s -X POST http://localhost:8030/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"For fundraising, should we prioritize reliability or GTM messaging first?"}' | jq
```

Expected output:
- `routing_trace.strategy_selected`
- selected agent and confidence
- retrieved doc IDs and cited IDs

Talk track:
- "This trace is why this is production-plausible. Every recommendation has a route and evidence."

## 5) Retrieval-Empty Behavior (Safe Fallback) (2 min)

Prompt:
- "Cite our internal Q4 board memo appendix C from yesterday."

Expected output:
- strict mode refusal or clarification request
- no fabricated citations

Talk track:
- "When retrieval is empty, the system refuses safely instead of hallucinating confidence."

## 6) Metrics Inspection (1-2 min)

Open:
- `GET /api/metrics`

Highlight:
- retrieval and generation latency p50/p95
- cache hit/miss counters
- request/timeout/error counters

Talk track:
- "We expose operating metrics needed for pilot governance and cost control."

## 7) Eval Run (retrieval_only) (1-2 min)

Run:

```bash
make eval-retrieval
cat evals/results.json
```

Expected output:
- pass/fail summary with retrieval and routing metrics
- `retrieval_hit_rate`, `routing_accuracy`, latency stats

Talk track:
- "This is the low-cost regression gate. Teams run this frequently before full paid evals."

## Closing Statement

- "The key value is not just answer quality. It is controlled routing, grounded evidence, and measurable reliability."

