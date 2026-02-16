import asyncio
import json
from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.providers.claude_client import ClaudeClient
from app.tools import execute_tool


@dataclass
class AgentTurnResult:
    final_text: str
    tool_calls: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    model: str | None
    usage_in: int
    usage_out: int
    request_id: str | None
    status_events: list[dict[str, Any]]


async def _execute_tool_with_timeout(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    timeout_s = max(0.1, settings.tools.timeout_ms / 1000.0)
    return await asyncio.wait_for(asyncio.to_thread(execute_tool, name, tool_input), timeout=timeout_s)


async def run_agent_turn(
    *,
    claude: ClaudeClient,
    system_prompt: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    cancel_event: asyncio.Event,
) -> AgentTurnResult:
    loop_messages: list[dict[str, Any]] = list(messages)
    tool_calls_all: list[dict[str, Any]] = []
    tool_results_all: list[dict[str, Any]] = []
    status_events: list[dict[str, Any]] = []

    model: str | None = None
    request_id: str | None = None
    usage_in = 0
    usage_out = 0
    final_text = ""

    max_iters = max(1, settings.tools.max_iters)
    for iter_idx in range(max_iters):
        if cancel_event.is_set():
            break

        result = await claude.create(system=system_prompt, messages=loop_messages, tools=tools)
        model = result.model
        request_id = result.request_id
        usage_in += int(result.input_tokens or 0)
        usage_out += int(result.output_tokens or 0)
        final_text = result.text

        if not result.tool_calls:
            break

        status_events.append(
            {
                "type": "status",
                "message": f"Running tool step {iter_idx + 1}/{max_iters}...",
            }
        )
        loop_messages.append({"role": "assistant", "content": result.content_blocks})

        tool_result_blocks = []
        for tc in result.tool_calls:
            name = str(tc.get("name") or "")
            tool_input = tc.get("input") or {}
            tool_use_id = str(tc.get("id") or "")
            call_rec = {"name": name, "input": tool_input, "id": tool_use_id}
            tool_calls_all.append(call_rec)

            try:
                output = await _execute_tool_with_timeout(name, tool_input)
                tool_rec = {"name": name, "tool_use_id": tool_use_id, "output": output}
                tool_results_all.append(tool_rec)
                status_events.append({"type": "tool_result", "tool": name, "output": output})
                content = json.dumps(output, ensure_ascii=False)
            except Exception as exc:
                err = {"error": str(exc)}
                tool_rec = {"name": name, "tool_use_id": tool_use_id, "error": str(exc)}
                tool_results_all.append(tool_rec)
                status_events.append({"type": "tool_error", "tool": name, "error": str(exc)})
                content = json.dumps(err, ensure_ascii=False)

            tool_result_blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": content,
                }
            )

        loop_messages.append({"role": "user", "content": tool_result_blocks})

    return AgentTurnResult(
        final_text=final_text,
        tool_calls=tool_calls_all,
        tool_results=tool_results_all,
        model=model,
        usage_in=usage_in,
        usage_out=usage_out,
        request_id=request_id,
        status_events=status_events,
    )
