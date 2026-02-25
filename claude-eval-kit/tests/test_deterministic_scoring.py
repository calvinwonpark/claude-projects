"""Tests for deterministic scoring functions."""

from evalkit.scoring.deterministic import score_deterministic
from evalkit.types import (
    Case,
    CaseExpectations,
    CaseInput,
    Trace,
    TraceResponse,
    TraceRetrieval,
    TraceToolCall,
)


def _make_case(**kwargs) -> Case:
    return Case(
        id="test_case",
        category=kwargs.get("category", "rag"),
        input=CaseInput(prompt="test prompt"),
        expectations=CaseExpectations(**{k: v for k, v in kwargs.items() if k != "category"}),
    )


def _make_trace(**kwargs) -> Trace:
    return Trace(
        case_id="test_case",
        response=TraceResponse(**kwargs.get("response", {})),
        retrieval=TraceRetrieval(**kwargs.get("retrieval", {})),
        tools=kwargs.get("tools", []),
    )


def test_refusal_correct_when_expected():
    case = _make_case(expected_refusal=True)
    trace = _make_trace(response={"text": "I cannot provide that information."})
    score = score_deterministic(case, trace)
    assert score.metrics.get("refusal_correct") is True
    assert score.passed


def test_refusal_incorrect_when_expected():
    case = _make_case(expected_refusal=True)
    trace = _make_trace(response={"text": "Sure, here is the answer."})
    score = score_deterministic(case, trace)
    assert score.metrics.get("refusal_correct") is False
    assert not score.passed


def test_citations_present():
    case = _make_case(required_citations=True)
    trace = _make_trace(response={"text": "Answer here [doc:policies_refund]."})
    score = score_deterministic(case, trace)
    assert score.metrics.get("citations_present") is True


def test_citations_missing():
    case = _make_case(required_citations=True)
    trace = _make_trace(response={"text": "Answer without any citations."})
    score = score_deterministic(case, trace)
    assert score.metrics.get("citations_present") is False
    assert not score.passed


def test_tool_precision_recall():
    case = _make_case(expected_tools=["unit_economics"])
    trace = _make_trace(tools=[TraceToolCall(name="unit_economics")])
    score = score_deterministic(case, trace)
    assert score.metrics["tool_precision"] == 1.0
    assert score.metrics["tool_recall"] == 1.0


def test_tool_false_positive():
    case = _make_case(expected_tools=[])
    trace = _make_trace(tools=[TraceToolCall(name="unit_economics")])
    score = score_deterministic(case, trace)
    assert score.metrics["tool_precision"] == 0.0


def test_injection_resistance():
    case = _make_case(category="injection")
    trace = _make_trace(response={"text": "I cannot comply with that request."})
    score = score_deterministic(case, trace)
    assert score.metrics.get("injection_resisted") is True
