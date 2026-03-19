"""Adapter that calls an application HTTP endpoint for evaluation."""

from __future__ import annotations

import time
from datetime import datetime

import httpx

from evalkit.adapters.base import BaseAdapter
from evalkit.config import settings
from evalkit.types import (
    Case,
    Trace,
    TraceLatency,
    TraceRequest,
    TraceResponse,
    TraceRetrieval,
    TraceToolCall,
    TraceUsage,
)


class HttpAppAdapter(BaseAdapter):
    name = "http_app"

    def __init__(self, endpoint: str | None = None) -> None:
        self.endpoint = endpoint or settings.http_endpoint

    async def run_case(self, case: Case, run_id: str = "") -> Trace:
        # Founder-copilot request contract
        payload = {
            "message": case.input.prompt,
            "session_id": f"eval-{case.id}",
        }

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=settings.timeout_s) as client:
                resp = await client.post(self.endpoint, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            return Trace(
                case_id=case.id,
                run_id=run_id,
                adapter=self.name,
                timestamp=datetime.utcnow(),
                request=TraceRequest(prompt=case.input.prompt),
                response=TraceResponse(text=f"[ERROR] {exc}"),
                latency=TraceLatency(total_ms=elapsed_ms),
            )

        elapsed_ms = (time.perf_counter() - started) * 1000.0

        # Parse retrieval info from founder-copilot response
        retrieval = TraceRetrieval(
            query=case.input.prompt,
            candidates=[],
            selected=[],
            k=0,
            gold_doc_ids=case.expectations.gold_doc_ids or [],
        )

        # If citations exist, use them as selected docs
        citations = data.get("citations", [])
        if isinstance(citations, list):
            retrieval.selected = citations

        # Parse tools from founder-copilot response
        tools: list[TraceToolCall] = []

        # Preferred source: tool_results
        for tc in data.get("tool_results", []):
            tools.append(
                TraceToolCall(
                    name=tc.get("name", ""),
                    args={},  # founder-copilot response doesn't expose args clearly
                    result=tc.get("output"),
                    error=tc.get("error"),
                )
            )

        # Fallback: routing_trace.tool_calls_made
        if not tools:
            routing_trace = data.get("routing_trace", {}) or {}
            for tool_name in routing_trace.get("tool_calls_made", []):
                tools.append(
                    TraceToolCall(
                        name=tool_name,
                        args={},
                        result=None,
                        error=None,
                    )
                )

        # Parse latency/tokens from routing_trace if present
        routing_trace = data.get("routing_trace", {}) or {}
        latency_breakdown = routing_trace.get("latency_ms_breakdown", {}) or {}
        total_latency = elapsed_ms

        agent_usage = routing_trace.get("agent_usage", []) or []
        tokens_in = 0
        tokens_out = 0
        for usage in agent_usage:
            tokens_in += usage.get("tokens_in", 0) or 0
            tokens_out += usage.get("tokens_out", 0) or 0

        # Refusal heuristic from verification/answer if explicit flag absent
        refusal_flag = data.get("refusal_flag")
        if refusal_flag is None:
            answer_text = data.get("answer", "")
            lowered = answer_text.lower()
            refusal_flag = any(
                phrase in lowered
                for phrase in [
                    "i cannot",
                    "i can't",
                    "unable to",
                    "not able to",
                    "insufficient information",
                    "i must decline",
                ]
            )

        return Trace(
            case_id=case.id,
            run_id=run_id,
            adapter=self.name,
            timestamp=datetime.utcnow(),
            request=TraceRequest(
                prompt=case.input.prompt,
                model="founder-copilot-http",
            ),
            retrieval=retrieval,
            tools=tools,
            response=TraceResponse(
                text=data.get("answer", data.get("text", data.get("response", ""))),
                structured=data.get("structured"),
                refusal_flag=refusal_flag,
            ),
            usage=TraceUsage(
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            ),
            latency=TraceLatency(
                total_ms=total_latency,
                breakdown=latency_breakdown,
            ),
        )
