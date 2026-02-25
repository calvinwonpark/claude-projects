"""Tests that offline mode does not invoke judge scoring."""

from evalkit.scoring.registry import score_case
from evalkit.types import (
    Case,
    CaseExpectations,
    CaseInput,
    Trace,
    TraceResponse,
)


def _make_case() -> Case:
    return Case(
        id="mode_test",
        category="rag",
        input=CaseInput(prompt="test"),
        expectations=CaseExpectations(required_citations=True),
    )


def _make_trace() -> Trace:
    return Trace(
        case_id="mode_test",
        response=TraceResponse(text="Here is the answer [doc:ref1]."),
    )


def test_offline_mode_no_pending_rubrics():
    """In offline mode, score should NOT include _pending_rubrics."""
    score = score_case(_make_case(), _make_trace(), mode="offline")
    assert "_pending_rubrics" not in score.metrics


def test_online_mode_has_pending_rubrics():
    """In online mode, score should include _pending_rubrics for judge dispatch."""
    score = score_case(_make_case(), _make_trace(), mode="online")
    assert "_pending_rubrics" in score.metrics
    assert isinstance(score.metrics["_pending_rubrics"], list)
