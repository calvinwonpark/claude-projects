import asyncio
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator

from anthropic import Anthropic, AsyncAnthropic

logger = logging.getLogger(__name__)


@dataclass
class ClaudeResponse:
    text: str
    model: str
    input_tokens: int | None
    output_tokens: int | None


class ClaudeClient:
    """Wrapper around Anthropic Messages API with deterministic model fallback."""

    def __init__(
        self,
        api_key: str,
        primary_model: str,
        fallback_model: str,
        extra_models: list[str] | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 900,
        request_timeout_ms: int = 15000,
    ) -> None:
        self._api_key = api_key
        self._client = AsyncAnthropic(api_key=api_key)
        self._sync_client = Anthropic(api_key=api_key)
        ordered = [primary_model, fallback_model] + (extra_models or [])
        # Keep deterministic order while deduplicating.
        self._configured_models = list(dict.fromkeys([m.strip() for m in ordered if m and m.strip()]))
        self._models = list(self._configured_models)
        self._available_models: list[str] = []
        self._selected_primary = self._models[0] if self._models else ""
        self._selected_fallback = self._models[1] if len(self._models) > 1 else self._selected_primary
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._request_timeout_s = max(request_timeout_ms / 1000.0, 1.0)

    @staticmethod
    def _request_id_from_exception(exc: Exception) -> str | None:
        request_id = getattr(exc, "request_id", None)
        if request_id:
            return str(request_id)
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            return body.get("request_id")
        return None

    @staticmethod
    def _pick_best_available(available: list[str]) -> str:
        priority = ["claude-3-5-sonnet-latest", "claude-3-5-haiku-latest"]
        for preferred in priority:
            if preferred in available:
                return preferred
        return available[0] if available else ""

    def warmup_model_selection(self) -> dict[str, Any]:
        """Load available models once and select robust primary/fallback model IDs."""
        try:
            models_page = self._sync_client.models.list(limit=200)
            ids = [m.id for m in models_page.data if getattr(m, "id", None)]
            self._available_models = sorted(set(ids))
        except Exception as exc:
            request_id = self._request_id_from_exception(exc)
            logger.warning("Unable to list Anthropic models. request_id=%s error=%s", request_id, exc)
            self._available_models = []
            self._models = list(self._configured_models)
            self._selected_primary = self._models[0] if self._models else ""
            self._selected_fallback = self._models[1] if len(self._models) > 1 else self._selected_primary
            return self.get_model_status()

        available_set = set(self._available_models)
        selected = [m for m in self._configured_models if m in available_set]
        if not selected:
            best = self._pick_best_available(self._available_models)
            selected = [best] if best else []
        if len(selected) == 1:
            next_best = next((m for m in self._available_models if m != selected[0]), selected[0] if selected else "")
            if next_best:
                selected.append(next_best)
        self._models = [m for m in selected if m]
        self._selected_primary = self._models[0] if self._models else ""
        self._selected_fallback = self._models[1] if len(self._models) > 1 else self._selected_primary
        return self.get_model_status()

    def get_model_status(self) -> dict[str, Any]:
        return {
            "configured_models": self._configured_models,
            "selected_primary": self._selected_primary,
            "selected_fallback": self._selected_fallback,
            "active_fallback_chain": self._models,
            "available_models": self._available_models,
        }

    async def create(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
    ) -> ClaudeResponse:
        last_error: Exception | None = None
        for model in self._models:
            try:
                async with asyncio.timeout(self._request_timeout_s):
                    response = await self._client.messages.create(
                        model=model,
                        max_tokens=self._max_output_tokens,
                        temperature=self._temperature,
                        system=system,
                        messages=messages,
                    )
                text = "".join(
                    block.text for block in response.content if getattr(block, "type", "") == "text"
                )
                usage = getattr(response, "usage", None)
                return ClaudeResponse(
                    text=text.strip(),
                    model=model,
                    input_tokens=getattr(usage, "input_tokens", None),
                    output_tokens=getattr(usage, "output_tokens", None),
                )
            except Exception as exc:
                request_id = self._request_id_from_exception(exc)
                logger.warning("Claude model %s failed: request_id=%s error=%s", model, request_id, exc)
                last_error = exc
                await asyncio.sleep(0.1)
        raise RuntimeError(
            f"All Claude models failed ({self._models}). Last error: {last_error}. "
            "Set CLAUDE_PRIMARY_MODEL and CLAUDE_FALLBACK_MODEL to model IDs available in your Anthropic account."
        )

    async def stream(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
    ) -> AsyncIterator[dict[str, Any]]:
        last_error: Exception | None = None
        for model in self._models:
            try:
                async with asyncio.timeout(self._request_timeout_s):
                    async with self._client.messages.stream(
                        model=model,
                        max_tokens=self._max_output_tokens,
                        temperature=self._temperature,
                        system=system,
                        messages=messages,
                    ) as stream:
                        full_text = ""
                        async for token in stream.text_stream:
                            full_text += token
                            yield {"type": "token", "token": token, "model": model}
                        final_message = await stream.get_final_message()
                        usage = getattr(final_message, "usage", None)
                        yield {
                            "type": "done",
                            "text": full_text.strip(),
                            "model": model,
                            "input_tokens": getattr(usage, "input_tokens", None),
                            "output_tokens": getattr(usage, "output_tokens", None),
                        }
                        return
            except Exception as exc:
                request_id = self._request_id_from_exception(exc)
                logger.warning("Claude stream model %s failed: request_id=%s error=%s", model, request_id, exc)
                last_error = exc
                await asyncio.sleep(0.1)
                continue
        raise RuntimeError(
            f"All Claude models failed during stream ({self._models}). Last error: {last_error}. "
            "Set CLAUDE_PRIMARY_MODEL and CLAUDE_FALLBACK_MODEL to model IDs available in your Anthropic account."
        )
