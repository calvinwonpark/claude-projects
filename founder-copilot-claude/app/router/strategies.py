import time
from dataclasses import dataclass
from typing import Any


@dataclass
class AgentCandidate:
    label: str
    confidence: float


def _now_ms() -> float:
    return time.time() * 1000


def winner_take_all(candidates: list[AgentCandidate]) -> dict[str, Any]:
    started = _now_ms()
    ranked = sorted(candidates, key=lambda c: c.confidence, reverse=True)
    chosen = ranked[0]
    return {
        "selected_agent": chosen.label,
        "candidates_considered": [{"label": c.label, "confidence": c.confidence} for c in ranked],
        "rationale": "Highest confidence candidate selected.",
        "latency_ms": round(_now_ms() - started, 2),
    }


def consult_then_decide(candidates: list[AgentCandidate]) -> dict[str, Any]:
    started = _now_ms()
    ranked = sorted(candidates, key=lambda c: c.confidence, reverse=True)
    primary = ranked[0]
    reviewer = ranked[1] if len(ranked) > 1 else ranked[0]
    return {
        "selected_agent": primary.label,
        "candidates_considered": [{"label": c.label, "confidence": c.confidence} for c in ranked],
        "rationale": f"Primary {primary.label} selected with reviewer {reviewer.label} critique.",
        "reviewer_agent": reviewer.label,
        "latency_ms": round(_now_ms() - started, 2),
    }


def ensemble_vote(candidates: list[AgentCandidate]) -> dict[str, Any]:
    started = _now_ms()
    ranked = sorted(candidates, key=lambda c: c.confidence, reverse=True)
    top = ranked[0]
    return {
        "selected_agent": top.label,
        "candidates_considered": [{"label": c.label, "confidence": c.confidence} for c in ranked],
        "rationale": "Ensemble vote collapsed to highest weighted candidate.",
        "latency_ms": round(_now_ms() - started, 2),
    }
