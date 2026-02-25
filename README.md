# Claude Production Systems — Applied AI Portfolio

This repository contains four production-grade Claude projects that model the full lifecycle of enterprise AI adoption: from technical discovery and architecture design through pilot evaluation, deployment, and operational governance.

The systems prioritize inspectability over abstraction, bounded behavior over unconstrained autonomy, and measurable performance over anecdotal quality. They are designed as applied deployment models rather than research experiments — reflecting the work of advising customer engineering teams on how to ship products with Claude safely and effectively.

Each project addresses a distinct deployment pattern (multi-agent RAG, domain helpdesk, realtime voice, evaluation infrastructure) while sharing consistent engineering principles: grounded retrieval, structured tool use, citation enforcement, eval-first development, and cost-aware operation. The accompanying workshop artifacts, pilot packs, and evaluation suites model the customer-facing deliverables that bridge technical implementation and business outcomes.

## How These Projects Map to Customer Engagements

| Project | Customer Pattern | Key Capabilities Demonstrated |
|---------|-----------------|-------------------------------|
| `founder-copilot-claude` | Multi-agent advisory product | Routing strategies, tool loops, citation grounding, structured traces |
| `k-food-helpdesk-claude` | Enterprise knowledge/support system | Domain RAG, strict citation policy, refusal handling, audit logging |
| `teachme-live-claude` | Realtime interactive application | WebSocket streaming, turn control, latency budgeting, barge-in safety |
| `claude-eval-kit` | Evaluation and pilot infrastructure | Typed eval framework, acceptance gates, regression diffing, pilot reporting |

## Architectural Themes

These patterns recur across projects and reflect the implementation guidance an Applied AI engineer would provide to customer teams:

- **Claude Messages API integration**: streaming, non-streaming, and bounded tool-use loops with retry/fallback.
- **RAG pipelines**: pgvector retrieval, reranking, lexical fallback, context budgeting, and cache-aware performance.
- **Tool gating**: intent-aware invocation, strict schemas, structured output contracts, and verification semantics.
- **Evaluation frameworks**: offline (deterministic, zero-cost) and online (judge-scored) modes for regression and quality measurement.
- **Safety and grounding**: strict/lenient citation policies, refusal correctness, unsupported-claim controls, and prompt injection resistance.
- **Cost controls**: embedding/retrieval caches, model fallback chains, retrieval-only eval modes, and token budgeting.
- **Observability**: routing traces, latency breakdowns, audit logs, and metrics endpoints for operational governance.
- **Deployment readiness**: environment-driven config, Docker workflows, auth scaffolding, and multi-tenant evolution paths.

Architecture decisions are made as explicit tradeoffs between model capability, latency, cost, and safety posture. Each system exposes policy toggles and instrumentation so these tradeoffs stay visible, testable, and measurable.

## Project Overviews

### founder-copilot-claude

Multi-agent decision system for startup execution workflows. Routes queries across investor, technical, and marketing perspectives using retrieval-grounded context and controlled tool calls.

- Routing strategies (`winner_take_all`, `consult_then_decide`, `ensemble_vote`) with full routing traces.
- Tool-loop with explicit verification semantics (unit economics, market sizing) and demo-stub hygiene.
- Citation-grounded generation with policy-driven refusal when evidence is insufficient.
- Evaluation: retrieval recall@k, MRR, citation-claim alignment, routing consistency, tool invocation accuracy, p50/p95 latency regressions.
- Workshop artifacts: customer workshop outline, pilot success criteria, demo script, failure modes analysis.

---

### k-food-helpdesk-claude

Domain-specific enterprise helpdesk with policy-grounded answers, citation enforcement, and safe response policies.

- RAG architecture over helpdesk policies and catalog data with reranking and lexical fallback.
- Citation enforcement modes (`strict`/`lenient`) with explicit groundedness behavior.
- Refusal handling for unsupported queries and out-of-scope requests.
- Evaluation: unsupported claim rate, citation coverage, retrieval hit rate, refusal correctness rate, latency p50/p95.
- Workshop artifacts: customer workshop outline, pilot criteria, demo script, failure modes analysis.

