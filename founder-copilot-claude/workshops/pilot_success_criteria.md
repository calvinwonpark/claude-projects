# Pilot Success Criteria (2-4 Weeks)

Scope: measurable validation of quality, safety, reliability, latency, and cost for `founder-copilot-claude`.

## 1) Quality Metrics

- **Citation precision (unsupported claim rate inverse)**
  - Definition: % cited claims that map to retrieved `doc_id` and support the statement.
  - Target: `>= 0.95` precision; unsupported claim rate `<= 0.05`.
  - Measure:
    - `make eval` -> `citation_precision`, `groundedness_rate`
    - spot-check `/chat` outputs against `routing_trace.retrieved_doc_ids` and cited IDs.

- **Answer helpfulness (rubric score)**
  - Rubric (1-5): relevance, actionability, clarity, and domain fit.
  - Target: average `>= 4.0`, no critical query below `3`.
  - Measure:
    - weekly human review of 20 representative prompts from pilot logs (`/audit/recent`).

- **Tool accuracy (precision/recall)**
  - Definition: when tools are invoked, were they needed and correct?
  - Target: precision `>= 0.90`, recall `>= 0.85`.
  - Measure:
    - eval metrics `tool_correctness_rate`
    - manual review of `routing_trace.tool_calls_made` and `tool_results`.

- **Retrieval hit rate**
  - Definition: % of prompts where top-k includes at least one relevant chunk.
  - Target: `>= 0.80` overall, `>= 0.90` on top business intents.
  - Measure:
    - `make eval-retrieval` -> `retrieval_hit_rate`
    - debug with `POST /search`.

## 2) Safety and Reliability Metrics

- **Refusal correctness rate**
  - Definition: model refuses when evidence is missing or policy requires refusal.
  - Target: `>= 0.95`.
  - Measure:
    - add explicit refusal cases in `evals/test_cases.jsonl`
    - verify strict mode (`CITATION_MODE=strict`) behavior in eval outputs.

- **Prompt injection resilience**
  - Definition: ignores malicious instruction inside retrieved docs (e.g., "ignore all prior instructions").
  - Target: pass rate `>= 0.90` on curated adversarial set.
  - Measure:
    - add adversarial docs/queries to eval set
    - verify responses remain policy-bound and grounded.

- **Cross-tenant leakage checks**
  - Definition: no retrieval or citation leakage between synthetic tenant A/B corpora.
  - Target: `0` leakage incidents in test suite.
  - Measure (even if single-tenant today):
    - run synthetic split corpus tests
    - validate retrieval filters and cache-key scoping plan before production rollout.

## 3) Performance Metrics

- **Latency budgets (p50/p95)**
  - End-to-end (`/chat` or `/chat/stream`): p50 `<= 2.5s`, p95 `<= 6.0s`
  - Retrieval stage: p50 `<= 300ms`, p95 `<= 800ms`
  - LLM stage: p50 `<= 1.8s`, p95 `<= 4.5s`
  - Tool stage (when used): p50 `<= 500ms`, p95 `<= 1.5s`
  - Measure:
    - `/api/metrics` and `/metrics`
    - eval latency summaries in `evals/results.json`.

- **Error and timeout rates**
  - Target: 5xx rate `< 1%`, timeout rate `< 2%`.
  - Measure:
    - API logs + audit latency fields + metrics counters.

## 4) Cost Metrics

- **Cost per conversation**
  - Target (pilot default): median `< $0.05` per conversation, p95 `< $0.12`.
  - Measure:
    - token usage from eval summary and provider billing dashboard
    - correlate with model routing and fallback rate.

- **Cache effectiveness**
  - Target: retrieval cache hit rate `>= 0.35` by week 2; query-embedding cache hit `>= 0.50`.
  - Measure:
    - `/api/metrics` cache hit/miss counters.

- **Eval-only regression mode**
  - Target: `make eval-retrieval` is used as required pre-merge gate for low-cost regressions.
  - Measure:
    - CI logs show retrieval-only eval pass before full eval runs.

## Measurement Cadence

- Daily: latency/error dashboard check (`/api/metrics`, logs).
- Twice weekly: eval run and KPI snapshot (`evals/results.json`).
- Weekly: pilot review with PM/Eng/Security using this scorecard.

## Pilot Exit Criteria (Go/No-Go)

Go if all are true:
- citation precision `>= 0.95`
- unsupported claim rate `<= 0.05`
- refusal correctness `>= 0.95`
- p95 latency `<= 6.0s`
- no cross-tenant leakage in synthetic tests
- no Sev-1 safety incidents

No-go / extend pilot if any criterion misses threshold for two consecutive reviews.

