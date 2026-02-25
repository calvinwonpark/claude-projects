# Pilot Evaluation Plan (2-4 Weeks)

## Week 0: Setup

- Install `claude-eval-kit` and configure `.env` with API keys.
- Seed pilot datasets with customer-specific cases added to `pilot/datasets/`.
- Run baseline: `evalkit run --suite pilot/datasets/pilot_core.jsonl --mode offline`
- Seed baseline: `python scripts/seed_baseline.py`
- Validate infrastructure: endpoint connectivity, credentials, timeout budgets.
- Stakeholder alignment: confirm success criteria from `pilot/success_criteria.md`.

Deliverable: baseline `summary.json` stored in `baselines/main/`.

## Week 1: Baseline + First Online Run

- Run full pilot suites (offline + online):
  ```
  evalkit run --suite pilot/datasets/pilot_core.jsonl --mode online
  evalkit run --suite pilot/datasets/pilot_injection.jsonl --mode online
  evalkit run --suite pilot/datasets/pilot_refusal.jsonl --mode online
  ```
- Run gate check: `evalkit gate --run runs/<id> --policy pilot/acceptance_gates.yaml`
- Generate pilot report: `evalkit pilot-report --run runs/<id> --policy pilot/acceptance_gates.yaml`
- Review top failures with engineering team.
- Add customer-specific edge cases to datasets based on observed gaps.

Deliverable: Week 1 pilot report shared with stakeholders.

## Week 2: Hardening

- Address top failure modes from Week 1 (prompt tuning, retrieval quality, tool gating).
- Re-run pilot suites and compare against Week 1 baseline with `evalkit diff`.
- Validate injection resistance improvements.
- Add adversarial cases discovered during review.
- Mid-pilot stakeholder check-in with updated metrics.

Deliverable: Week 2 report showing metric trend vs Week 1.

## Week 3: Rollout Readiness

- Final full pilot run across all suites.
- Gate check with production thresholds: `evalkit gate --policy pilot/acceptance_gates.yaml`
- Generate final pilot report.
- Go/no-go decision based on `acceptance_gates.yaml` criteria.
- If go: document rollout plan, monitoring thresholds, escalation paths.
- If no-go: document gaps, extend pilot with focused remediation plan.

Deliverable: Final pilot report + go/no-go recommendation.

## Data Requirements

- Customer-provided: representative queries, expected refusal scenarios, domain-specific edge cases.
- Framework-provided: injection fixtures, refusal templates, citation-required patterns.
- Minimum: 40 cases across core, injection, and refusal suites for statistical significance.

## Stakeholder Cadence

- Weekly: pilot report review with PM, Engineering, Security.
- Ad-hoc: failure triage after each run if pass rate drops below threshold.
