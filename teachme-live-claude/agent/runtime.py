import json
import re
from dataclasses import dataclass
from typing import Any, Callable

try:
    from config import settings
    from tools.registry import available_tools_for_query, execute_tool_with_timeout
except ImportError:  # pragma: no cover - fallback for package imports in tests/evals
    from app.config import settings
    from app.tools.registry import available_tools_for_query, execute_tool_with_timeout


STRUCTURED_KEYS = ["answer", "steps", "examples", "common_mistakes", "next_exercises"]


@dataclass
class AgentRuntimeResult:
    raw_text: str
    structured: dict[str, Any]
    tool_calls: list[dict[str, Any]]
    tool_failures: int
    model: str
    request_id: str | None
    input_tokens: int
    output_tokens: int
    duration_ms: float


def build_structured_system_prompt(target_language: str, translator_mode: bool) -> str:
    lang_name = "Korean (존댓말)" if target_language == "ko" else "English"
    translator = (
        "Translator mode is enabled. If user language differs from target output language, briefly interpret intent first."
        if translator_mode
        else "Translator mode is disabled."
    )
    return (
        f"You are a realtime tutor. Always answer in {lang_name}. "
        f"{translator} "
        "Return ONLY valid JSON with keys: answer, steps, examples, common_mistakes, next_exercises. "
        "Do not include markdown, code fences, backticks, or prose before/after JSON. "
        "Keep answer concise and practical."
    )


def parse_structured_json(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    # Strip common markdown wrappers from model output.
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("{")
    if start < 0:
        return None
    # Extract first balanced JSON object only.
    depth = 0
    end = -1
    for idx in range(start, len(raw)):
        ch = raw[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = idx
                break
    if end <= start:
        return None
    try:
        obj = json.loads(raw[start : end + 1])
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    for key in STRUCTURED_KEYS:
        if key not in obj:
            return None
    if not isinstance(obj.get("answer"), str):
        return None
    for list_key in STRUCTURED_KEYS[1:]:
        if not isinstance(obj.get(list_key), list):
            return None
    return obj


def safe_structured_fallback(target_language: str) -> dict[str, Any]:
    if target_language == "ko":
        return {
            "answer": "질문을 정확히 이해했는지 확인하고 싶어요. 핵심을 한 문장으로 다시 말해주실래요?",
            "steps": ["질문의 핵심 개념을 확인하기", "주어진 조건 정리하기", "한 단계씩 풀이하기"],
            "examples": ["예: 2x+3=11 이면 2x=8, x=4"],
            "common_mistakes": ["조건을 빠뜨림", "계산 부호 실수"],
            "next_exercises": ["비슷한 문제 2개를 풀어보기", "풀이 과정을 소리 내어 설명하기"],
        }
    return {
        "answer": "I want to make sure I understood your question. Could you restate it in one short sentence?",
        "steps": ["Identify the core concept", "List given constraints", "Solve one step at a time"],
        "examples": ["Example: if 2x+3=11, then 2x=8, x=4"],
        "common_mistakes": ["Skipping constraints", "Sign errors in arithmetic"],
        "next_exercises": ["Solve 2 similar problems", "Explain your steps out loud"],
    }


def coerce_structured_from_text(text: str, target_language: str) -> dict[str, Any]:
    """
    Deterministically coerce arbitrary model text into the required response schema.
    This guarantees format compliance even when the model emits malformed JSON.
    """
    base = safe_structured_fallback(target_language)
    raw = (text or "").strip()
    if not raw:
        return base

    parsed = parse_structured_json(raw)
    if parsed:
        return parsed

    # Remove code fences and keep compact plain text.
    cleaned = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).replace("```", "").strip()
    lines = [ln.strip(" -\t") for ln in cleaned.splitlines() if ln.strip()]
    answer = lines[0] if lines else cleaned[:280]
    if not answer:
        return base

    # Heuristic bullet extraction for step-like content.
    bullets = [ln for ln in lines[1:] if len(ln) > 3]
    steps = bullets[:3] if bullets else base["steps"]
    examples = [b for b in bullets if any(ch.isdigit() for ch in b)][:3] or base["examples"]
    mistakes = [b for b in bullets if any(k in b.lower() for k in ["mistake", "error", "wrong", "실수"])]
    next_ex = [b for b in bullets if any(k in b.lower() for k in ["next", "practice", "exercise", "연습", "다음"])]

    return {
        "answer": answer,
        "steps": steps if isinstance(steps, list) and steps else base["steps"],
        "examples": examples if isinstance(examples, list) and examples else base["examples"],
        "common_mistakes": mistakes if mistakes else base["common_mistakes"],
        "next_exercises": next_ex if next_ex else base["next_exercises"],
    }


def is_image_required_query(query: str) -> bool:
    q = (query or "").lower()
    return any(k in q for k in ["this image", "in the image", "picture", "사진", "이미지", "첨부된"])


def is_math_like_query(query: str) -> bool:
    q = query or ""
    return bool(re.search(r"\d+\s*[\+\-\*/\^]\s*\d+", q))


async def _call_with_tools(
    claude,
    *,
    system: str,
    messages: list[dict[str, Any]],
    query: str,
    translator_mode: bool,
) -> AgentRuntimeResult:
    import time

    started = time.perf_counter()
    tool_calls: list[dict[str, Any]] = []
    tool_failures = 0
    total_in = 0
    total_out = 0
    model = settings.anthropic_model_primary
    request_id = None
    tools = available_tools_for_query(query, translator_mode)
    loop_messages = list(messages)
    final_text = ""

    for _ in range(max(1, settings.tool_max_iters)):
        response = await claude.create(system=system, messages=loop_messages, tools=tools)
        total_in += response.input_tokens
        total_out += response.output_tokens
        model = response.model
        request_id = response.request_id
        final_text = response.text

        tool_uses = [c for c in response.content if c.get("type") == "tool_use"]
        if not tool_uses:
            break

        loop_messages.append({"role": "assistant", "content": response.content})
        tool_result_blocks: list[dict[str, Any]] = []
        for tc in tool_uses:
            name = tc.get("name", "")
            args = tc.get("input") or {}
            tool_use_id = tc.get("id", "")
            tool_calls.append({"name": name, "args": args})
            try:
                output = await execute_tool_with_timeout(name, args, settings.tool_timeout_ms)
                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps(output, ensure_ascii=False),
                    }
                )
            except Exception as exc:
                tool_failures += 1
                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps({"error": str(exc)}, ensure_ascii=False),
                    }
                )
        loop_messages.append({"role": "user", "content": tool_result_blocks})

    structured = parse_structured_json(final_text) or {}
    return AgentRuntimeResult(
        raw_text=final_text,
        structured=structured,
        tool_calls=tool_calls,
        tool_failures=tool_failures,
        model=model,
        request_id=request_id,
        input_tokens=total_in,
        output_tokens=total_out,
        duration_ms=(time.perf_counter() - started) * 1000.0,
    )


