"""Stub adapter for framework-only testing. Returns placeholder traces with no real execution."""

from __future__ import annotations

from datetime import datetime, timezone

from evalkit.adapters.base import BaseAdapter
from evalkit.types import (
    Case,
    Trace,
    TraceLatency,
    TraceRequest,
    TraceResponse,
)


class OfflineStubAdapter(BaseAdapter):
    """Returns a minimal placeholder Trace. Use only for framework sanity tests."""

    name = "offline_stub"

    async def run_case(self, case: Case, run_id: str = "") -> Trace:
        return Trace(
            case_id=case.id,
            run_id=run_id,
            adapter=self.name,
            timestamp=datetime.now(timezone.utc),
            request=TraceRequest(
                prompt=case.input.prompt,
                system=case.input.system or "",
                model="offline_stub",
            ),
            response=TraceResponse(text="[offline stub]"),
            latency=TraceLatency(total_ms=0.0),
        )
