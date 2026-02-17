import argparse
import asyncio
import json
import os
import statistics
import time
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.runtime import parse_structured_json
from agent.runtime import run_tutor_turn
from app.config import settings
from app.tools.registry import available_tools_for_query


def load_cases() -> list[dict]:
    path = ROOT / "evals" / "test_cases.jsonl"
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def offline_response(case: dict) -> str:
    target = case.get("target_language", "en")
    if case.get("expect_guardrail"):
        return (
            '{"answer":"If this is about an image, please upload it first.","steps":[],"examples":[],"common_mistakes":[],"next_exercises":[]}'
            if target == "en"
            else '{"answer":"이미지 관련 질문이면 먼저 이미지를 업로드해 주세요.","steps":[],"examples":[],"common_mistakes":[],"next_exercises":[]}'
        )
    return json.dumps(
        {
            "answer": "Mock tutoring answer",
            "steps": ["Step 1", "Step 2"],
            "examples": ["Example A"],
            "common_mistakes": ["Mistake A"],
            "next_exercises": ["Exercise A"],
        },
        ensure_ascii=False,
    )


def mock_stream_events(case: dict) -> list[dict]:
    if case.get("expect_llm_delta_before_final"):
        return [
            {"type": "llm_delta", "text": "{", "final": False},
            {"type": "llm_delta", "text": '"answer":"mock"', "final": False},
            {"type": "llm_delta", "text": "}", "final": True},
        ]
    return [{"type": "llm_delta", "text": "", "final": True}]


def llm_delta_before_final(events: list[dict]) -> bool:
    saw_non_final = False
    for ev in events:
        if ev.get("type") != "llm_delta":
            continue
        if not ev.get("final"):
            saw_non_final = True
        if ev.get("final"):
            return saw_non_final
    return False


def _is_valid_structured(obj: dict | None) -> bool:
    if not isinstance(obj, dict):
        return False
    keys = ["answer", "steps", "examples", "common_mistakes", "next_exercises"]
    if not all(k in obj for k in keys):
        return False
    if not isinstance(obj.get("answer"), str):
        return False
    return all(isinstance(obj.get(k), list) for k in keys[1:])


async def full_response(client, case: dict) -> dict:
    # Evaluate the same runtime path used by the app (tool gating + strict repair + fallback).
    result = await run_tutor_turn(
        claude=client,
        conversation_messages=[{"role": "user", "content": [{"type": "text", "text": case["input"]}]}],
        query=case["input"],
        target_language=case.get("target_language", "en"),
        translator_mode=bool(case.get("translator_mode")),
        on_token=None,
    )
    return {
        "raw_text": result.raw_text,
        "structured": result.structured,
        "tool_calls": [t.get("name") for t in result.tool_calls],
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default=os.getenv("EVAL_MODE", "offline"), choices=["offline", "full"])
    parser.add_argument("--suite", default="default")
    args = parser.parse_args()

    cases = load_cases()
    if args.suite == "realtime_smoke":
        cases = cases[:8]
    elif args.mode == "full":
        full_cases = int(os.getenv("EVAL_FULL_CASES", "6"))
        cases = cases[: max(1, full_cases)]

    client = None
    if args.mode == "full" and settings.anthropic_api_key:
        from app.llm.anthropic_client import AnthropicClient

        client = AnthropicClient(settings.anthropic_api_key)
    format_ok = 0
    tool_tp = 0
    tool_fp = 0
    tool_fn = 0
    guardrail_pass = 0
    stream_order_pass = 0
    latencies = []
    rows = []

    for case in cases:
        t0 = time.perf_counter()
        if args.mode == "offline":
            out = offline_response(case)
            structured_obj = parse_structured_json(out)
        else:
            if client is None:
                out = offline_response(case)
                structured_obj = parse_structured_json(out)
            else:
                full_out = await full_response(client, case)
                out = full_out["raw_text"]
                structured_obj = full_out.get("structured")
        latency_ms = (time.perf_counter() - t0) * 1000
        latencies.append(latency_ms)

        parsed = structured_obj if _is_valid_structured(structured_obj) else parse_structured_json(out)
        format_ok += int(parsed is not None and _is_valid_structured(parsed))

        offered = available_tools_for_query(case["input"], bool(case.get("translator_mode")))
        offered_names = [t["name"] for t in offered]
        expected = case.get("expect_tool", "")
        if expected:
            if expected in offered_names:
                tool_tp += 1
            else:
                tool_fn += 1
        else:
            tool_fp += int(len(offered_names) > 0)

        if case.get("expect_guardrail"):
            check_text = (parsed or {}).get("answer", out).lower()
            guardrail_pass += int("upload" in check_text or "이미지" in check_text)
        else:
            guardrail_pass += 1

        if case.get("expect_llm_delta_before_final"):
            stream_order_pass += int(llm_delta_before_final(mock_stream_events(case)))
        else:
            stream_order_pass += 1

        rows.append(
            {
                "id": case["id"],
                "mode": args.mode,
                "latency_ms": round(latency_ms, 2),
                "format_valid": bool(parsed is not None),
                "offered_tools": offered_names,
                "expected_tool": expected,
                "guardrail_expected": bool(case.get("expect_guardrail")),
                "llm_delta_order_ok": not case.get("expect_llm_delta_before_final")
                or llm_delta_before_final(mock_stream_events(case)),
            }
        )

    total = len(cases) or 1
    tool_precision = tool_tp / max(1, (tool_tp + tool_fp))
    tool_recall = tool_tp / max(1, (tool_tp + tool_fn))
    summary = {
        "mode": args.mode,
        "suite": args.suite,
        "cases": len(cases),
        "format_valid_rate": round(format_ok / total, 4),
        "tool_precision": round(tool_precision, 4),
        "tool_recall": round(tool_recall, 4),
        "guardrail_pass_rate": round(guardrail_pass / total, 4),
        "llm_delta_order_pass_rate": round(stream_order_pass / total, 4),
        "avg_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
    }
    output = {"summary": summary, "cases": rows}
    out_path = ROOT / "evals" / "results.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Evaluation Summary")
    print("==================")
    for k, v in summary.items():
        print(f"{k}: {v}")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
