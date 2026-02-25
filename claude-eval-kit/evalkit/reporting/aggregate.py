"""Aggregate scores into a RunSummary."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from evalkit.types import RunSummary, Score, Trace


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    idx = int(len(sorted_v) * pct / 100.0)
    idx = min(idx, len(sorted_v) - 1)
    return sorted_v[idx]


def aggregate_results(
    run_id: str,
    suite: str,
    mode: str,
    scores: list[Score],
    traces: list[Trace],
) -> RunSummary:
    """Compute summary metrics from a list of scores and traces."""
    total = len(scores)
    passed = sum(1 for s in scores if s.passed)
    failed = total - passed

    # Collect numeric metrics across all scores
    all_metrics: dict[str, list[float]] = {}
    for s in scores:
        for k, v in s.metrics.items():
            if k.startswith("_"):
                continue
            if isinstance(v, (int, float, bool)):
                all_metrics.setdefault(k, []).append(float(v))

    # Compute averages
    aggregates: dict[str, Any] = {}
    aggregates["pass_rate"] = passed / total if total else 0.0
    for k, vals in all_metrics.items():
        aggregates[f"avg_{k}"] = sum(vals) / len(vals) if vals else 0.0

    # Latency
    latencies = [t.latency.total_ms for t in traces if t.latency.total_ms > 0]
    if latencies:
        aggregates["latency_p50_ms"] = _percentile(latencies, 50)
        aggregates["latency_p95_ms"] = _percentile(latencies, 95)

    # Token usage
    total_in = sum(t.usage.tokens_in for t in traces)
    total_out = sum(t.usage.tokens_out for t in traces)
    if total_in or total_out:
        aggregates["total_tokens_in"] = total_in
        aggregates["total_tokens_out"] = total_out

    return RunSummary(
        run_id=run_id,
        suite=suite,
        mode=mode,
        total_cases=total,
        passed=passed,
        failed=failed,
        metric_aggregates=aggregates,
        timestamp=datetime.utcnow(),
    )
