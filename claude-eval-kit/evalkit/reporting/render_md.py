"""Render a human-readable markdown report from run artifacts."""

from __future__ import annotations

from typing import Any


def render_report(summary: dict[str, Any], results: list[dict[str, Any]]) -> str:
    """Generate a markdown report from summary.json and results.jsonl entries."""
    lines = [
        "# Evaluation Report",
        "",
        f"**Run ID:** `{summary.get('run_id', 'unknown')}`",
        f"**Suite:** `{summary.get('suite', '')}`",
        f"**Mode:** `{summary.get('mode', 'offline')}`",
        f"**Timestamp:** {summary.get('timestamp', '')}",
        "",
        f"**Total:** {summary.get('total_cases', 0)} | "
        f"**Passed:** {summary.get('passed', 0)} | "
        f"**Failed:** {summary.get('failed', 0)}",
        "",
    ]

    # Metric aggregates table
    agg = summary.get("metric_aggregates", {})
    if agg:
        lines.append("## Metrics")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        for k, v in sorted(agg.items()):
            if k.startswith("_"):
                continue
            display = f"{v:.4f}" if isinstance(v, float) else str(v)
            lines.append(f"| {k} | {display} |")
        lines.append("")

    # Top failures
    failures = [r for r in results if r.get("score", {}).get("passed") is False]
    if failures:
        lines.append("## Top Failures")
        lines.append("")
        for f in failures[:10]:
            score = f.get("score", {})
            case_id = score.get("case_id", "unknown")
            reasons = score.get("reasons", [])
            lines.append(f"- **{case_id}**: {'; '.join(reasons) or 'no reason'}")
        lines.append("")

    return "\n".join(lines)
