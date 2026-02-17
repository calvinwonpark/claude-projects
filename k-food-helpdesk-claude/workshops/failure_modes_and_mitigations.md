# Failure Modes and Mitigations

Top failure modes for `k-food-helpdesk-claude` and how to detect/mitigate them in pilot and rollout.

## 1) Hallucinations from Weak Retrieval

- Symptom:
  - assistant provides policy-like statements without strong evidence.
- Root causes:
  - sparse/old policy corpus, weak chunking, low retrieval thresholds.
- Detection:
  - degraded `retrieval_hit_rate` and `groundedness_rate` in evals.
  - audit spot checks show claims not supported by retrieved chunks.
- Mitigation:
  - improve corpus quality/chunking cadence.
  - tighten threshold/rerank settings and keep strict citation mode for policy intents.

## 2) Citation Mismatch

- Symptom:
  - citations do not map to retrieved doc IDs or cited text is off-topic.
- Root causes:
  - citation extraction/validation drift or weak prompt constraints.
- Detection:
  - `citation_precision` decline in evals.
  - manual mismatch via `/search` output vs answer citations.
- Mitigation:
  - enforce strict citation validator.
  - expand citation-focused eval cases.

## 3) Tool Over-Invocation / Stub Risk

- Symptom:
  - unnecessary operation/tool-like paths for simple policy queries.
  - outputs treated as authoritative without verification.
- Root causes:
  - broad invocation triggers, missing UX labels for non-authoritative operations.
- Detection:
  - spike in complex-operation path usage.
  - QA review catches unsupported assumptions.
- Mitigation:
  - keep operations deterministic and tightly scoped.
  - explicit assumption labeling and verification-required language.

## 4) Streaming Safety (Draft Then Refusal)

- Symptom:
  - streamed text starts with a direct answer, then final response refuses.
- Root causes:
  - streaming before citation/safety checks finish.
- Detection:
  - user reports contradictory interim/final outputs.
  - logs show late refusal after long stream.
- Mitigation:
  - buffer stream until safety checks pass in strict workflows.
  - add regression tests for refusal-path streaming behavior.

## 5) Latency Spikes / Timeouts

- Symptom:
  - p95 latency and timeout rates increase during peak loads.
- Root causes:
  - large retrieval context, rerank overhead, cache misses, provider latency.
- Detection:
  - `/metrics` p95 increases and timeout counters.
  - eval latency p95 regression.
- Mitigation:
  - reduce context budgets and rerank depth.
  - tune cache TTL/size and fallback behavior.
  - prewarm frequent query embeddings.

## 6) Prompt Injection in Retrieved Docs

- Symptom:
  - model follows malicious instruction embedded in corpus.
- Root causes:
  - treating retrieved text as trusted instruction instead of untrusted evidence.
- Detection:
  - adversarial eval failures.
  - suspicious policy override outputs in audit review.
- Mitigation:
  - sanitize ingestion and flag high-risk documents.
  - system prompt hard rule: retrieved text cannot override policy.
  - maintain injection-specific eval suite.

## 7) Multi-Tenant Leakage via Caches

- Symptom:
  - one tenant sees policy snippets or metadata from another tenant.
- Root causes:
  - cache keys or retrieval filters not tenant-scoped.
- Detection:
  - synthetic tenant A/B leakage tests.
  - audit anomalies in retrieved/cited IDs across tenant boundaries.
- Mitigation:
  - include tenant scope in cache keys.
  - enforce tenant filters in retrieval and audit queries.
  - add tenancy checks to CI/evals before production.

