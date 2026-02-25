"""Tests for diff/regression detection."""

from evalkit.reporting.diff import compute_diff


def test_no_regression():
    baseline = {
        "run_id": "base",
        "metric_aggregates": {"pass_rate": 0.90, "latency_p95_ms": 2000},
    }
    current = {
        "run_id": "current",
        "metric_aggregates": {"pass_rate": 0.92, "latency_p95_ms": 1900},
    }
    result = compute_diff(baseline, current)
    assert result["regression"] is False


def test_pass_rate_regression():
    baseline = {
        "run_id": "base",
        "metric_aggregates": {"pass_rate": 0.95},
    }
    current = {
        "run_id": "current",
        "metric_aggregates": {"pass_rate": 0.90},
    }
    result = compute_diff(baseline, current)
    assert result["regression"] is True
    assert result["deltas"]["pass_rate"]["regressed"] is True


def test_latency_regression():
    baseline = {
        "run_id": "base",
        "metric_aggregates": {"latency_p95_ms": 2000},
    }
    current = {
        "run_id": "current",
        "metric_aggregates": {"latency_p95_ms": 3000},
    }
    result = compute_diff(baseline, current)
    assert result["regression"] is True
    assert result["deltas"]["latency_p95_ms"]["regressed"] is True
