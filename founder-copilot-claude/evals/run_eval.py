import json
import os
import statistics
import time
import asyncio
import re
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.providers.embeddings import build_embeddings_provider
from app.providers.claude_client import ClaudeClient
from app.rag import Retriever, apply_citation_mode, build_context
from app.router.router import route_query
from app.tools import should_invoke_tool


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    arr = sorted(values)
    idx = min(int(len(arr) * p), len(arr) - 1)
    return round(arr[idx], 2)


def load_cases() -> list[dict]:
    p = ROOT / "evals" / "test_cases.jsonl"
    with p.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _first_slide_number(answer: str) -> int | None:
    txt = (answer or "").strip()
    if not txt:
        return None
    # Support structured investor output (JSON) as well as rendered markdown.
    try:
        obj = json.loads(txt)
        if isinstance(obj, dict):
            slides = obj.get("slides")
            if isinstance(slides, list) and slides:
                first = slides[0]
                if isinstance(first, dict) and "number" in first:
                    return int(first["number"])
    except Exception:
        pass
    m = re.search(r"(^|\n)\s*(\d+)\.\s", txt)
    if not m:
        return None
    try:
        return int(m.group(2))
    except Exception:
        return None


async def main():
    eval_mode = os.getenv("EVAL_MODE", "retrieval_only").lower()
    cases = load_cases()
    retriever = Retriever(build_embeddings_provider())
    claude = None
    if eval_mode == "full" and os.getenv("ANTHROPIC_API_KEY"):
        claude = ClaudeClient(
            api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            primary_model=os.getenv("CLAUDE_PRIMARY_MODEL", "claude-3-5-sonnet-latest"),
            fallback_model=os.getenv("CLAUDE_FALLBACK_MODEL", "claude-3-5-haiku-latest"),
            extra_models=[m.strip() for m in os.getenv("CLAUDE_MODEL_CANDIDATES", "").split(",") if m.strip()],
            timeout_ms=int(os.getenv("REQUEST_TIMEOUT_MS", "20000")),
        )
        # Match server behavior: resolve to actually available models for this account.
        claude.warmup_model_selection()

    routing_ok = 0
    grounded_ok = 0
    tool_ok = 0
    retrieval_hit_ok = 0
    citation_precision_hits = 0
    citation_precision_total = 0
    citation_recall_hits = 0
    citation_recall_total = 0
    retrieval_lat = []
    generation_lat = []
    token_estimate = 0
    token_in = 0
    token_out = 0
    pitch_outline_total = 0
    pitch_outline_starts_at_one = 0
    rows = []

    for case in cases:
        q = case["query"]
        expected_agent = case["expected_agent"]
        acceptable_agents = set(case.get("acceptable_agents", []))
        acceptable_agents.add(expected_agent)
        expected_docs = set(case.get("expected_doc_ids", []))
        expected_tool = case.get("expected_tool", "")

        trace = route_query(q)
        selected = trace["selected_agent"]
        routing_ok += int(selected in acceptable_agents)

        docs, r_ms = retriever.retrieve(q, top_k=int(os.getenv("RETRIEVAL_TOP_K", "8")))
        retrieval_lat.append(r_ms)
        retrieved_ids = {d.doc_id for d in docs}
        hit = bool(expected_docs.intersection(retrieved_ids))
        retrieval_hit_ok += int(hit)

        answer = ""
        citations: list[str] = []
        verification = "not_run"
        model_name = None
        gen_ms = 0.0
        if eval_mode == "full" and claude:
            system = (
                "Answer using only retrieved context. "
                "For grounded claims use inline citations in format [doc:<doc_id>]. "
                "If evidence is insufficient, say so and ask one clarifying question."
            )
            context = build_context(docs, max_chars=7000)
            messages = [
                {"role": "user", "content": "Retrieved context JSON:\n" + context},
                {"role": "user", "content": q},
            ]
            g0 = time.perf_counter()
            try:
                resp = await claude.create(system=system, messages=messages, tools=[])
                answer = resp.text
                model_name = resp.model
                token_in += int(resp.input_tokens or 0)
                token_out += int(resp.output_tokens or 0)
            except Exception as exc:
                answer = f"Generation error: {exc}"
            gen_ms = (time.perf_counter() - g0) * 1000
            answer, citations, verification = apply_citation_mode(answer, docs, q)
        generation_lat.append(gen_ms)
        token_estimate += len(q.split()) + len(answer.split())
        grounded_ok += int(verification == "verified" and len(citations) > 0 and bool(expected_docs))

        cited_ids = {c.split(":", 1)[1] for c in citations if ":" in c}
        citation_precision_total += len(cited_ids)
        citation_precision_hits += sum(1 for cid in cited_ids if cid in retrieved_ids)
        if expected_docs:
            citation_recall_total += len(expected_docs)
            citation_recall_hits += sum(1 for eid in expected_docs if eid in cited_ids)

        planned_tool = ""
        for tool_name in ("market_size_lookup", "unit_economics_calculator", "competitor_summary"):
            if should_invoke_tool(q, tool_name):
                planned_tool = tool_name
                break
        tool_ok += int(planned_tool == expected_tool)

        if "pitch deck" in q.lower():
            pitch_outline_total += 1
            first_num = _first_slide_number(answer)
            pitch_outline_starts_at_one += int(first_num == 1)
            if eval_mode == "full" and answer and first_num != 1:
                raise AssertionError(f"Pitch deck outline must start at 1 for case {case['id']}, got: {first_num}")

        rows.append(
            {
                "id": case["id"],
                "query": q,
                "selected_agent": selected,
                "expected_agent": expected_agent,
                "acceptable_agents": sorted(acceptable_agents),
                "retrieved_doc_ids": sorted(retrieved_ids),
                "expected_doc_ids": sorted(expected_docs),
                "citations": citations,
                "verification": verification,
                "expected_tool": expected_tool,
                "planned_tool": planned_tool,
                "retrieval_hit": hit,
                "answer_preview": answer[:280],
                "model": model_name,
                "latency_ms": {"retrieval": round(r_ms, 2), "generation": round(gen_ms, 2)},
                "first_slide_number": _first_slide_number(answer),
            }
        )

    total = len(cases)
    citation_precision = (citation_precision_hits / citation_precision_total) if citation_precision_total else 0.0
    citation_recall = (citation_recall_hits / citation_recall_total) if citation_recall_total else 0.0
    summary = {
        "eval_mode": eval_mode,
        "total_cases": total,
        "routing_accuracy": round(routing_ok / total, 4) if total else 0.0,
        "retrieval_hit_rate": round(retrieval_hit_ok / total, 4) if total else 0.0,
        "groundedness_rate": round(grounded_ok / total, 4) if total else 0.0,
        "citation_precision": round(citation_precision, 4),
        "citation_recall": round(citation_recall, 4),
        "tool_correctness_rate": round(tool_ok / total, 4) if total else 0.0,
        "latency_ms": {
            "retrieval_p50": percentile(retrieval_lat, 0.5),
            "retrieval_p95": percentile(retrieval_lat, 0.95),
            "generation_p50": percentile(generation_lat, 0.5),
            "generation_p95": percentile(generation_lat, 0.95),
            "retrieval_avg": round(statistics.mean(retrieval_lat), 2) if retrieval_lat else 0.0,
        },
        "token_usage": {"input": token_in, "output": token_out, "estimated_total_words": token_estimate},
        "pitch_outline_starts_at_one_rate": round(pitch_outline_starts_at_one / pitch_outline_total, 4)
        if pitch_outline_total
        else 0.0,
    }
    output = {"summary": summary, "cases": rows}
    out_path = ROOT / "evals" / "results.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Evaluation Summary")
    print("==================")
    print(f"cases: {summary['total_cases']}")
    print(f"eval_mode: {summary['eval_mode']}")
    print(f"routing_accuracy: {summary['routing_accuracy']}")
    print(f"retrieval_hit_rate: {summary['retrieval_hit_rate']}")
    print(f"citation_precision: {summary['citation_precision']}")
    print(f"citation_recall: {summary['citation_recall']}")
    print(f"groundedness_rate: {summary['groundedness_rate']}")
    print(f"tool_correctness_rate: {summary['tool_correctness_rate']}")
    print(f"retrieval p50/p95 (ms): {summary['latency_ms']['retrieval_p50']} / {summary['latency_ms']['retrieval_p95']}")
    print(f"generation p50/p95 (ms): {summary['latency_ms']['generation_p50']} / {summary['latency_ms']['generation_p95']}")
    print(f"token usage in/out: {summary['token_usage']['input']} / {summary['token_usage']['output']}")
    print(f"pitch outline starts-at-1 rate: {summary['pitch_outline_starts_at_one_rate']}")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
