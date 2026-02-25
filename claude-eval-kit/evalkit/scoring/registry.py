"""Scorer registry: selects and combines scorers based on case category and mode."""

from __future__ import annotations

from evalkit.scoring.deterministic import score_deterministic
from evalkit.types import Case, Score, Trace


# Rubric assignments by category (used in online mode only)
_CATEGORY_RUBRICS: dict[str, list[str]] = {
    "rag": ["groundedness", "helpfulness"],
    "tool": ["tool_use", "helpfulness"],
    "refusal": ["refusal", "helpfulness"],
    "injection": ["refusal"],
    "routing": ["helpfulness"],
    "streaming": ["helpfulness"],
    "structured": ["helpfulness"],
    "general": ["helpfulness"],
}


def score_case(case: Case, trace: Trace, mode: str = "offline") -> Score:
    """Score a single case using deterministic checks and optionally judge rubrics.

    In offline mode, only deterministic checks are applied.
    In online mode, judge scoring would be appended (async caller responsibility).
    """
    score = score_deterministic(case, trace)

    # In offline mode, deterministic scoring is complete.
    # Online mode judge integration is handled at the runner level
    # to keep this function synchronous for simplicity.
    if mode == "offline":
        return score

    # Mark which rubrics would apply (caller can invoke judge.score_with_judge)
    rubrics = _CATEGORY_RUBRICS.get(case.category, ["helpfulness"])
    score.metrics["_pending_rubrics"] = rubrics

    return score
