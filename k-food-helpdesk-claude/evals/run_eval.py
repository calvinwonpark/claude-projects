import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.prompts.system import SYSTEM_PROMPT
from server.providers.embeddings import build_embeddings_provider
from server.rag.context_builder import build_retrieval_context
from server.rag.reranker import rerank_docs
from server.rag.retriever import Retriever
from server.reliability.citations import enforce_citation_policy


def load_cases(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    arr = sorted(values)
    idx = min(int(len(arr) * p), len(arr) - 1)
    return float(arr[idx])


def parse_cited_ids(citations: list[str]) -> list[str]:
    ids = []
    for citation in citations:
        if citation.startswith("doc:"):
            ids.append(citation.split(":", 1)[1])
    return ids


async def maybe_generate_answer(query: str, docs, context_text: str) -> tuple[str, list[str], float]:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return "", [], 0.0
    try:
        from server.providers.claude_client import ClaudeClient
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Generation eval requires Anthropic SDK. Install dependencies or run `make eval` (containerized)."
        ) from exc

    claude = ClaudeClient(
        api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        primary_model=os.getenv("CLAUDE_PRIMARY_MODEL", "claude-3-5-sonnet-latest"),
        fallback_model=os.getenv("CLAUDE_FALLBACK_MODEL", "claude-3-haiku-latest"),
        extra_models=[
            m.strip()
            for m in os.getenv(
                "CLAUDE_MODEL_CANDIDATES",
                "claude-3-haiku-20240307,claude-3-sonnet-20240229,claude-3-5-haiku-20241022",
            ).split(",")
            if m.strip()
        ],
        temperature=float(os.getenv("CLAUDE_TEMPERATURE", "0.2")),
        max_output_tokens=int(os.getenv("MAX_OUTPUT_TOKENS", "900")),
        request_timeout_ms=int(os.getenv("REQUEST_TIMEOUT_MS", "15000")),
    )
    claude.warmup_model_selection()
    started = time.perf_counter()
    response = await claude.create(
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": "Retrieved context JSON:\n" + context_text},
            {"role": "user", "content": query},
        ],
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    assessment = enforce_citation_policy(response.text, docs, query)
    if (
        os.getenv("CITATION_MODE", "strict").lower() == "strict"
        and not assessment.verified
        and docs
    ):
        allowed_ids = ", ".join(str(d.doc_id) for d in docs)
        repair = await claude.create(
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": "Retrieved context JSON:\n" + context_text},
                {
                    "role": "user",
                    "content": (
                        "Rewrite your previous answer using ONLY the retrieved context. "
                        "Add [doc:<id>] to every factual sentence. "
                        f"Allowed doc ids: {allowed_ids}. "
                        f"Original query: {query}\n"
                        f"Previous draft answer:\n{response.text}"
                    ),
                },
            ],
        )
        assessment = enforce_citation_policy(repair.text, docs, query)
        elapsed_ms = (time.perf_counter() - started) * 1000
    return assessment.answer, assessment.valid_citations, elapsed_ms


async def run() -> None:
    cases = load_cases(ROOT / "evals" / "test_cases.jsonl")
    retriever = Retriever(build_embeddings_provider())
    retrieval_latencies: list[float] = []
    generation_latencies: list[float] = []
    per_case: list[dict[str, Any]] = []

    hit_count = 0
    grounded_count = 0
    citation_precision_num = 0
    citation_precision_den = 0
    citation_recall_num = 0
    citation_recall_den = 0

    for case in cases:
        query = case["query"]
        expected = [str(doc_id) for doc_id in case.get("expected_doc_ids", [])]
        t0 = time.perf_counter()
        docs = retriever.retrieve_top_k_from_text(query, k=int(os.getenv("RAG_TOP_K", "8")))
        docs = rerank_docs(query, docs, mode=os.getenv("RERANK_MODE", "heuristic"))
        retrieval_ms = (time.perf_counter() - t0) * 1000
        retrieval_latencies.append(retrieval_ms)

        retrieved_ids = [str(doc.doc_id) for doc in docs]
        hit = any(doc_id in retrieved_ids for doc_id in expected)
        hit_count += int(hit)

        built = build_retrieval_context(
            docs,
            max_chars=int(os.getenv("RAG_MAX_CONTEXT_CHARS", "6000")),
            snippet_chars=int(os.getenv("RAG_SNIPPET_CHARS", "400")),
        )
        answer = ""
        citations: list[str] = []
        gen_ms = 0.0
        if os.getenv("RUN_GENERATION_EVAL", "true").lower() == "true":
            try:
                answer, citations, gen_ms = await maybe_generate_answer(query, built.included_docs, built.context_text)
            except Exception as exc:
                answer = f"[GENERATION_ERROR] {exc}"
                citations = []
                gen_ms = 0.0
        if gen_ms > 0:
            generation_latencies.append(gen_ms)

        cited_ids = parse_cited_ids(citations)
        valid_cited_ids = [doc_id for doc_id in cited_ids if doc_id in retrieved_ids]
        citation_precision_num += len(valid_cited_ids)
        citation_precision_den += len(cited_ids)

        citation_recall_num += len([doc_id for doc_id in expected if doc_id in cited_ids])
        citation_recall_den += len(expected)

        if expected and valid_cited_ids:
            grounded_count += 1

        per_case.append(
            {
                "id": case["id"],
                "query": query,
                "expected_doc_ids": expected,
                "retrieved_doc_ids": retrieved_ids,
                "hit": hit,
                "citations": citations,
                "answer_preview": answer[:240],
                "retrieval_latency_ms": round(retrieval_ms, 2),
                "generation_latency_ms": round(gen_ms, 2),
            }
        )

    total = len(cases)
    summary = {
        "total_cases": total,
        "retrieval_hit_rate": round(hit_count / total, 4) if total else 0.0,
        "citation_precision": round(citation_precision_num / citation_precision_den, 4) if citation_precision_den else 0.0,
        "citation_recall": round(citation_recall_num / citation_recall_den, 4) if citation_recall_den else 0.0,
        "groundedness_rate": round(grounded_count / total, 4) if total else 0.0,
        "retrieval_latency_ms": {
            "p50": round(percentile(retrieval_latencies, 0.5), 2),
            "p95": round(percentile(retrieval_latencies, 0.95), 2),
            "avg": round(statistics.mean(retrieval_latencies), 2) if retrieval_latencies else 0.0,
        },
        "generation_latency_ms": {
            "p50": round(percentile(generation_latencies, 0.5), 2),
            "p95": round(percentile(generation_latencies, 0.95), 2),
            "avg": round(statistics.mean(generation_latencies), 2) if generation_latencies else 0.0,
        },
    }

    out = {"summary": summary, "cases": per_case}
    out_path = ROOT / "evals" / "results.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nEvaluation Summary")
    print("==================")
    print(f"cases:               {summary['total_cases']}")
    print(f"retrieval_hit_rate:  {summary['retrieval_hit_rate']}")
    print(f"citation_precision:  {summary['citation_precision']}")
    print(f"citation_recall:     {summary['citation_recall']}")
    print(f"groundedness_rate:   {summary['groundedness_rate']}")
    print(f"retrieval p50/p95ms: {summary['retrieval_latency_ms']['p50']} / {summary['retrieval_latency_ms']['p95']}")
    print(f"generation p50/p95ms:{summary['generation_latency_ms']['p50']} / {summary['generation_latency_ms']['p95']}")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    asyncio.run(run())
