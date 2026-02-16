import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Any, AsyncIterator

from anthropic import Anthropic, AsyncAnthropic

logger = logging.getLogger(__name__)


@dataclass
class ClaudeCallResult:
    text: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    request_id: str | None
    tool_calls: list[dict[str, Any]]
    content_blocks: list[dict[str, Any]]


class ClaudeClient:
    def __init__(
        self,
        api_key: str,
        primary_model: str,
        fallback_model: str,
        extra_models: list[str] | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 1000,
        timeout_ms: int = 20000,
    ) -> None:
        self._async = AsyncAnthropic(api_key=api_key)
        self._sync = Anthropic(api_key=api_key)
        self._configured = [primary_model, fallback_model] + (extra_models or [])
        self._configured = [m.strip() for m in self._configured if m and m.strip()]
        self._models = list(dict.fromkeys(self._configured))
        self._available_models: list[str] = []
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._timeout_s = max(1.0, timeout_ms / 1000.0)

    @property
    def selected_models(self) -> list[str]:
        return self._models

    def warmup_model_selection(self) -> dict[str, Any]:
        try:
            page = self._sync.models.list(limit=200)
            self._available_models = sorted({m.id for m in page.data if getattr(m, "id", None)})
        except Exception as exc:
            logger.warning("Could not list Anthropic models: %s", exc)
            self._available_models = []
            return self.model_status()

        available = set(self._available_models)
        chosen = [m for m in self._configured if m in available]
        priority = ["claude-3-5-sonnet-latest", "claude-3-5-haiku-latest"]
        if not chosen:
            for p in priority:
                if p in available:
                    chosen.append(p)
                    break
        if not chosen and self._available_models:
            chosen.append(self._available_models[0])
        self._models = list(dict.fromkeys(chosen))
        return self.model_status()

    def model_status(self) -> dict[str, Any]:
        return {
            "configured_models": self._configured,
            "selected_models": self._models,
            "available_models": self._available_models,
        }

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        msg = str(exc).lower()
        return any(token in msg for token in ["429", "500", "503", "rate limit", "overloaded"])

    @staticmethod
    def _request_id(exc: Exception) -> str | None:
        rid = getattr(exc, "request_id", None)
        if rid:
            return str(rid)
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            return body.get("request_id")
        return None

    async def _call_with_retries(self, call_coro_factory):
        backoff = 0.6
        last_error = None
        for attempt in range(5):
            try:
                async with asyncio.timeout(self._timeout_s):
                    return await call_coro_factory()
            except Exception as exc:
                last_error = exc
                if not self._is_retryable(exc) or attempt == 4:
                    raise
                await asyncio.sleep(backoff + random.uniform(0, 0.35))
                backoff *= 2
        raise RuntimeError(f"Failed after retries: {last_error}")

    async def create(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ClaudeCallResult:
        last_error: Exception | None = None
        for model in self._models:
            try:
                response = await self._call_with_retries(
                    lambda: self._async.messages.create(
                        model=model,
                        system=system,
                        messages=messages,
                        tools=tools or [],
                        temperature=self._temperature,
                        max_tokens=self._max_output_tokens,
                    )
                )
                text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text").strip()
                tool_calls = [
                    {"name": b.name, "input": b.input, "id": b.id}
                    for b in response.content
                    if getattr(b, "type", "") == "tool_use"
                ]
                content_blocks: list[dict[str, Any]] = []
                for b in response.content:
                    btype = getattr(b, "type", "")
                    if btype == "text":
                        content_blocks.append({"type": "text", "text": getattr(b, "text", "")})
                    elif btype == "tool_use":
                        content_blocks.append(
                            {
                                "type": "tool_use",
                                "id": getattr(b, "id", ""),
                                "name": getattr(b, "name", ""),
                                "input": getattr(b, "input", {}),
                            }
                        )
                usage = getattr(response, "usage", None)
                return ClaudeCallResult(
                    text=text,
                    model=model,
                    input_tokens=getattr(usage, "input_tokens", None),
                    output_tokens=getattr(usage, "output_tokens", None),
                    request_id=getattr(response, "id", None),
                    tool_calls=tool_calls,
                    content_blocks=content_blocks,
                )
            except Exception as exc:
                logger.warning("Claude call failed model=%s request_id=%s error=%s", model, self._request_id(exc), exc)
                last_error = exc
                continue
        raise RuntimeError(f"All Claude models failed: {last_error}")

    async def stream(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        cancel_event: asyncio.Event,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        last_error = None
        for model in self._models:
            try:
                async with asyncio.timeout(self._timeout_s):
                    async with self._async.messages.stream(
                        model=model,
                        system=system,
                        messages=messages,
                        tools=tools or [],
                        temperature=self._temperature,
                        max_tokens=self._max_output_tokens,
                    ) as stream:
                        full = ""
                        async for delta in stream.text_stream:
                            if cancel_event.is_set():
                                yield {"type": "cancelled"}
                                return
                            full += delta
                            yield {"type": "token", "delta": delta, "model": model}
                        final = await stream.get_final_message()
                        usage = getattr(final, "usage", None)
                        tool_calls = [
                            {"name": b.name, "input": b.input, "id": b.id}
                            for b in final.content
                            if getattr(b, "type", "") == "tool_use"
                        ]
                        yield {
                            "type": "done",
                            "text": full.strip(),
                            "model": model,
                            "input_tokens": getattr(usage, "input_tokens", None),
                            "output_tokens": getattr(usage, "output_tokens", None),
                            "request_id": getattr(final, "id", None),
                            "tool_calls": tool_calls,
                        }
                        return
            except Exception as exc:
                logger.warning("Claude stream failed model=%s request_id=%s error=%s", model, self._request_id(exc), exc)
                last_error = exc
                continue
        raise RuntimeError(f"All Claude streaming models failed: {last_error}")
