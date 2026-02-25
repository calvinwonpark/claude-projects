# Claude Production Systems — Applied AI Portfolio

This monorepo contains four production-style Claude projects built to reflect real deployment conditions rather than toy demos. The systems prioritize inspectability over abstraction, bounded behavior over unconstrained autonomy, and measurable performance over anecdotal quality.
These systems are intentionally designed as applied deployment models rather than research experiments, prioritizing inspectability, safety boundaries, and measurable performance under real-world constraints.

Across projects, the implementation focus is consistent: grounded RAG pipelines, structured agent behavior, measurable eval harnesses, and deployment-ready infrastructure. Each project includes explicit controls for refusal behavior, citation integrity, and fallback handling, with metrics and traces that make system decisions inspectable.

The repository is designed to model enterprise adoption patterns: pilot-friendly architecture, configurable policy modes, cost-aware operation, and clear pathways from local development to production governance.

## Architectural Themes

- **Claude-native runtime patterns**: Anthropic Messages integration with streaming and bounded tool-use loops.
- **RAG infrastructure**: pgvector-backed retrieval, rerank/fallback logic, and context budgeting for grounded responses.
- **Tool gating and structure**: intent-aware tool invocation, strict schemas, and structured output contracts.
- **Eval-first engineering**: retrieval-only and full modes for low-cost regression checks and behavior validation.
- **Safety and grounding**: strict/lenient citation policies, refusal handling, and unsupported-claim controls.
- **Cost controls**: cache layers, embedding dedupe, model fallback strategy, and selective paid-eval usage.
- **Observability by default**: routing traces, latency breakdowns, audit logs, and metrics endpoints.
- **Deployment readiness**: environment-driven config, Docker workflows, and auth-ready architecture for multi-tenant evolution.

Across projects, architecture decisions are made as explicit tradeoffs between model capability, latency, cost, and safety posture. Each system exposes policy toggles and instrumentation so these tradeoffs stay visible, testable, and measurable rather than implicit.

## Project Overviews

## founder-copilot-claude

`founder-copilot-claude` is a multi-agent decision system for startup execution workflows. It routes queries across investor, technical, and marketing perspectives, then combines retrieval-grounded context with Claude reasoning and controlled tool calls.

Core characteristics:
- Multi-agent routing strategies (`winner_take_all`, `consult_then_decide`, `ensemble_vote`) with routing traces.
- Tool-loop support for structured tasks (for example, unit economics and market-size style operations) with explicit verification semantics.
- Citation-grounded generation and policy-driven refusal when evidence quality is insufficient.
- Evaluation support includes retrieval recall@k and MRR tracking, citation-claim alignment checks, routing consistency across temperature seeds, tool invocation accuracy (precision and false-positive rate), and p50/p95 latency regressions.
- Enterprise-style telemetry and safety controls through audit logs, policy modes, and config-driven runtime limits.

This project emphasizes guiding startups through structured decision-making with Claude, while keeping system behavior inspectable and measurable.

---

## k-food-helpdesk-claude

`k-food-helpdesk-claude` is a domain-specific enterprise helpdesk system centered on policy-grounded answers. It combines retrieval pipelines, citation enforcement, and safe response policies to reduce unsupported support outputs.

Core characteristics:
- Domain-focused RAG architecture over helpdesk policies and catalog data.
- Citation enforcement modes (`strict` and `lenient`) with explicit groundedness behavior.
- Structured response behavior and refusal handling for unsupported queries.
- Retrieval architecture with pgvector, reranking, lexical fallback, and cache-aware performance tuning.
- Tool/operation discipline and eval coverage to prevent unnecessary complexity in policy-first workflows.
- Metrics and eval outputs include unsupported claim rate, citation coverage percentage, retrieval hit rate, refusal correctness rate, and latency p50/p95.

This project emphasizes designing grounded, reliable enterprise knowledge systems with Claude.

---

## teachme-live-claude

`teachme-live-claude` is a realtime tutoring system that demonstrates low-latency voice interaction with strict runtime controls. It implements a live STT -> Claude -> TTS loop with true incremental model streaming and turn-safe interruption behavior.

