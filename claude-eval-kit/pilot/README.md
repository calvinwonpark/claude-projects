# Pilot Evaluation Pack

This directory contains customer-ready artifacts for running a structured Claude pilot evaluation.

## Contents

- `success_criteria.md` — KPI definitions and target thresholds
- `eval_plan.md` — 2-4 week pilot plan with weekly checkpoints
- `acceptance_gates.yaml` — machine-readable go/no-go gate definitions (online mode)
- `acceptance_gates_offline.yaml` — deterministic-only gates (offline scoring mode)
- `datasets/` — curated pilot evaluation suites
- `scorecards/` — rubric definitions for judge scoring

## Quick Start (3 Commands)

The pilot pack is designed to run against a real system via the HTTP adapter. MODE controls scoring (offline = deterministic only, online = + judge). The adapter controls execution.

```bash
# 1. Run pilot suite against your app (offline scoring, real execution)
evalkit run --suite pilot/datasets/pilot_core.jsonl --mode offline --adapter http

# 2. Check acceptance gates
evalkit gate --run runs/<run_id> --policy pilot/acceptance_gates_offline.yaml

# 3. Generate stakeholder report
evalkit pilot-report --run runs/<run_id> --policy pilot/acceptance_gates_offline.yaml
```

For formal pilot checkpoints with judge scoring:

```bash
evalkit run --suite pilot/datasets/pilot_core.jsonl --mode online --adapter http
evalkit gate --run runs/<run_id> --policy pilot/acceptance_gates.yaml
evalkit pilot-report --run runs/<run_id> --policy pilot/acceptance_gates.yaml
```

## Adapter vs Mode

| Flag | Controls | Options |
|------|----------|---------|
| `--mode` | Which scorers run | `offline` (deterministic only) / `online` (+ judge) |
| `--adapter` | Where traces come from | `http` (your app) / `anthropic` (direct API) / `offline_stub` (placeholder) |

- Use `--adapter http` for pilot evaluations against your running application.
- Use `--adapter offline_stub` only for framework sanity tests (CI). Stub traces will not pass pilot gates.
- Your app can set `EVAL_MODE=retrieval_only` to keep cost low during offline-scored pilot runs.

## Interpreting Results

**Gate check output** prints a table of each gate with actual value, threshold, and pass/fail status.
- Exit code `0`: all gates passed. Pilot is on track.
- Exit code `1`: one or more gates failed. Review the pilot report for failure details and recommendations.

**Pilot report** (`pilot_report.md`) contains:
1. Executive summary with overall pass/fail
2. KPI table with metric, target, actual, and status
3. Top failure modes with case IDs
4. Recommendations based on which gates failed
5. Next steps checklist

## CI Usage

CI runs framework tests with `--adapter offline_stub` against generic suites (not pilot datasets). Pilot gate checks require a real app endpoint and are run locally or in integration pipelines:

```bash
# CI (framework only)
evalkit run --suite cases/suites/rag_core.jsonl --mode offline --adapter offline_stub --max-cases 5

# Integration pipeline (pilot)
evalkit run --suite pilot/datasets/pilot_core.jsonl --mode offline --adapter http
```

## Adding Customer-Specific Cases

1. Create new `.jsonl` files in `pilot/datasets/` following the Case schema.
2. Add `gold_doc_ids` for RAG cases that reference fixture documents.
3. Set `expected_refusal`, `expected_tools`, and `required_citations` per case.
4. Run and validate: `evalkit run --suite pilot/datasets/<your_file>.jsonl --mode offline --adapter http`
