"""Generate a stakeholder-ready pilot report from run artifacts and gate results."""

from __future__ import annotations

from typing import Any


def generate_pilot_report(
    summary: dict[str, Any],
    gate_results: list[dict[str, Any]],
    results: list[dict[str, Any]] | None = None,
) -> str:
    """Produce a concise markdown pilot report."""
    lines: list[str] = []
    all_passed = all(g["passed"] for g in gate_results)
    passed_count = sum(1 for g in gate_results if g["passed"])
    total_gates = len(gate_results)

    # 1) Executive Summary
    lines.append("# Pilot Evaluation Report")
    lines.append("")
    lines.append(f"**Run ID:** `{summary.get('run_id', 'unknown')}`")
    lines.append(f"**Suite:** `{summary.get('suite', '')}`")
    lines.append(f"**Mode:** `{summary.get('mode', 'offline')}`")
    lines.append(f"**Timestamp:** {summary.get('timestamp', '')}")
    lines.append("")

    if all_passed:
        lines.append(f"**Result: PASS** ({passed_count}/{total_gates} gates met)")
    else:
        lines.append(f"**Result: FAIL** ({passed_count}/{total_gates} gates met)")
    lines.append("")

    # 2) KPI Table
    lines.append("## Acceptance Gates")
    lines.append("")
    lines.append("| Gate | Metric | Target | Actual | Status |")
    lines.append("|------|--------|--------|--------|--------|")
    for g in gate_results:
        actual_str = f"{g['actual']:.4f}" if g["actual"] is not None else "N/A"
        status = "PASS" if g["passed"] else "FAIL"
        lines.append(
            f"| {g['name']} | {g['metric']} | {g['op']} {g['threshold']} | {actual_str} | {status} |"
        )
    lines.append("")

    # 3) Top Failure Modes
    failures: list[dict[str, Any]] = []
    if results:
        for r in results:
            score = r.get("score", {})
            if score.get("passed") is False:
                failures.append(score)

    if failures:
        lines.append("## Top Failure Modes")
        lines.append("")
        for f in failures[:10]:
            case_id = f.get("case_id", "unknown")
            reasons = f.get("reasons", [])
            lines.append(f"- **{case_id}**: {'; '.join(reasons) or 'unspecified'}")
        lines.append("")

    # 4) Recommendations
    failed_gates = [g for g in gate_results if not g["passed"]]
    if failed_gates:
        lines.append("## Recommendations")
        lines.append("")
        for g in failed_gates[:5]:
            name = g["name"]
            reason = g["reason"]
            if "not found" in reason:
                lines.append(f"- **{name}**: metric not available in this run mode. Run in online mode or add cases that produce this metric.")
            elif "citation" in name.lower():
                lines.append(f"- **{name}**: improve retrieval quality or prompt engineering to increase citation coverage. Verify corpus completeness.")
            elif "refusal" in name.lower():
                lines.append(f"- **{name}**: review refusal prompt design and add refusal-specific test cases. Check system prompt safety instructions.")
            elif "injection" in name.lower():
                lines.append(f"- **{name}**: strengthen system prompt guardrails against retrieved-document injection. Add adversarial cases to dataset.")
            elif "latency" in name.lower():
                lines.append(f"- **{name}**: tune timeout budgets, cache strategy, or model tier. Check retrieval and tool stage latency breakdown.")
            elif "cost" in name.lower():
                lines.append(f"- **{name}**: reduce token usage via shorter prompts, caching, or model fallback strategy.")
            else:
                lines.append(f"- **{name}**: {reason}")
        lines.append("")

    # 5) Next Steps
    lines.append("## Next Steps")
    lines.append("")
    if all_passed:
        lines.append("- [ ] Confirm go decision with stakeholders")
        lines.append("- [ ] Document rollout plan and monitoring thresholds")
        lines.append("- [ ] Set up production alerting for gate metrics")
        lines.append("- [ ] Archive pilot run as production baseline")
        lines.append("- [ ] Schedule post-launch review at 2 weeks")
    else:
        lines.append("- [ ] Address top failure modes identified above")
        lines.append("- [ ] Add edge cases for failing categories to pilot datasets")
        lines.append("- [ ] Re-run pilot suites after fixes")
        lines.append("- [ ] Schedule follow-up review with stakeholders")
        lines.append("- [ ] Consider extending pilot by 1 week if trends improve")
    lines.append("")

    return "\n".join(lines)
