# Scoring Rubrics

## Overview

Scoring has two layers:

1. **Deterministic scoring** (offline + online): format checks, refusal correctness, tool precision/recall, retrieval metrics, injection resistance.
2. **Judge scoring** (online only): Claude evaluates response quality against YAML rubric prompts.

## Deterministic Scorers

These require no API calls and are always applied:

| Scorer | Condition | Metric |
|--------|-----------|--------|
| format_valid | `output_schema` set | bool |
| refusal_correct | `expected_refusal` set | bool |
| citations_present | `required_citations` set | bool |
| tool_precision / tool_recall | `expected_tools` set | float |
| recall_at_k / mrr | `gold_doc_ids` set | float |
| latency_within_budget | `latency_budget_ms` set | bool |
| injection_resisted | category = injection | bool |

## Judge Rubrics

Located in `evalkit/scoring/rubrics/`. Each YAML defines:
- `criteria`: what the judge evaluates
- `scale`: scoring range (typically 0-5)
- `pass_threshold`: minimum score to pass

Available rubrics:
- **groundedness**: are all claims supported by retrieved evidence?
- **refusal**: does refusal/compliance behavior match expectations?
- **tool_use**: was tool invocation appropriate and accurate?
- **helpfulness**: is the response useful, clear, and actionable?

## How the Judge Works

1. A prompt is constructed from the rubric YAML, the user prompt, the model response, and retrieved context.
2. Claude (judge model) returns a JSON object: `{score, pass, reasons}`.
3. Invalid JSON triggers one retry.
4. Results are merged into the case Score.

## Adding Custom Rubrics

Create a new YAML in `evalkit/scoring/rubrics/` following the existing format. Register the rubric name in `scoring/registry.py` under the appropriate category.
