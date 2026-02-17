import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable

from anthropic import AsyncAnthropic

try:
    from config import settings
except ImportError:  # pragma: no cover - package import fallback
    from app.config import settings


@dataclass
class ClaudeResponse:
    text: str
    content: list[dict[str, Any]]
    model: str
    request_id: str | None
    input_tokens: int
    output_tokens: int


class AnthropicClient:
    def __init__(self, api_key: str) -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._primary_model = settings.anthropic_model_primary
        self._fallback_model = settings.anthropic_model_fallback

    async def create(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        model: str | None = None,
    ) -> ClaudeResponse:
        request = {
            "model": model or self._primary_model,
            "system": system,
            "messages": messages,
            "tools": tools or [],
            "max_tokens": max_tokens or settings.llm_max_tokens,
            "temperature": settings.llm_temperature if temperature is None else temperature,
        }
        try:
            resp = await asyncio.wait_for(
                self._client.messages.create(**request),
                timeout=max(1.0, settings.llm_request_timeout_ms / 1000.0),
            )
        except Exception:
            if request["model"] == self._fallback_model:
                raise
            request["model"] = self._fallback_model
            resp = await asyncio.wait_for(
                self._client.messages.create(**request),
                timeout=max(1.0, settings.llm_request_timeout_ms / 1000.0),
            )

        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        usage = getattr(resp, "usage", None)
        return ClaudeResponse(
            text=text,
            content=[block.model_dump() for block in resp.content],
            model=getattr(resp, "model", request["model"]),
            request_id=getattr(resp, "id", None),
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        )

    async def stream_text(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        on_delta: Callable[[str], Awaitable[None]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> ClaudeResponse:
        # Used for realtime experiences where partial deltas are desirable.
        full_text = ""
        request_id = None
        model = self._primary_model
        input_tokens = 0
        output_tokens = 0
        async with self._client.messages.stream(
            model=self._primary_model,
            system=system,
            messages=messages,
            max_tokens=max_tokens or settings.llm_max_tokens,
            temperature=settings.llm_temperature if temperature is None else temperature,
        ) as stream:
            async for delta in self.stream_message(stream):
                full_text += delta
                if on_delta:
                    await on_delta(delta)
            final = await stream.get_final_message()
            usage = getattr(final, "usage", None)
            input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
            content = [block.model_dump() for block in getattr(final, "content", [])]
            request_id = getattr(final, "id", None)
            model = getattr(final, "model", model)
        return ClaudeResponse(
            text=full_text,
            content=content,
            model=model,
            request_id=request_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def stream_message(self, stream) -> AsyncIterator[str]:
        """Yield real text deltas from Anthropic streaming events."""
        async for event in stream:
            if getattr(event, "type", "") != "content_block_delta":
                continue
            delta = getattr(getattr(event, "delta", None), "text", "") or ""
            if delta:
                yield delta
