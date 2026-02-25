"""Adapter that calls Claude directly via Anthropic Messages API."""

from __future__ import annotations

import time
from datetime import datetime

from evalkit.adapters.base import BaseAdapter
from evalkit.config import settings
from evalkit.types import (
    Case,
    Trace,
    TraceLatency,
    TraceRequest,
    TraceResponse,
    TraceUsage,
)


class AnthropicMessagesAdapter(BaseAdapter):
    name = "anthropic_messages"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or settings.target_model
        self.api_key = api_key or settings.anthropic_api_key

    async def run_case(self, case: Case, run_id: str = "") -> Trace:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self.api_key)
        system = case.input.system or "You are a helpful assistant."
        messages = [{"role": "user", "content": case.input.prompt}]

        started = time.perf_counter()
        try:
            response = await client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system,
                messages=messages,
            )
            elapsed_ms = (time.perf_counter() - started) * 1000.0

            text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text

            return Trace(
                case_id=case.id,
                run_id=run_id,
                adapter=self.name,
                timestamp=datetime.utcnow(),
                request=TraceRequest(
                    prompt=case.input.prompt,
                    system=system,
                    model=response.model,
                ),
                response=TraceResponse(text=text),
                usage=TraceUsage(
                    tokens_in=getattr(response.usage, "input_tokens", 0),
                    tokens_out=getattr(response.usage, "output_tokens", 0),
                ),
                latency=TraceLatency(total_ms=elapsed_ms),
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            return Trace(
                case_id=case.id,
                run_id=run_id,
                adapter=self.name,
                timestamp=datetime.utcnow(),
                request=TraceRequest(prompt=case.input.prompt, system=system, model=self.model),
                response=TraceResponse(text=f"[ERROR] {exc}"),
                latency=TraceLatency(total_ms=elapsed_ms),
            )
