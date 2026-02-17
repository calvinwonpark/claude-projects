# Customer Workshop Outline (Claude Realtime Tutoring)

## Discovery
- Which learner personas are in-scope (K-12, test prep, adult ESL)?
- What latency is acceptable for "natural" voice turn-taking?
- What content can the model cite (lesson notes, workbook pages, LMS)?
- What refusal behavior is required for uncertain or missing context?

## Architecture Options
- Option A: Single region FastAPI + Claude + GCP STT/TTS (pilot speed).
- Option B: Multi-region edge WS ingress + regional inference workers.
- Option C: Add retrieval service for lesson corpus with citation policy.

## Evaluation Plan
- Baseline with offline eval suite (format/tool/guardrail).
- Run controlled pilot sessions with target latency SLO and tutor CSAT.
- Capture failure taxonomy: low-confidence STT, wrong tool trigger, invalid JSON.

## Rollout + Safety Checklist
- Enable strict structured mode and image guardrails by default.
- Monitor `/api/metrics` p95 latency and low-confidence transcript rates daily.
- Add escalation path for ambiguous safety responses to human educators.
- Weekly review: transcript samples, tool precision/recall, learner feedback.
