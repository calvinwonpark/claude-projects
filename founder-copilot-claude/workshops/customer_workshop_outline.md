# Customer Workshop Outline (60-90 min)

Audience: enterprise team evaluating `founder-copilot-claude` for strategy, pitch, GTM, and docs-grounded advisory.

## Goals and Outcomes

- Align on business outcomes for the pilot (decision support, speed, trustworthiness, and operating cost).
- Confirm technical fit: routing, retrieval, citation policy, tool behavior, and observability.
- Leave with concrete implementation decisions, pilot KPIs, and an execution owner per workstream.

## Stakeholders to Invite

- Product: PM, product ops owner
- Engineering: backend lead, platform lead, AI/ML engineer
- Security and compliance: security engineer, governance/compliance lead
- Legal and privacy: legal counsel or privacy officer
- Data owners: knowledge base/content owner
- Executive sponsor: budget/sign-off authority

## Agenda (Timeboxed)

### 0-10 min: Context and Success Criteria

- Frame problem: where founder teams lose time (fundraising narrative, GTM prioritization, architecture tradeoffs).
- Define "good": grounded answers, predictable routing/tool behavior, and measurable latency/cost.

Script:
- "Today we are not evaluating a generic chatbot. We are evaluating a decision copilot with explicit traceability."
- "Every answer should be explainable by routing trace, retrieval evidence, and policy decisions."

### 10-25 min: Discovery Questions

Business and users:
- Which decisions matter most (fundraising, GTM, roadmap, hiring, architecture)?
- Who uses this first (founder, PM, sales leader, CTO) and what is their tolerance for refusal?
- What is the acceptable tradeoff between speed and strict grounding?

Risk and safety:
- What unsupported claim rate is acceptable in pilot vs production?
- Which topics require strict refusal without citations?
- Any regulated data classes (PII, financial, legal, healthcare)?

Performance and reliability:
- p50/p95 latency targets by workflow?
- Required uptime and error budget?
- Must-have observability outputs for legal/security review?

Data and deployment constraints:
- Which corpora are authoritative and how often do they change?
- Cloud/on-prem constraints and networking limits?
- Single-tenant now vs multi-tenant roadmap expectations?

Script:
- "I want to calibrate where you need hard guarantees versus best-effort suggestions."
- "Your risk tolerance directly drives citation mode, refusal posture, and cache policy."

### 25-45 min: Architecture Whiteboard Template (Repo-Specific)

Use this exact flow:
- UI (`/`) -> API (`/chat` or `/chat/stream`) -> router strategy (`winner_take_all|consult_then_decide|ensemble_vote`)
- retrieval (`pgvector`, optional lexical fallback, rerank) -> citation validator (strict/lenient)
- tool loop (gated tools, bounded by `TOOL_MAX_ITERS`, timeout via `TOOL_TIMEOUT_MS`)
- response + `routing_trace` + audit row in `audit_logs`

Discuss and decide:
- Safety/grounding mode:
  - strict: refuse unsupported factual claims
  - lenient: allow answer with `[Unverified]` labels
- Tool gating patterns:
  - only route to tools when intent is explicit and value is measurable
  - keep demo stubs marked as `demo_stub=true` with `verification=demo_mode`
- Observability and audit:
  - `/api/metrics`, `/metrics`, `/audit/recent`
  - structured logs with request_id, latency, retrieval IDs, cited IDs
- Cost controls:
  - model selection (`CLAUDE_PRIMARY_MODEL` + fallback)
  - retrieval/embedding cache TTL + max size
  - eval-only regression mode (`make eval-retrieval`)

Script:
- "This whiteboard is our source of truth: request path, policy checks, and where each decision is logged."
- "If we cannot observe it, we cannot safely roll it out."

### 45-70 min: Hands-On Validation

- Run demo queries in UI and via `POST /chat`.
- Inspect `routing_trace` for strategy and selected agent.
- Inspect retrieval evidence with `POST /search`.
- Open `/api/metrics` and confirm latency/cache counters.
- Run evals:
  - `make eval-retrieval`
  - `make eval` (if API budget approved)

Script:
- "We are validating behavior, not just output quality."
- "Each answer should match expected route, evidence, and policy."

### 70-90 min: Decisions and Next Steps

## Decisions We Will Make Today

- Model policy: primary/fallback model and timeout budgets.
- Citation policy: strict vs lenient by use case.
- Tool policy: enabled tools, demo-stub handling, and escalation language.
- Routing policy: auto thresholds vs fixed strategy override.
- Multi-tenant approach: near-term single-tenant controls and tenant-isolation roadmap.
- Pilot scorecard: KPI thresholds, owners, and review cadence.

Script:
- "By the end of this session we should have policy defaults and a measurable pilot plan, not just ideas."

## Homework and Follow-Ups

- Data ingestion:
  - finalize source docs
  - run `make index`
  - verify dedupe and update cadence
- Eval dataset:
  - add customer-specific queries to `evals/test_cases.jsonl`
  - tag risky prompts (prompt injection, unsupported claims, high-stakes decisions)
- Rollout plan:
  - internal alpha -> limited beta -> production gate
  - go/no-go review criteria tied to pilot metrics

