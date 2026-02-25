"""CLI entrypoint for evalkit."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from evalkit.config import Settings
from evalkit.logging import setup_logging

app = typer.Typer(name="evalkit", help="Claude Eval Kit — evaluate Claude-powered systems.")
console = Console()


@app.command()
def run(
    suite: str = typer.Option(..., help="Path to JSONL suite file"),
    mode: str = typer.Option(
        "offline",
        help="offline (deterministic scoring only) or online (+ judge scoring)",
    ),
    adapter: str = typer.Option(
        "",
        help=(
            "Adapter for trace execution: http | anthropic | offline_stub. "
            "Defaults to offline_stub (mode=offline) or anthropic (mode=online). "
            "MODE controls scoring, not execution: use --adapter http with mode=offline "
            "to run against your app with deterministic-only scoring."
        ),
    ),
    max_cases: int = typer.Option(0, "--max-cases", help="Limit cases (0 = all)"),
    concurrency: int = typer.Option(4, help="Max concurrent evaluations"),
) -> None:
    """Run an evaluation suite."""
    setup_logging()

    import asyncio

    from evalkit.runners.runner import execute_run, resolve_adapter

    # Resolve adapter early to print its name
    resolved = resolve_adapter(adapter, mode)
    console.print(f"[dim]mode={mode}  adapter={resolved.name}[/]")

    result = asyncio.run(
        execute_run(
            suite_path=suite,
            mode=mode,
            adapter_name=adapter,
            max_cases=max_cases,
            concurrency=concurrency,
        )
    )
    console.print(f"\n[bold green]Run complete:[/] {result.run_id}")
    console.print(f"  passed: {result.passed}/{result.total_cases}")
    console.print(f"  failed: {result.failed}/{result.total_cases}")

    if result.metric_aggregates:
        table = Table(title="Metric Aggregates")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        for k, v in sorted(result.metric_aggregates.items()):
            table.add_row(k, f"{v:.4f}" if isinstance(v, float) else str(v))
        console.print(table)


@app.command()
def report(
    run_path: str = typer.Option(..., "--run", help="Path to run directory"),
    fmt: str = typer.Option("md", "--format", help="md or json"),
) -> None:
    """Generate a report from a completed run."""
    setup_logging()
    from evalkit.reporting.render_md import render_report

    run_dir = Path(run_path)
    if not run_dir.exists():
        console.print(f"[red]Run directory not found:[/] {run_dir}")
        raise typer.Exit(code=1)

    summary_path = run_dir / "summary.json"
    results_path = run_dir / "results.jsonl"

    if not summary_path.exists():
        console.print(f"[red]summary.json not found in {run_dir}[/]")
        raise typer.Exit(code=1)

    summary = json.loads(summary_path.read_text())
    results = []
    if results_path.exists():
        results = [json.loads(ln) for ln in results_path.read_text().strip().splitlines() if ln.strip()]

    report_text = render_report(summary, results)
    report_file = run_dir / "report.md"
    report_file.write_text(report_text)
    console.print(f"[green]Report written to {report_file}[/]")


@app.command()
def diff(
    baseline: str = typer.Option("baselines/main", help="Baseline directory"),
    run_path: str = typer.Option(..., "--run", help="Run directory to compare"),
) -> None:
    """Compare a run against a baseline."""
    setup_logging()
    from evalkit.reporting.diff import compute_diff, render_diff_md

    baseline_dir = Path(baseline)
    run_dir = Path(run_path)

    baseline_summary = baseline_dir / "summary.json"
    run_summary = run_dir / "summary.json"

    if not baseline_summary.exists():
        console.print(f"[yellow]No baseline found at {baseline_summary}. Skipping diff.[/]")
        raise typer.Exit(code=0)

    if not run_summary.exists():
        console.print(f"[red]Run summary not found: {run_summary}[/]")
        raise typer.Exit(code=1)

    base = json.loads(baseline_summary.read_text())
    current = json.loads(run_summary.read_text())

    diff_result = compute_diff(base, current)
    diff_text = render_diff_md(diff_result)

    diff_file = run_dir / "diff.md"
    diff_file.write_text(diff_text)
    console.print(f"[green]Diff written to {diff_file}[/]")

    if diff_result.get("regression"):
        console.print("[bold red]REGRESSION DETECTED[/]")
        raise typer.Exit(code=1)
    else:
        console.print("[bold green]No regressions.[/]")


@app.command()
def gate(
    run_path: str = typer.Option(..., "--run", help="Path to run directory"),
    policy: str = typer.Option("pilot/acceptance_gates.yaml", help="Path to gates YAML"),
) -> None:
    """Evaluate acceptance gates against a completed run."""
    setup_logging()
    from evalkit.reporting.gates import all_gates_passed, evaluate_gates, load_gates

    run_dir = Path(run_path)
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        console.print(f"[red]summary.json not found in {run_dir}[/]")
        raise typer.Exit(code=1)

    summary = json.loads(summary_path.read_text())
    gates = load_gates(policy)
    results = evaluate_gates(gates, summary)

    table = Table(title="Acceptance Gates")
    table.add_column("Gate", style="cyan")
    table.add_column("Metric")
    table.add_column("Threshold", justify="right")
    table.add_column("Actual", justify="right")
    table.add_column("Status", justify="center")

    for g in results:
        actual_str = f"{g['actual']:.4f}" if g["actual"] is not None else "N/A"
        status = "[green]PASS[/]" if g["passed"] else "[red]FAIL[/]"
        table.add_row(g["name"], g["metric"], f"{g['op']} {g['threshold']}", actual_str, status)

    console.print(table)

    if all_gates_passed(results):
        console.print("\n[bold green]All gates passed.[/]")
    else:
        console.print("\n[bold red]Gates failed.[/]")
        console.print("\nTop failures:")
        for g in results:
            if not g["passed"]:
                console.print(f"  - {g['name']}: {g['reason']}")
        raise typer.Exit(code=1)


@app.command("pilot-report")
def pilot_report(
    run_path: str = typer.Option(..., "--run", help="Path to run directory"),
    policy: str = typer.Option("pilot/acceptance_gates.yaml", help="Path to gates YAML"),
    out: str = typer.Option("", help="Output path (default: <run>/pilot_report.md)"),
) -> None:
    """Generate a stakeholder-ready pilot evaluation report."""
    setup_logging()
    from evalkit.reporting.gates import evaluate_gates, load_gates
    from evalkit.reporting.pilot_report import generate_pilot_report

    run_dir = Path(run_path)
    summary_path = run_dir / "summary.json"
    results_path = run_dir / "results.jsonl"

    if not summary_path.exists():
        console.print(f"[red]summary.json not found in {run_dir}[/]")
        raise typer.Exit(code=1)

    summary = json.loads(summary_path.read_text())
    gates = load_gates(policy)
    gate_results = evaluate_gates(gates, summary)

    case_results = []
    if results_path.exists():
        case_results = [json.loads(ln) for ln in results_path.read_text().strip().splitlines() if ln.strip()]

    report_text = generate_pilot_report(summary, gate_results, case_results)

    out_path = Path(out) if out else run_dir / "pilot_report.md"
    out_path.write_text(report_text)
    console.print(f"[green]Pilot report written to {out_path}[/]")


if __name__ == "__main__":
    app()
