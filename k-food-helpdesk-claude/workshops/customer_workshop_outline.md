# Customer Workshop Outline (60-90 min)

Audience: enterprise support, product, and operations teams adopting `k-food-helpdesk-claude` as a policy-grounded customer helpdesk assistant.

## Goals and Outcomes

- Align on target support outcomes: faster resolution, fewer escalations, and safer policy compliance.
- Confirm production-fit architecture: retrieval quality, citation policy, refusal behavior, and observability.
- Leave with signed pilot scope, KPI thresholds, and owners for data/evals/rollout.

## Stakeholders to Invite

- Product: PM, support operations lead
- Engineering: backend/API lead, platform owner
- Security/compliance: security lead, governance/compliance partner
- Legal/privacy: legal counsel or privacy owner
- Data/content owners: policy documentation and restaurant catalog owners
- Executive sponsor: budget and go/no-go approver

## Agenda (Timeboxed)

### 0-10 min: Outcomes and Constraints

- Define target business outcomes for support automation.
- Confirm what "safe and helpful" means for your org.

Script:
- "We are evaluating a policy-grounded assistant, not a generic chatbot."
- "Every answer should be traceable to retrieval evidence and citation policy."

### 10-25 min: Discovery Questions

Business and user questions:
- Which support intents are highest volume (hours, fees, allergens, refunds, delivery)?
- What languages are in-scope at pilot launch?
- What escalation paths must remain human-only?

Risk and policy:
- Which topics require strict refusal without grounded evidence?
- What is acceptable unsupported-claim rate for pilot?
- Any regulated data handling requirements (PII, card, location, order history)?

Technical and deployment:
- Cloud/network constraints and data residency requirements?
- Required p50/p95 latency and uptime targets?
- Current ticketing/CRM integration constraints?

Script:
- "Risk tolerance and compliance posture determine strict vs lenient citation policy."
- "Latency targets determine retrieval depth, rerank strategy, and timeout settings."

### 25-45 min: Architecture Whiteboard Template (Repo-Specific)

Use this flow:
- Next.js web (`web/app/page.tsx`) -> FastAPI (`server/main.py`) -> retrieval (`POST /search`, pgvector, rerank, lexical fallback)
- citation policy enforcement (`strict|lenient`) -> Claude generation (`/chat` or `/chat/stream`) -> response + audit log

Discuss:
- Safety/grounding policy:
  - `CITATION_MODE=strict` for policy answers
  - `lenient` only when business accepts `[Unverified]`
- Tool policy:
  - current baseline is retrieval-first without heavy tool usage
  - define future tool gates only for clearly bounded operations (e.g., fee calculation)
- Observability and audit:
  - `/metrics`, `/api/metrics`, `/audit/recent`
  - required audit fields for compliance review
- Cost controls:
  - embedding provider choice (`gemini|openai|local`)
  - cache TTL/LRU sizing
  - retrieval-only eval mode as low-cost gate

Script:
- "This whiteboard is the operating contract: data path, policy checks, and auditability."
- "If we cannot explain it with trace and logs, we should not ship it."

### 45-70 min: Hands-On Validation

- Run live demo with representative support prompts.
- Inspect retrieval with `POST /search`.
- Verify strict citation/refusal behavior on unsupported queries.
- Inspect metrics (`/api/metrics`) and audit output (`/audit/recent`).
- Run evals:
  - `make eval` (or retrieval-focused runs during iteration)

Script:
- "We are validating behavior under policy, not only response fluency."
- "The system passes when it answers grounded questions well and refuses unsafe ones correctly."

### 70-90 min: Decisions and Follow-Up

## Decisions We Will Make Today

- Citation policy by intent: strict vs lenient.
- Embedding provider and retrieval/rerank settings.
- Latency budget and timeout policy.
- Logging/audit retention expectations.
- Auth mode (`none|jwt`) and phased multi-tenant plan.
- Pilot KPI scorecard and review cadence.

Script:
- "By end of session we should have concrete defaults and measurable pilot gates."

## Homework and Follow-Ups

- Data readiness:
  - confirm canonical policy docs
  - run indexer and validate coverage
- Eval readiness:
  - expand `evals/test_cases.jsonl` with customer-specific scenarios
  - include adversarial and edge-policy queries
- Rollout readiness:
  - pilot timeline with owners
  - go/no-go criteria mapped to KPI thresholds

