# How to Integrate with Applications

## HTTP Adapter

The HTTP adapter (`evalkit/adapters/http_app.py`) calls your application endpoint for each case and collects a trace.

### Contract

**Request** (POST to your endpoint):

```json
{
  "case_id": "rag_01",
  "prompt": "What is the refund policy?",
  "language": "en",
  "metadata": {},
  "attachments": []
}
```

**Response** (your app returns):

```json
{
  "text": "The refund policy allows returns within 14 days. [doc:policies_refund]",
  "model": "claude-sonnet-4-5-20250929",
  "retrieval": {
    "query": "refund policy",
    "candidates": ["policies_refund", "product_faq", "policies_delivery"],
    "selected": ["policies_refund"],
    "k": 3
  },
  "tools": [],
  "structured": null,
  "refusal_flag": false,
  "tokens_in": 150,
  "tokens_out": 80
}
```

### Minimal Response

If your app only returns text:

```json
{
  "text": "The refund policy allows returns within 14 days."
}
```

The adapter will fill empty trace fields. Richer responses enable more scoring dimensions.

### Configuration

Set in `.env`:

```
HTTP_ENDPOINT=http://localhost:8000/api/eval
TIMEOUT_S=30
```

### Running

```bash
evalkit run --suite cases/suites/rag_core.jsonl --mode online --adapter http
```

## Anthropic Direct Adapter

For testing Claude directly without an application layer:

```bash
evalkit run --suite cases/suites/refusal.jsonl --mode online --adapter anthropic
```

This calls Claude Messages API directly and is useful for model-level baselines before system integration.

## Adding a Custom Adapter

1. Create a new file in `evalkit/adapters/`.
2. Subclass `BaseAdapter` and implement `async run_case(case, run_id) -> Trace`.
3. Register it in `runners/runner.py` `_get_adapter()`.
