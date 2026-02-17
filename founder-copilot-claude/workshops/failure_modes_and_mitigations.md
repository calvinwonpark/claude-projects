# Failure Modes and Mitigations

This list is tuned for `founder-copilot-claude` (router + RAG + tools + citations + streaming).

## 1) Hallucinations from Weak Retrieval

- Symptom:
  - confident answer with thin or irrelevant evidence.
- Root causes:
  - low-quality chunks, weak embeddings, overly low retrieval threshold.
- Detection:
  - drop in `retrieval_hit_rate`, `groundedness_rate`, citation-review failures.
  - manual mismatch between `retrieved_doc_ids` and answer claims.
- Mitigation:
  - tighten retrieval filters and rerank mode.
  - improve corpus quality/chunking.
  - keep `CITATION_MODE=strict` for factual workflows.

## 2) Citation Mismatch / Fabricated Citations

- Symptom:
  - cited IDs not present in retrieved set or unsupported claim text.
- Root causes:
  - weak citation validation, lenient prompt behavior, stale eval coverage.
- Detection:
  - `citation_precision` decline.
  - strict-mode refusal spikes from citation validator.
- Mitigation:
  - enforce "cited IDs subset of retrieved IDs" invariant.
  - add citation-specific eval cases.
  - fail CI on citation metric regressions.

## 3) Tool Over-Invocation and Demo Stub Risk

- Symptom:
  - tools called for generic queries; demo-only tool outputs treated as facts.
- Root causes:
  - broad tool gating prompts, missing verification labels in UX.
- Detection:
  - `routing_trace.tool_calls_made` unexpectedly high.
  - user-visible outputs missing `demo_stub` or `verification=demo_mode`.
- Mitigation:
  - tighten intent gating and increase confidence threshold for tool use.
  - keep tool loop bounded (`TOOL_MAX_ITERS`, `TOOL_TIMEOUT_MS`).
  - label stub-derived content explicitly in final answer.

## 4) Streaming Safety: Draft-Then-Refusal UX

- Symptom:
  - early streamed content says one thing, final safety check refuses later.
- Root causes:
  - unsafe token streaming before citation/safety validation.
- Detection:
  - user reports contradictory stream vs final answer.
  - audit entries where final status is refusal after long partial stream.
- Mitigation:
  - keep `STRICT_STREAM_BUFFERED=true` in strict mode.
  - stream only after policy checks pass.
  - add tests for refusal paths in streaming endpoint.

## 5) Latency Spikes and Timeouts

- Symptom:
  - p95 latency increases, timeout rate grows, poor UX.
- Root causes:
  - large retrieval sets, model fallback churn, tool timeout accumulation, cold caches.
- Detection:
  - `/api/metrics` p95 latency by stage.
  - timeout/error counters and audit latency trends.
- Mitigation:
  - tune top-k, rerank depth, and timeout budgets.
  - improve cache TTL/max size for query/retrieval paths.
  - route low-risk workloads to cheaper/faster model tiers.

## 6) Prompt Injection in Documents

- Symptom:
  - model follows malicious text embedded in corpus ("ignore policy", "reveal secrets").
- Root causes:
  - retrieval includes adversarial chunks, weak system guardrails.
- Detection:
  - adversarial eval suite failures.
  - unusual instruction-following traces in risky docs.
- Mitigation:
  - sanitize/flag risky docs during ingestion.
  - treat retrieved docs as untrusted data, never policy overrides.
  - add injection-specific regression cases in evals.

## 7) Multi-Tenant Leakage via Caches or Retrieval

- Symptom:
  - user sees evidence or summaries belonging to another tenant.
- Root causes:
  - tenant-unscoped cache keys, missing tenant filters in retrieval queries.
- Detection:
  - synthetic tenant A/B leakage tests.
  - audit review for cross-tenant doc IDs.
- Mitigation:
  - include tenant_id in cache key and DB filters.
  - add tenant_id to `documents` and `audit_logs`.
  - enforce auth claims to retrieval filter mapping.

## 8) Routing Drift / Wrong Agent Selection

- Symptom:
  - strategy or selected agent does not match query intent.
- Root causes:
  - threshold miscalibration, stale strategy prompts, domain overlap.
- Detection:
  - `routing_accuracy` regression in evals.
  - manual review of `routing_trace.strategy_selected` vs expected route.
- Mitigation:
  - tune `ROUTER_AUTO_HIGH_CONF`, `ROUTER_AUTO_GAP`, `ROUTER_AUTO_MID_CONF`.
  - add targeted route-eval cases for ambiguous prompts.

