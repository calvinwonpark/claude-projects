"""Diff a run against a baseline with regression thresholds."""

from __future__ import annotations

from typing import Any

# Default regression thresholds
_THRESHOLDS = {
    "pass_rate": -0.02,          # fail if drops > 2%
    "avg_refusal_correct": -0.05,
    "avg_citations_present": -0.05,
    "avg_tool_precision": -0.05,
    "avg_tool_recall": -0.05,
    "latency_p95_ms": 500,       # fail if increases > 500ms
}


def compute_diff(
    baseline: dict[str, Any],
    current: dict[str, Any],
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Compare current run summary against baseline.

    Returns a dict with deltas and a regression flag.
    """
    t = thresholds or _THRESHOLDS
    base_agg = baseline.get("metric_aggregates", {})
    curr_agg = current.get("metric_aggregates", {})

    deltas: dict[str, dict[str, Any]] = {}
    regression = False

    all_keys = set(base_agg.keys()) | set(curr_agg.keys())
    for key in sorted(all_keys):
        if key.startswith("_") or key.startswith("total_"):
            continue
        base_val = base_agg.get(key)
        curr_val = curr_agg.get(key)
        if base_val is None or curr_val is None:
            continue
        if not isinstance(base_val, (int, float)) or not isinstance(curr_val, (int, float)):
            continue

        delta = curr_val - base_val
        entry: dict[str, Any] = {
            "baseline": round(base_val, 4),
            "current": round(curr_val, 4),
            "delta": round(delta, 4),
            "regressed": False,
        }

        if key in t:
            threshold = t[key]
            if "latency" in key:
                # For latency, regression = increase beyond threshold
                if delta > threshold:
                    entry["regressed"] = True
                    regression = True
            else:
                # For quality metrics, regression = decrease beyond threshold
                if delta < threshold:
                    entry["regressed"] = True
                    regression = True

        deltas[key] = entry

    return {
        "baseline_run": baseline.get("run_id", "unknown"),
        "current_run": current.get("run_id", "unknown"),
        "deltas": deltas,
        "regression": regression,
    }


def render_diff_md(diff_result: dict[str, Any]) -> str:
    """Render diff result as markdown."""
    lines = [
        "# Regression Diff",
        "",
        f"Baseline: `{diff_result['baseline_run']}`",
        f"Current:  `{diff_result['current_run']}`",
        "",
    ]

    if diff_result["regression"]:
        lines.append("**STATUS: REGRESSION DETECTED**")
    else:
        lines.append("**STATUS: No regressions**")
    lines.append("")

    lines.append("| Metric | Baseline | Current | Delta | Regressed |")
    lines.append("|--------|----------|---------|-------|-----------|")

    for key, entry in diff_result.get("deltas", {}).items():
        flag = "YES" if entry["regressed"] else ""
        lines.append(
            f"| {key} | {entry['baseline']} | {entry['current']} | {entry['delta']:+.4f} | {flag} |"
        )

    lines.append("")
    return "\n".join(lines)