Core characteristics:
- WebSocket-based realtime pipeline with true token delta streaming (`LLM_DELTA`).
- End-to-end audio workflow: speech capture, transcription, Claude generation, and synthesized playback.
- Turn controller with interruption handling, cancellation, and race-safe generation lifecycle.
- Latency budgeting with tracked p50/p95 end-to-end turn time (STT -> LLM -> TTS) and timeout fallback modes.
- Safety controls for low-confidence transcripts (thresholded handling), image-grounding constraints, and structured tutoring outputs.
- Eval and observability hooks for streaming token delay, cancellation success rate, transcript confidence threshold behavior, and realtime reliability metrics.

This project emphasizes low-latency, interactive AI systems that remain production-safe under live user behavior.

---

## claude-eval-kit

`claude-eval-kit` is a standalone evaluation framework for Claude-powered systems. It provides typed case definitions, pluggable adapters, deterministic and judge-based scoring, regression diffing, and a pilot evaluation pack with machine-readable acceptance gates.

Core characteristics:
- Adapter-based execution: run cases against an HTTP endpoint, directly via Anthropic API, or with an offline stub for framework testing.
- Mode-separated scoring: offline mode applies deterministic checks only (no API cost); online mode adds rubric-driven LLM judge scoring.
- Deterministic scorers for format validity, refusal correctness, citation detection, tool precision/recall, retrieval recall@k, MRR, and prompt injection resistance.
- Regression diffing against stored baselines with configurable thresholds and CI-compatible exit codes.
- Pilot evaluation pack with go/no-go acceptance gates, curated datasets (core, injection, refusal), stakeholder report generation, and a structured 2-4 week pilot plan.
- CLI commands: `evalkit run`, `evalkit report`, `evalkit diff`, `evalkit gate`, `evalkit pilot-report`.

This project emphasizes systematic evaluation infrastructure for enterprise Claude deployments: measurable quality gates, reproducible runs, and customer-ready pilot artifacts.

## Deployment & Engineering Practices

- **Environment-based configuration** across services and runtime policies.
- **Docker-first workflows** for reproducible local and review environments.
- **Secrets hygiene** with template env files and no committed credentials.
- **Eval-first development loop** using fast regression modes before full API-backed checks.
- **Structured logging and metrics** for latency, failures, routing, and grounding signals.
- **Cost-aware architecture** through cache layers, retrieval controls, model fallback, and targeted eval spend.
- **Production-grade streaming patterns** with cancellation safety, buffering strategy, and explicit protocol events.

## Pilot & Rollout Model

- **2-4 week pilot structure** with scoped intents, policy coverage, and weekly KPI reviews.
- **Low-cost regression loop** using retrieval-only eval modes before full model-backed runs.
- **Policy toggles for rollout maturity** (`strict` vs `lenient` grounding) to phase safety posture by use case.
- **Instrumentation-led budgeting** with latency, cache, and token/cost signals to tune operating envelopes.
- **Auth-ready evolution path** (`none|jwt` patterns) for staged multi-tenant deployment.

## Reliability & Failure Controls

Common failure modes addressed across these systems:
- retrieval hallucination from low-recall context
- citation drift between retrieved evidence and generated claims
- tool over-invocation and unnecessary tool path selection
- tool loop exhaustion without convergent outputs
- streaming race conditions during cancellation/interruption
- cross-session cache contamination
- prompt injection via retrieved documents
- latency spikes and degraded network behavior

Primary mitigations:
- retrieval confidence thresholds and fallback policies
- structured output validation and schema checks
- bounded tool loops with timeout budgets
- cancellation-safe streaming lifecycle controls
- scoped cache keys (tenant/session-aware)
- strict citation enforcement modes
- timeout budgets with explicit fallback behavior

## Applied AI Relevance

This portfolio demonstrates practical applied AI engineering in customer-facing contexts: designing pilots, architecting Claude integrations, building evaluation frameworks, making model/tool tradeoffs explicit, and operating safe, scalable LLM systems under real constraints.
