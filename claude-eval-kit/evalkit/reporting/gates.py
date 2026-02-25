"""Acceptance gate evaluation: load policy YAML, evaluate against run summary."""

from __future__ import annotations

import operator
from pathlib import Path
from typing import Any

import yaml


_OPS = {
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
    "==": operator.eq,
}


def load_gates(policy_path: str | Path) -> dict[str, dict[str, Any]]:
    """Load gate definitions from a YAML file.

    Returns: {gate_name: {op, value, metric, description}}
    """
    with open(policy_path, "r") as f:
        raw = yaml.safe_load(f)

    gates = raw.get("pilot", {})
    if not gates:
        raise ValueError(f"No 'pilot' key found in {policy_path}")
    return gates


def evaluate_gates(
    gates: dict[str, dict[str, Any]],
    summary: dict[str, Any],
) -> list[dict[str, Any]]:
    """Evaluate each gate against summary metrics.

    Returns a list of gate results:
    [{name, metric, op, threshold, actual, passed, reason}]
    """
    aggregates = summary.get("metric_aggregates", {})
    results: list[dict[str, Any]] = []

    for gate_name, gate_def in gates.items():
        op_str = gate_def.get("op", ">=")
        threshold = gate_def.get("value")
        metric_key = gate_def.get("metric", gate_name)
        description = gate_def.get("description", "")

        op_fn = _OPS.get(op_str)
        if op_fn is None:
            results.append({
                "name": gate_name,
                "metric": metric_key,
                "op": op_str,
                "threshold": threshold,
                "actual": None,
                "passed": False,
                "reason": f"Unsupported operator: {op_str}",
            })
            continue

        actual = aggregates.get(metric_key)
        if actual is None:
            results.append({
                "name": gate_name,
                "metric": metric_key,
                "op": op_str,
                "threshold": threshold,
                "actual": None,
                "passed": False,
                "reason": f"Metric '{metric_key}' not found in summary",
            })
            continue

        passed = op_fn(float(actual), float(threshold))
        reason = "" if passed else f"{actual} does not satisfy {op_str} {threshold}"

        results.append({
            "name": gate_name,
            "metric": metric_key,
            "op": op_str,
            "threshold": threshold,
            "actual": round(float(actual), 4),
            "passed": passed,
            "reason": reason,
        })

    return results


def all_gates_passed(results: list[dict[str, Any]]) -> bool:
    return all(r["passed"] for r in results)
