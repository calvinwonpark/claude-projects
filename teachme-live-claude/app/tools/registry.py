import asyncio
import re
import ast
import operator
from typing import Any

from pydantic import BaseModel, Field, ValidationError
try:
    from sympy import SympifyError, sympify
except ImportError:  # pragma: no cover - optional dependency fallback
    SympifyError = Exception
    sympify = None


class MathSolverArgs(BaseModel):
    expression: str = Field(min_length=1, max_length=200)


class GrammarCheckArgs(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    target_language: str = Field(default="en")


def has_math_intent(text: str) -> bool:
    q = (text or "").lower()
    return bool(
        re.search(r"\d+\s*[\+\-\*/\^]\s*\d+", q)
        or any(k in q for k in ["solve", "equation", "calculate", "math", "분수", "계산"])
    )


def has_grammar_intent(text: str) -> bool:
    q = (text or "").lower()
    keys = [
        "grammar",
        "correct this",
        "proofread",
        "fix my sentence",
        "fix this sentence",
        "correct my sentence",
        "문법",
        "교정",
        "고쳐줘",
        "문장 교정",
    ]
    return any(k in q for k in keys)


def has_translation_rewrite_intent(text: str) -> bool:
    q = (text or "").lower()
    keys = [
        "translate",
        "rewrite",
        "more natural",
        "자연스럽게",
        "영어로 바꿔",
        "한국어로 바꿔",
        "바꿔줘",
    ]
    return any(k in q for k in keys)


def available_tools_for_query(query: str, translator_mode: bool) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    if has_math_intent(query):
        tools.append(
            {
                "name": "math_solver",
                "description": "Safely solves a math expression and returns concise steps.",
                "input_schema": MathSolverArgs.model_json_schema(),
            }
        )
    # Keep high precision but recover recall in translator scenarios for rewrite intent.
    if has_grammar_intent(query) or (translator_mode and has_translation_rewrite_intent(query)):
        tools.append(
            {
                "name": "grammar_check",
                "description": "Checks grammar and returns corrections with mistake explanations.",
                "input_schema": GrammarCheckArgs.model_json_schema(),
            }
        )
    return tools


def _solve_math(args: MathSolverArgs) -> dict[str, Any]:
    normalized = args.expression.replace("^", "**")
    if sympify is not None:
        try:
            expr = sympify(normalized, evaluate=True)
            result = str(expr)
        except (SympifyError, TypeError) as exc:
            raise ValueError(f"Unable to parse expression safely: {exc}") from exc
    else:
        allowed = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.Pow: operator.pow,
            ast.USub: operator.neg,
        }

        def _eval(node):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            if isinstance(node, ast.BinOp) and type(node.op) in allowed:
                return allowed[type(node.op)](_eval(node.left), _eval(node.right))
            if isinstance(node, ast.UnaryOp) and type(node.op) in allowed:
                return allowed[type(node.op)](_eval(node.operand))
            raise ValueError("Unsupported expression")

        try:
            parsed = ast.parse(normalized, mode="eval")
            result = str(_eval(parsed.body))
        except Exception as exc:
            raise ValueError(f"Unable to parse expression safely: {exc}") from exc
    steps = [
        f"Normalize expression: {args.expression}",
        f"Compute with symbolic parser: {normalized}",
        f"Result: {result}",
    ]
    return {"result": result, "steps": steps}


def _grammar_check(args: GrammarCheckArgs) -> dict[str, Any]:
    text = args.text.strip()
    corrected = text
    explanations: list[str] = []
    mistakes: list[dict[str, str]] = []

    # Very lightweight deterministic checks for demo reliability.
    if re.search(r"\bi am agree\b", corrected, re.I):
        corrected = re.sub(r"\bi am agree\b", "I agree", corrected, flags=re.I)
        explanations.append('Use "I agree" instead of "I am agree".')
        mistakes.append({"type": "phrase", "original": "I am agree", "fix": "I agree"})
    if re.search(r"\bdoesn'?t has\b", corrected, re.I):
        corrected = re.sub(r"\bdoesn'?t has\b", "doesn't have", corrected, flags=re.I)
        explanations.append('After "does not", use base form "have".')
        mistakes.append({"type": "verb_form", "original": "doesn't has", "fix": "doesn't have"})
    if corrected and corrected[0].islower():
        corrected = corrected[0].upper() + corrected[1:]
        explanations.append("Capitalize the first letter.")
        mistakes.append({"type": "capitalization", "original": text[:1], "fix": corrected[:1]})
    if corrected and corrected[-1] not in ".!?":
        corrected = corrected + "."
        explanations.append("End the sentence with punctuation.")
        mistakes.append({"type": "punctuation", "original": "(none)", "fix": "."})

    return {
        "corrected_text": corrected,
        "explanations": explanations or ["No major grammar issues detected with deterministic checks."],
        "mistakes": mistakes,
        "target_language": args.target_language,
    }


def execute_tool(name: str, raw_args: dict[str, Any]) -> dict[str, Any]:
    if name == "math_solver":
        try:
            args = MathSolverArgs.model_validate(raw_args)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        return _solve_math(args)
    if name == "grammar_check":
        try:
            args = GrammarCheckArgs.model_validate(raw_args)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        return _grammar_check(args)
    raise ValueError(f"Tool not allowed: {name}")


async def execute_tool_with_timeout(name: str, raw_args: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
    return await asyncio.wait_for(asyncio.to_thread(execute_tool, name, raw_args), timeout=max(0.1, timeout_ms / 1000.0))