async def _call_streaming_no_tools(
    claude,
    *,
    system: str,
    messages: list[dict[str, Any]],
    on_token: Callable[[str], Any] | None = None,
) -> AgentRuntimeResult:
    import time

    started = time.perf_counter()
    response = await claude.stream_text(
        system=system,
        messages=messages,
        on_delta=on_token,
        max_tokens=settings.llm_max_tokens,
        temperature=settings.llm_temperature,
    )
    structured = parse_structured_json(response.text) or {}
    return AgentRuntimeResult(
        raw_text=response.text,
        structured=structured,
        tool_calls=[],
        tool_failures=0,
        model=response.model,
        request_id=response.request_id,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        duration_ms=(time.perf_counter() - started) * 1000.0,
    )


async def run_tutor_turn(
    *,
    claude,
    conversation_messages: list[dict[str, Any]],
    query: str,
    target_language: str,
    translator_mode: bool,
    on_token: Callable[[str], Any] | None = None,
) -> AgentRuntimeResult:
    system = build_structured_system_prompt(target_language, translator_mode)
    offered_tools = available_tools_for_query(query, translator_mode)
    if offered_tools:
        result = await _call_with_tools(
            claude,
            system=system,
            messages=conversation_messages,
            query=query,
            translator_mode=translator_mode,
        )
    else:
        result = await _call_streaming_no_tools(
            claude,
            system=system,
            messages=conversation_messages,
            on_token=on_token,
        )
    if parse_structured_json(result.raw_text):
        result.structured = parse_structured_json(result.raw_text) or {}
        return result

    if settings.strict_structured_mode:
        for _ in range(2):
            repair_messages = list(conversation_messages) + [
                {"role": "assistant", "content": [{"type": "text", "text": result.raw_text}]},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Output MUST be a valid minified JSON object only. "
                                "Repair the previous answer. Return ONLY strict JSON with keys "
                                "answer, steps, examples, common_mistakes, next_exercises. "
                                "No markdown and no code fences."
                            ),
                        }
                    ],
                },
            ]
            repair_resp = await claude.create(
                system=system,
                messages=repair_messages,
                tools=[],
                max_tokens=min(300, settings.llm_max_tokens),
                temperature=0.0,
            )
            parsed = parse_structured_json(repair_resp.text)
            if parsed:
                result.raw_text = repair_resp.text
                result.structured = parsed
                result.model = repair_resp.model
                result.request_id = repair_resp.request_id
                result.input_tokens += repair_resp.input_tokens
                result.output_tokens += repair_resp.output_tokens
                return result

    result.structured = coerce_structured_from_text(result.raw_text, target_language)
    result.raw_text = json.dumps(result.structured, ensure_ascii=False)
    return result