---

### teachme-live-claude

Realtime voice tutoring system with low-latency streaming, turn control, and production safety constraints.

- WebSocket pipeline with true token delta streaming (`LLM_DELTA`) and STT -> Claude -> TTS audio loop.
- Turn controller with barge-in interruption, per-turn cancellation tokens, and race-safe generation lifecycle.
- Latency budgeting with tracked p50/p95 end-to-end turn time and timeout fallback modes.
- Safety: low-confidence transcript thresholds, image-grounding constraints, structured tutoring output contracts.
- Evaluation: streaming token delay, cancellation success rate, transcript confidence behavior, format validity.

---

### claude-eval-kit

Standalone evaluation framework for Claude-powered systems with typed case definitions, pluggable adapters, and a pilot evaluation pack.

- Adapter-based execution: HTTP endpoint, direct Anthropic API, or offline stub. MODE controls scoring, not execution.
- Deterministic scorers: format validity, refusal correctness, citation detection, tool precision/recall, retrieval recall@k, MRR, prompt injection resistance.
- Judge scoring: YAML rubric-driven LLM evaluation for groundedness, helpfulness, tool use, and refusal quality.
- Regression diffing with configurable thresholds and CI-compatible exit codes.
- Pilot pack: acceptance gates (`evalkit gate`), stakeholder reports (`evalkit pilot-report`), curated datasets, and a 2-4 week pilot plan.

## Customer Engagement Model

Each project includes workshop and pilot artifacts that model how a Product Engineer on the Applied AI team would guide customers from discovery through deployment:

- **Discovery**: workshop outlines with stakeholder mapping, business alignment questions, and architecture whiteboarding templates.
- **Pilot design**: measurable success criteria, 2-4 week eval plans, acceptance gates with go/no-go thresholds.
- **Implementation guidance**: architecture decisions documented as explicit tradeoffs; routing traces and metrics endpoints that make system behavior inspectable during code reviews.
- **Evaluation**: eval suites that test retrieval quality, citation integrity, tool discipline, refusal correctness, and injection resistance — runnable offline for low-cost regression checks.
- **Rollout readiness**: failure mode analysis, policy toggle documentation, and production monitoring recommendations.

## Deployment & Engineering Practices

- **Environment-based configuration** across services and runtime policies.
- **Docker-first workflows** for reproducible local and review environments.
- **Secrets hygiene** with template env files and no committed credentials.
- **Eval-first development loop** using fast regression modes before full API-backed checks.
- **Structured logging and metrics** for latency, failures, routing, and grounding signals.
- **Cost-aware architecture** through cache layers, retrieval controls, model fallback, and targeted eval spend.
- **Production-grade streaming patterns** with cancellation safety, buffering strategy, and explicit protocol events.

## Reliability & Failure Controls

Common failure modes addressed across these systems:
- retrieval hallucination from low-recall context
- citation drift between retrieved evidence and generated claims
- tool over-invocation and tool loop exhaustion
- streaming race conditions during cancellation/interruption
- cross-session cache contamination
- prompt injection via retrieved documents
- latency spikes and degraded network behavior

Primary mitigations:
- retrieval confidence thresholds and fallback policies
- structured output validation and schema enforcement
- bounded tool loops with timeout budgets
- cancellation-safe streaming lifecycle controls
- scoped cache keys (tenant/session-aware)
- strict citation enforcement modes
- timeout budgets with explicit fallback behavior

## Applied AI Relevance

This portfolio reflects the core responsibilities of a Product Engineer on Anthropic's Applied AI team: serving as a technical advisor to customers deploying Claude, architecting solutions that balance capability with safety, developing evaluation frameworks that translate model behavior into measurable business outcomes, and building the implementation patterns and pilot infrastructure that move customers from technical discovery to production deployment.
