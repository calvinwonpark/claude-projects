# How to Add Evaluation Cases

## Case Format

Each case is a single line in a JSONL file under `cases/suites/`.

### Minimal Case

```json
{
  "id": "my_case_01",
  "category": "rag",
  "input": {
    "prompt": "What is the refund policy?"
  },
  "expectations": {
    "required_citations": true,
    "gold_doc_ids": ["policies_refund"]
  }
}
```

### Full Case (All Fields)

```json
{
  "id": "my_case_02",
  "category": "tool",
  "input": {
    "prompt": "Calculate unit economics with ARPU $29.",
    "language": "en",
    "system": "You are a financial advisor.",
    "attachments": [],
    "metadata": {"domain": "finance"}
  },
  "expectations": {
    "expected_refusal": false,
    "expected_tools": ["unit_economics"],
    "required_citations": false,
    "gold_doc_ids": null,
    "output_schema": null,
    "latency_budget_ms": 5000,
    "notes": "Should invoke unit_economics tool"
  }
}
```

## Categories

| Category | Purpose |
|----------|---------|
| rag | Retrieval-grounded answers |
| tool | Tool invocation correctness |
| refusal | Refusal/compliance behavior |
| injection | Prompt injection resistance |
| routing | Agent/strategy selection |
| streaming | Real-time behavior |
| structured | Output format validation |
| general | Uncategorized |

## Tips

- Use `gold_doc_ids` that match your fixture documents for retrieval scoring.
- Set `expected_tools` to an empty list `[]` when NO tools should be invoked.
- Use `expected_refusal: true` for cases that should be refused.
- Add `notes` to document the intent of tricky cases.
- Keep case IDs unique and descriptive.
