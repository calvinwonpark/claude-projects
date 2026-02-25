"""Tests for pilot report generation."""

from evalkit.reporting.pilot_report import generate_pilot_report


def test_pilot_report_pass():
    summary = {
        "run_id": "test_run",
        "suite": "pilot_core",
        "mode": "offline",
        "timestamp": "2026-02-17T00:00:00",
    }
    gate_results = [
        {"name": "pass_rate", "metric": "pass_rate", "op": ">=", "threshold": 0.92, "actual": 0.95, "passed": True, "reason": ""},
        {"name": "latency", "metric": "latency_p95_ms", "op": "<=", "threshold": 2500, "actual": 1800, "passed": True, "reason": ""},
    ]
    report = generate_pilot_report(summary, gate_results)
    assert "PASS" in report
    assert "test_run" in report
    assert "pass_rate" in report
    assert "rollout plan" in report.lower()


def test_pilot_report_fail_with_recommendations():
    summary = {
        "run_id": "test_run_fail",
        "suite": "pilot_core",
        "mode": "online",
        "timestamp": "2026-02-17T00:00:00",
    }
    gate_results = [
        {"name": "pass_rate", "metric": "pass_rate", "op": ">=", "threshold": 0.92, "actual": 0.80, "passed": False, "reason": "0.8 does not satisfy >= 0.92"},
        {"name": "citation_coverage_rate", "metric": "avg_citations_present", "op": ">=", "threshold": 0.90, "actual": 0.70, "passed": False, "reason": "0.7 does not satisfy >= 0.9"},
    ]
    report = generate_pilot_report(summary, gate_results)
    assert "FAIL" in report
    assert "Recommendations" in report
    assert "citation" in report.lower()


def test_pilot_report_with_case_failures():
    summary = {"run_id": "r1", "suite": "s", "mode": "offline"}
    gate_results = [
        {"name": "g1", "metric": "m1", "op": ">=", "threshold": 0.5, "actual": 0.3, "passed": False, "reason": "low"},
    ]
    case_results = [
        {"score": {"case_id": "c1", "passed": False, "reasons": ["Missing citations"]}},
        {"score": {"case_id": "c2", "passed": True, "reasons": []}},
    ]
    report = generate_pilot_report(summary, gate_results, case_results)
    assert "c1" in report
    assert "Missing citations" in report
