"""Core data models for evaluation cases, traces, scores, and run summaries."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Case (input specification)
# ---------------------------------------------------------------------------

class CaseInput(BaseModel):
    prompt: str
    language: str = "en"
    system: Optional[str] = None
    attachments: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseExpectations(BaseModel):
    expected_refusal: Optional[bool] = None
    expected_tools: Optional[list[str]] = None
    required_citations: Optional[bool] = None
    gold_doc_ids: Optional[list[str]] = None
    output_schema: Optional[dict[str, Any]] = None
    latency_budget_ms: Optional[float] = None
    notes: Optional[str] = None


class Case(BaseModel):
    id: str
    suite: str = ""
    category: str  # rag | tool | refusal | routing | streaming | structured | injection
    input: CaseInput
    expectations: CaseExpectations = Field(default_factory=CaseExpectations)


# ---------------------------------------------------------------------------
# Trace (execution record)
# ---------------------------------------------------------------------------

class TraceRetrieval(BaseModel):
    query: str = ""
    candidates: list[str] = Field(default_factory=list)
    selected: list[str] = Field(default_factory=list)
    k: int = 0
    gold_doc_ids: list[str] = Field(default_factory=list)


class TraceToolCall(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    error: Optional[str] = None


class TraceRequest(BaseModel):
    prompt: str = ""
    system: str = ""
    model: str = ""
    params: dict[str, Any] = Field(default_factory=dict)


class TraceResponse(BaseModel):
    text: str = ""
    structured: Optional[dict[str, Any]] = None
    refusal_flag: Optional[bool] = None


class TraceUsage(BaseModel):
    tokens_in: int = 0
    tokens_out: int = 0


class TraceLatency(BaseModel):
    total_ms: float = 0.0
    breakdown: dict[str, float] = Field(default_factory=dict)


class TraceSafety(BaseModel):
    flags: list[str] = Field(default_factory=list)
    injection_detected: Optional[bool] = None


class Trace(BaseModel):
    case_id: str
    run_id: str = ""
    adapter: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request: TraceRequest = Field(default_factory=TraceRequest)
    retrieval: TraceRetrieval = Field(default_factory=TraceRetrieval)
    tools: list[TraceToolCall] = Field(default_factory=list)
    response: TraceResponse = Field(default_factory=TraceResponse)
    usage: TraceUsage = Field(default_factory=TraceUsage)
    latency: TraceLatency = Field(default_factory=TraceLatency)
    safety: TraceSafety = Field(default_factory=TraceSafety)


# ---------------------------------------------------------------------------
# Score (per-case evaluation result)
# ---------------------------------------------------------------------------

class Score(BaseModel):
    case_id: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    passed: bool = True
    reasons: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Run Summary
# ---------------------------------------------------------------------------

class RunSummary(BaseModel):
    run_id: str
    suite: str
    mode: str
    total_cases: int = 0
    passed: int = 0
    failed: int = 0
    metric_aggregates: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
