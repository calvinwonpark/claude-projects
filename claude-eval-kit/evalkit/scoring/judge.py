"""LLM-as-judge scoring using Claude with YAML rubrics."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from evalkit.config import settings
from evalkit.logging import get_logger
from evalkit.types import Case, Score, Trace

logger = get_logger(__name__)

RUBRICS_DIR = Path(__file__).parent / "rubrics"


def _load_rubric(name: str) -> dict[str, Any]:
    path = RUBRICS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Rubric not found: {path}")
    with open(path, "r") as f:
        return yaml.safe_load(f)


def _build_judge_prompt(rubric: dict, case: Case, trace: Trace) -> str:
    criteria = rubric.get("criteria", "Evaluate the response.")
    scale = rubric.get("scale", "0-5")
    return (
        f"You are an evaluation judge. Score the following response.\n\n"
        f"## Criteria\n{criteria}\n\n"
        f"## Scale\n{scale}\n\n"
        f"## User Prompt\n{case.input.prompt}\n\n"
        f"## Model Response\n{trace.response.text}\n\n"
        f"## Retrieved Context IDs\n{', '.join(trace.retrieval.selected) or 'none'}\n\n"
        f"## Instructions\n"
        f"Return ONLY a JSON object: {{\"score\": <int 0-5>, \"pass\": <bool>, \"reasons\": [<str>, ...]}}\n"
    )


def _parse_judge_output(text: str) -> dict[str, Any]:
    """Extract JSON from judge response, handling markdown fences."""
    cleaned = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
    start = cleaned.find("{")
    if start < 0:
        return {"score": 0, "pass": False, "reasons": ["Judge output not parseable"]}
    depth = 0
    end = -1
    for i in range(start, len(cleaned)):
        if cleaned[i] == "{":
            depth += 1
        elif cleaned[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end <= start:
        return {"score": 0, "pass": False, "reasons": ["Judge output not parseable"]}
    try:
        return json.loads(cleaned[start : end + 1])
    except Exception:
        return {"score": 0, "pass": False, "reasons": ["Judge JSON parse failed"]}


async def score_with_judge(case: Case, trace: Trace, rubric_name: str) -> dict[str, Any]:
    """Call Claude as judge using a named rubric. Returns {score, pass, reasons}."""
    import anthropic

    rubric = _load_rubric(rubric_name)
    prompt = _build_judge_prompt(rubric, case, trace)

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    for attempt in range(2):
        try:
            response = await client.messages.create(
                model=settings.judge_model,
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in response.content if hasattr(b, "text"))
            result = _parse_judge_output(text)
            if "score" in result:
                return result
        except Exception as exc:
            logger.warning(f"Judge attempt {attempt + 1} failed: {exc}")

    return {"score": 0, "pass": False, "reasons": ["Judge scoring failed after retries"]}
