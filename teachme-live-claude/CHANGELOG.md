# Changelog

## 2026-02-16

- Ported LLM integration from Gemini to Anthropic Claude Messages API.
- Added app-managed stateless conversation handling by `session_id`.
- Implemented iterative tool loop with schema validation, timeouts, and max-iteration guard.
- Added deterministic tutoring tools: `math_solver` and `grammar_check` with intent-based gating.
- Added safety controls: low-confidence STT clarification, image-upload guardrail, strict structured output + repair fallback.
- Added observability: `/api/metrics` and structured per-turn logging fields.
- Added eval harness (`evals/`) with 30+ cases and offline/full modes.
- Added workshop artifacts for customer discovery, pilot success criteria, and demo narrative.
