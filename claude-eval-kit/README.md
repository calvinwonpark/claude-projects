# Claude Eval Kit

Production evaluation framework for Claude-powered systems. Evaluates RAG pipelines, tool usage, refusal behavior, prompt injection resistance, and streaming reliability with offline and online modes, regression baselines, and professional reporting.

Built for teams running Claude in production who need measurable quality gates, not ad-hoc spot checks.

## Architecture

```text
cases/suites/*.jsonl          (test cases with expectations)
        |
        v
evalkit/runners/runner.py     (load suite, dispatch to adapter, score, aggregate)
        |
        +---> adapters/       (offline | http_app | anthropic_messages)
        |
        +---> scoring/        (deterministic checks + optional LLM judge)
        |       |
        |       +---> rubrics/*.yaml  (groundedness, refusal, tool_use, helpfulness)
        |
        +---> reporting/      (aggregate, diff, render markdown)
        |
        v
runs/<run_id>/
  - manifest.json             (config snapshot)
  - results.jsonl             (trace + score per case)
  - summary.json              (metric aggregates)
  - report.md                 (human-readable report)
  - diff.md                   (regression comparison)
```

## Quickstart

```bash
# Install
pip install -e ".[dev]"

# Run offline eval (no API keys needed)
evalkit run --suite cases/suites/rag_core.jsonl --mode offline

# Generate report
evalkit report --run runs/<run_id> --format md

# Seed a baseline
python scripts/seed_baseline.py

# Compare against baseline
evalkit diff --baseline baselines/main --run runs/<run_id>
```

## Key Features

- **Offline mode**: no API keys, no cost. Validates structure, routing, tool gating, format compliance, and refusal logic.
- **Online mode**: calls Claude for generation and rubric-based judge scoring. Tests answer quality and groundedness.
- **Deterministic scoring**: format validation, refusal correctness, citation detection, tool precision/recall, retrieval recall@k, MRR, injection resistance.
- **Judge scoring**: YAML rubric-driven LLM evaluation for groundedness, helpfulness, tool use, and refusal quality.
- **Regression diffing**: compare runs against baselines with configurable thresholds. Fail CI on regressions.
- **Professional artifacts**: `results.jsonl`, `summary.json`, `report.md`, `diff.md` per run.
- **Adapter system**: plug in any backend (HTTP endpoint, direct Anthropic API, or custom).

## Case Suites

| Suite | Cases | Focus |
|-------|-------|-------|
| `rag_core.jsonl` | 12 | Citation grounding, retrieval quality |
| `tool_use.jsonl` | 10 | Tool invocation precision, false-positive gating |
| `refusal.jsonl` | 12 | Refusal/compliance correctness |
| `multilingual_ko_en.jsonl` | 10 | Korean/English language adherence |
| `prompt_injection.jsonl` | 10 | Injection resistance via adversarial docs |

## Scoring Dimensions

| Metric | Type | Mode |
|--------|------|------|
| format_valid | deterministic | offline + online |
| refusal_correct | deterministic | offline + online |
| citations_present | deterministic | offline + online |
| tool_precision / tool_recall | deterministic | offline + online |
| recall_at_k / mrr | deterministic | offline + online |
| injection_resisted | deterministic | offline + online |
| latency_within_budget | deterministic | online |
| groundedness (judge) | rubric | online |
| helpfulness (judge) | rubric | online |
| tool_use (judge) | rubric | online |
| refusal (judge) | rubric | online |

## Integrating with Your App

Point the HTTP adapter at your application:

```bash
# In .env
HTTP_ENDPOINT=http://localhost:8000/api/eval

# Run
evalkit run --suite cases/suites/rag_core.jsonl --mode online --adapter http
```

Your endpoint receives `{case_id, prompt, language, metadata}` and returns `{text, retrieval?, tools?, structured?, refusal_flag?, tokens_in?, tokens_out?}`. See `docs/how_to_integrate_with_apps.md` for the full contract.

## Example Report Snippet

```
# Evaluation Report

**Run ID:** `20260216_143022_a1b2c3d4`
**Suite:** `cases/suites/rag_core.jsonl`
**Mode:** `offline`

**Total:** 12 | **Passed:** 10 | **Failed:** 2

## Metrics

| Metric           | Value  |
|------------------|--------|
| pass_rate        | 0.8333 |
| avg_refusal_correct | 1.0000 |
| avg_citations_present | 0.8333 |
```

## Cost Controls

- **Default offline**: no API calls, zero cost. Use for every commit.
- **Online subset**: `--max-cases 10` to limit API spend.
- **Judge model**: defaults to a cheaper model (`claude-haiku-4-5-20251001`).
- **Baseline diffing**: catch regressions without re-running full online suites.

## Make Targets

```bash
make install          # pip install -e ".[dev]"
make eval             # offline eval
make eval-online      # online eval (requires ANTHROPIC_API_KEY)
make baseline         # seed baseline
make test             # pytest
```

## Pilot Pack (Go/No-Go Gates)

The `pilot/` directory contains a customer-ready evaluation pack for structured pilot validation. It translates eval metrics into explicit acceptance thresholds with machine-readable gate definitions.

MODE controls scoring (offline = deterministic only, online = + judge). The `--adapter` flag controls where traces come from (`http` for your app, `anthropic` for direct API, `offline_stub` for framework tests).

```bash
# Run pilot suite against your app (offline scoring, real execution)
evalkit run --suite pilot/datasets/pilot_core.jsonl --mode offline --adapter http

# Check acceptance gates
evalkit gate --run runs/<run_id> --policy pilot/acceptance_gates_offline.yaml

# Generate stakeholder report
evalkit pilot-report --run runs/<run_id> --policy pilot/acceptance_gates_offline.yaml
```

Contents:
- `pilot/success_criteria.md` — KPI definitions and target thresholds
- `pilot/eval_plan.md` — 2-4 week pilot plan with weekly checkpoints
- `pilot/acceptance_gates.yaml` — go/no-go gates (online mode with judge scoring)
- `pilot/acceptance_gates_offline.yaml` — deterministic-only gates (offline scoring)
- `pilot/datasets/` — curated pilot evaluation suites (core, injection, refusal)
- `pilot/scorecards/` — rubric definitions for judge scoring

Gate check exits with code `0` (pass) or `1` (fail). Pilot report includes executive summary, KPI table, failure modes, recommendations, and next steps.

## Documentation

- `docs/evaluation_philosophy.md` — system-level eval vs model eval
- `docs/scoring_rubrics.md` — rubric design and judge mechanics
- `docs/how_to_add_cases.md` — case format and templates
- `docs/how_to_integrate_with_apps.md` — HTTP adapter contract

## What to Look at First

1. `evalkit/types.py` — data model (Case, Trace, Score, RunSummary)
2. `evalkit/scoring/deterministic.py` — all offline scoring logic
3. `evalkit/scoring/rubrics/*.yaml` — judge rubric definitions
4. `cases/suites/rag_core.jsonl` — example case suite
5. `evalkit/runners/runner.py` — end-to-end run orchestration
6. `evalkit/reporting/diff.py` — regression detection logic
