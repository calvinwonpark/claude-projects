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
        payload = {
            "case_id": case.id,
            "prompt": case.input.prompt,
            "language": case.input.language,
            "metadata": case.input.metadata,
            "attachments": case.input.attachments,
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

        # Parse optional trace fields from response
        retrieval = TraceRetrieval()
        if "retrieval" in data and isinstance(data["retrieval"], dict):
            r = data["retrieval"]
            retrieval = TraceRetrieval(
                query=r.get("query", ""),
                candidates=r.get("candidates", []),
                selected=r.get("selected", []),
                k=r.get("k", 0),
                gold_doc_ids=case.expectations.gold_doc_ids or [],
            )

        tools: list[TraceToolCall] = []
        for tc in data.get("tools", []):
            tools.append(TraceToolCall(
                name=tc.get("name", ""),
                args=tc.get("args", {}),
                result=tc.get("result"),
                error=tc.get("error"),
            ))

        return Trace(
            case_id=case.id,
            run_id=run_id,
            adapter=self.name,
            timestamp=datetime.utcnow(),
            request=TraceRequest(
                prompt=case.input.prompt,
                model=data.get("model", ""),
            ),
            retrieval=retrieval,
            tools=tools,
            response=TraceResponse(
                text=data.get("text", data.get("response", "")),
                structured=data.get("structured"),
                refusal_flag=data.get("refusal_flag"),
            ),
            usage=TraceUsage(
                tokens_in=data.get("tokens_in", 0),
                tokens_out=data.get("tokens_out", 0),
            ),
            latency=TraceLatency(total_ms=elapsed_ms),
        )
