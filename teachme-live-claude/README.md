# TeachMe Live Claude

> This folder is the Claude port of the original Gemini implementation.  
> The original `teachme-live-gemini/` project is intentionally left unchanged.

Portfolio-grade realtime voice tutoring stack for Anthropic Product Engineer (Applied AI, Seoul):
- mic -> WebSocket -> streaming STT -> Claude -> streaming TTS -> playback
- optional image upload
- language toggle + translator mode
- tool-loop discipline + safety guardrails + evals + metrics

## Architecture

```text
Browser (AudioWorklet + VAD + WS + playback)
    |
    v
FastAPI WebSocket (/ws)
  - Turn controller (barge-in, cancel, max turn caps)
  - STT confidence checks + clarification fallback
  - Agent runtime (Claude tool loop, strict structured output)
  - Safety guardrails (image-required checks, no fabricated image claims)
  - TTS streaming chunks
    |
    +--> Google Cloud STT (streaming_recognize)
    +--> Anthropic Claude Messages API
    +--> Google Cloud TTS (LINEAR16)
```

## Streaming vs Tools (Anthropic Engineer Notes)

This runtime intentionally splits generation into two paths:

1) **Streaming path (fast path, no tools needed)**
- We call Claude with real Messages streaming and emit `LLM_DELTA` over WebSocket as tokens arrive.
- This is the lowest-latency path and is used for most conversational tutoring turns.
- We still enforce guardrails before speaking (low-confidence STT, image-required checks, turn cancellation).

2) **Tool path (deterministic path, tools needed)**
- We call Claude with tool schemas and run an iterative tool loop:
  - inspect `tool_use` blocks
  - validate args
  - execute tool with timeout/allowlist
  - append `tool_result`
  - call Claude again (bounded by `TOOL_MAX_ITERS`)
- This path prioritizes correctness over first-token speed.
- After tool resolution, we send final structured output (and speak the final synthesized answer).

### Why this split exists
- Tool turns need deterministic execution boundaries; fully token-streaming through unresolved tool calls can leak partial/speculative reasoning.
- Non-tool turns benefit most from real-time deltas (`LLM_DELTA`) and keep voice UX responsive.
- This design keeps latency low in the common case while preserving reliability where tool correctness matters.

### Operational behavior
- **Barge-in:** new speech cancels in-flight generation/TTS for the active turn.
- **Structured contract:** tutoring output is normalized to JSON keys (`answer`, `steps`, `examples`, `common_mistakes`, `next_exercises`).
- **Timeout budgets:** standard turns use `TIME_BUDGET_MS`; image turns can use `IMAGE_TIME_BUDGET_MS`.
- **Fallbacks:** if budget is exceeded, we return a safe short summary rather than hanging the turn.

## Quickstart

1. Copy env template:
```bash
cp ENV_EXAMPLE.txt .env
```
2. Fill `ANTHROPIC_API_KEY` and `GOOGLE_APPLICATION_CREDENTIALS`.
3. Run:
```bash
docker compose up --build
```
4. Open:
```text
http://localhost:8000
```

## Reliability + Safety Features

- Session-scoped turn controller with cancellation on new speech segment.
- Hard caps: `TURN_MAX_SECONDS`, `MAX_AUDIO_BYTES`.
- STT low-confidence fallback -> clarification question (target language).
- Image guardrail: asks for upload if user asks image-specific questions without image.
- Structured tutoring response contract:
  - `answer`, `steps`, `examples`, `common_mistakes`, `next_exercises`
- Strict mode JSON repair retry; safe fallback if still invalid.
- Tool loop correctness with max tool iterations + per-tool timeout.
- Tool gating:
  - `math_solver` only for math-like intent
  - `grammar_check` only for grammar intent or translator mode

## Cost Controls

- No Vertex AI dependencies.
- Uses Claude directly via Anthropic SDK.
- Tool gating minimizes unnecessary tool calls.
- Offline eval mode requires no paid API calls.

## Metrics

`GET /api/metrics` returns:
- `stt_latency_ms` p50/p95
- `llm_latency_ms` p50/p95
- `tts_latency_ms` p50/p95
- `end_to_end_turn_latency_ms` p50/p95
- `tool_calls_total`
- `tool_failures_total`
- `transcripts_low_confidence_total`
- `active_sessions`

## Evals

Run:
```bash
make eval
```

Modes:
- `--mode offline` (default): mock-compatible, no paid API calls
- `--mode full`: small API-backed subset (requires Anthropic key)

Outputs:
- `evals/results.json`
- printed summary:
  - `format_valid_rate`
  - `tool_precision` / `tool_recall`
  - `guardrail_pass_rate`
  - `avg_latency_ms`

## Make Commands

- `make dev`
- `make eval`
- `make eval-realtime-smoke`
- `make lint`

## What I'd Change for Production at a Customer

- Move in-memory sessions to Redis + distributed turn workers.
- Add authN/authZ and tenant-scoped usage controls.
- Add persistent audit logging and PII redaction pipeline.
- Add STT/TTS provider fallback policy and circuit breaking.
- Add canary release + regression gates around realtime latency and format validity.
