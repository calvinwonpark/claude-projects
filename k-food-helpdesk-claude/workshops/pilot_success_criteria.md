# Pilot Success Criteria (2-4 Weeks)

Scope: validate `k-food-helpdesk-claude` on quality, safety, latency, and cost for policy-grounded customer support.

## 1) Quality Metrics

- **Citation precision / unsupported claim rate**
  - Definition: % of factual claims supported by retrieved policy docs and valid cited IDs.
  - Targets: citation precision `>= 0.95`; unsupported claim rate `<= 0.05`.
  - Measurement:
    - eval outputs (`make eval`, `evals/results.json`)
    - spot checks from `/chat` responses + retrieval evidence from `/search`.

- **Answer helpfulness (support rubric)**
  - Rubric (1-5): correctness, policy compliance, clarity, actionability.
  - Targets: average `>= 4.2`, no high-impact intent below `3`.
  - Measurement:
    - weekly review of sampled `/audit/recent` conversations.

- **Retrieval hit rate**
  - Definition: top-k includes at least one relevant policy chunk.
  - Targets: overall `>= 0.85`; critical intents (refund/allergen/delivery) `>= 0.92`.
  - Measurement:
    - eval retrieval metrics + `POST /search` debug traces.

## 2) Safety and Reliability Metrics

- **Refusal correctness rate**
  - Definition: correctly refuse or escalate when policy evidence is missing.
  - Target: `>= 0.95`.
  - Measurement:
    - refusal-focused eval cases in `evals/test_cases.jsonl`
    - strict mode validation (`CITATION_MODE=strict`).

- **Prompt-injection resilience**
  - Definition: malicious instructions in docs/user input do not override policy/system behavior.
  - Target: pass rate `>= 0.90` on adversarial set.
  - Measurement:
    - injection test subset in eval harness
    - audit review for anomalous policy violations.

- **Cross-tenant leakage validation**
  - Definition: no evidence leakage between tenant test corpora.
  - Target: `0` leakage incidents.
  - Measurement:
    - synthetic A/B corpus tests
    - cache-key and retrieval-filter review before production tenancy rollout.

## 3) Performance Metrics

- **Latency budgets (p50/p95)**
  - End-to-end `/chat`: p50 `<= 2.0s`, p95 `<= 5.0s`
  - Retrieval stage: p50 `<= 250ms`, p95 `<= 700ms`
  - Generation stage: p50 `<= 1.5s`, p95 `<= 4.0s`
  - Streaming first token (`/chat/stream`): p95 `<= 1.2s`
  - Measurement:
    - `/metrics` and `/api/metrics`
    - latency fields in eval results.

- **Reliability**
  - Targets: 5xx `< 1%`, timeout `< 2%`.
  - Measurement:
    - server logs + audit latencies + metrics counters.

## 4) Cost Metrics

- **Cost per resolved conversation**
  - Targets: median `< $0.04`, p95 `< $0.10` (pilot baseline).
  - Measurement:
    - token usage trends from evals + provider dashboard.

- **Cache effectiveness**
  - Targets by week 2:
    - embedding cache hit `>= 0.45`
    - retrieval cache hit `>= 0.35`
  - Measurement:
    - `/metrics` cache hit/miss counters.

- **Low-cost regression discipline**
  - Target: retrieval-focused eval run used as required pre-merge gate.
  - Measurement:
    - CI/job logs for eval run compliance.

## Measurement Cadence

- Daily: latency/error/timeout dashboard check.
- Twice weekly: eval run and KPI snapshot.
- Weekly: cross-functional pilot review (PM/Eng/Security/Support Ops).

## Pilot Exit Criteria (Go/No-Go)

Go if all criteria are met for two consecutive reviews:
- citation precision `>= 0.95`
- refusal correctness `>= 0.95`
- retrieval hit rate `>= 0.85` overall
- p95 end-to-end latency `<= 5.0s`
- no cross-tenant leakage incidents
- no Sev-1 safety/compliance incident

