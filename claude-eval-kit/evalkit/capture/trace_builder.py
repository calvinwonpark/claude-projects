"""Helpers for constructing Trace objects from partial data."""

from __future__ import annotations

from datetime import datetime

from evalkit.types import (
    Case,
    Trace,
    TraceLatency,
    TraceRequest,
    TraceResponse,
    TraceRetrieval,
)


def build_offline_trace(case: Case, run_id: str = "") -> Trace:
    """Build a minimal Trace for offline evaluation (no API call)."""
    return Trace(
        case_id=case.id,
        run_id=run_id,
        adapter="offline",
        timestamp=datetime.utcnow(),
        request=TraceRequest(
            prompt=case.input.prompt,
            system=case.input.system or "",
            model="offline",
        ),
        retrieval=TraceRetrieval(
            gold_doc_ids=case.expectations.gold_doc_ids or [],
        ),
        response=TraceResponse(text="[offline — no model output]"),
        latency=TraceLatency(total_ms=0.0),
    )
