# Demo Script (Recruiter / Customer Ready)

## 1) Start and Verify
1. Run `docker compose up --build`.
2. Open `http://localhost:8000`.
3. Show that session starts and live transcript updates.

## 2) Translator Mode
1. Enable translator mode.
2. Speak Korean with target language set to English.
3. Show English tutoring output and spoken response.

## 3) Tutoring Structured Output
1. Ask for a concept explanation ("Explain quadratic equations").
2. Click "Update Notes".
3. Show structured JSON contract fields in notes panel.

## 4) Tool Loop Discipline
1. Ask a math question ("calculate 12*7 + 5").
2. Explain that tool gating selected `math_solver`.
3. Ask grammar correction ("correct: i am agree with you").
4. Explain deterministic `grammar_check` usage.

## 5) Image Guardrail
1. Ask "What does this image say?" before uploading any image.
2. Show safe refusal asking user to upload an image first.
3. Upload image and repeat question to show grounded behavior.

## 6) Metrics + Evals
1. Open `/api/metrics`.
2. Highlight p50/p95 latency and tool counters.
3. Run `python evals/run_eval.py --mode offline`.
4. Show `evals/results.json` summary metrics.
