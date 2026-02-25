# Evaluation Philosophy

## System-Level Eval vs Model-Level Eval

This framework evaluates **systems**, not models in isolation. A Claude-powered application includes retrieval, routing, tool invocation, citation enforcement, and safety policies. Model quality is one variable; system behavior is the deliverable.

Implications:
- Eval cases test end-to-end behavior: prompt -> retrieval -> generation -> scoring.
- Offline mode validates structure, routing, and policy compliance without API calls.
- Online mode adds rubric-based quality scoring via a judge model.

## What We Measure

- **Retrieval quality**: recall@k, MRR, hit rate against labeled gold documents.
- **Groundedness**: are factual claims supported by retrieved evidence?
- **Refusal correctness**: does the system refuse when it should, and comply when it should?
- **Tool discipline**: are tools invoked only when appropriate, with correct arguments?
- **Format compliance**: does structured output match the expected schema?
- **Injection resistance**: does the system resist adversarial content in retrieved documents?
- **Latency**: does the system meet budgeted response times?

## Common Pitfalls

- **Evaluating only happy paths**: always include refusal, injection, and empty-retrieval cases.
- **Conflating model quality with system quality**: a good model in a bad pipeline still fails.
- **Non-reproducible runs**: use stable run IDs, stored traces, and deterministic scoring where possible.
- **Ignoring cost**: online evals are expensive. Use offline mode for regression checks; online for quality audits.

## Offline vs Online

- **Offline**: no API calls, no cost. Tests structure, routing, tool gating, format compliance, and refusal logic. Run frequently.
- **Online**: calls Claude for generation and judge scoring. Tests answer quality, groundedness, and helpfulness. Run selectively.
