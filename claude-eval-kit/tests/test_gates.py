"""Tests for acceptance gate loading and evaluation."""

from evalkit.reporting.gates import all_gates_passed, evaluate_gates, load_gates


def test_load_gates():
    gates = load_gates("pilot/acceptance_gates.yaml")
    assert "overall_pass_rate" in gates
    assert gates["overall_pass_rate"]["op"] == ">="
    assert gates["overall_pass_rate"]["value"] == 0.92


def test_load_offline_gates():
    gates = load_gates("pilot/acceptance_gates_offline.yaml")
    assert "overall_pass_rate" in gates
    assert "refusal_correctness_rate" in gates


def test_evaluate_all_pass():
    gates = {
        "pass_rate_gate": {"op": ">=", "value": 0.90, "metric": "pass_rate"},
        "latency_gate": {"op": "<=", "value": 3000, "metric": "latency_p95_ms"},
    }
    summary = {
        "metric_aggregates": {
            "pass_rate": 0.95,
            "latency_p95_ms": 2000,
        }
    }
    results = evaluate_gates(gates, summary)
    assert len(results) == 2
    assert all(r["passed"] for r in results)
    assert all_gates_passed(results)


def test_evaluate_with_failure():
    gates = {
        "pass_rate_gate": {"op": ">=", "value": 0.90, "metric": "pass_rate"},
    }
    summary = {
        "metric_aggregates": {
            "pass_rate": 0.80,
        }
    }
    results = evaluate_gates(gates, summary)
    assert not results[0]["passed"]
    assert not all_gates_passed(results)


def test_evaluate_missing_metric():
    gates = {
        "missing_gate": {"op": ">=", "value": 0.50, "metric": "nonexistent_metric"},
    }
    summary = {"metric_aggregates": {}}
    results = evaluate_gates(gates, summary)
    assert not results[0]["passed"]
    assert "not found" in results[0]["reason"]
