"""Generate app-specific eval cases using Claude.

Usage:
    python -m evalkit.generators.generate_cases \
        --app-spec cases/apps/founder_copilot/app_spec.yaml \
        --category tool \
        --count 20 \
        --out cases/apps/founder_copilot/generated/tool_use.jsonl
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from evalkit.generators.models import (
    AppSpec,
    GeneratedCase,
    GenerationSummary,
    ValidationIssue,
)
from evalkit.generators.prompt_builder import build_prompt, build_system_prompt
from evalkit.generators.validators import validate_batch

app = typer.Typer(
    name="generate-cases",
    help="Generate app-specific eval cases using Claude.",
)
console = Console()


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------


def _call_claude(
    prompt: str,
    system: str,
    api_key: str,
    model: str = "claude-sonnet-4-5-20250929",
    temperature: float = 0.7,
    max_tokens: int = 8192,
) -> str:
    """Synchronous call to Claude Messages API."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(
        block.text for block in response.content if hasattr(block, "text")
    )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _extract_json_array(text: str) -> list[dict]:
    """Extract a JSON array from LLM output, handling markdown fences."""
    cleaned = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
    start = cleaned.find("[")
    if start < 0:
        raise ValueError("No JSON array found in LLM response")

    depth = 0
    end = -1
    for i in range(start, len(cleaned)):
        if cleaned[i] == "[":
            depth += 1
        elif cleaned[i] == "]":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end <= start:
        raise ValueError("Unbalanced JSON array in LLM response")

    return json.loads(cleaned[start : end + 1])


def _parse_cases(raw_dicts: list[dict]) -> list[GeneratedCase]:
    """Parse raw dicts from LLM output into GeneratedCase objects."""
    cases: list[GeneratedCase] = []
    for d in raw_dicts:
        try:
            case = GeneratedCase(
                id=d.get("id", ""),
                category=d.get("category", ""),
                input=d.get("input", {}),
                expectations=d.get("expectations", {}),
                tags=d.get("tags", []),
                notes=d.get("notes"),
            )
            cases.append(case)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not parse case: {e}[/]")
            console.print(f"  Raw: {json.dumps(d, indent=2)[:200]}")
    return cases


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def _load_existing_ids(path: Path) -> set[str]:
    """Load case IDs from an existing JSONL file."""
    ids: set[str] = set()
    if path.exists():
        for line in path.read_text().strip().splitlines():
            if line.strip():
                try:
                    ids.add(json.loads(line)["id"])
                except (json.JSONDecodeError, KeyError):
                    pass
    return ids


def _write_jsonl(
    cases: list[GeneratedCase],
    path: Path,
    overwrite: bool = False,
) -> None:
    """Write cases to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if overwrite else "a"
    with open(path, mode) as f:
        for case in cases:
            f.write(json.dumps(case.to_jsonl_dict(), ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Core generation flow
# ---------------------------------------------------------------------------


def generate(
    app_spec_path: str | Path,
    category: str,
    count: int = 10,
    out: Optional[str | Path] = None,
    model: str = "claude-sonnet-4-5-20250929",
    temperature: float = 0.7,
    seed: Optional[int] = None,
    dry_run: bool = False,
    print_prompt: bool = False,
    overwrite: bool = False,
    api_key: Optional[str] = None,
) -> GenerationSummary:
    """Main generation pipeline: build prompt → call LLM → validate → write."""

    spec = AppSpec.from_yaml(app_spec_path)

    if category not in spec.supported_categories:
        console.print(
            f"[red]Category '{category}' not in supported categories: "
            f"{spec.supported_categories}[/]"
        )
        raise typer.Exit(code=1)

    prompt = build_prompt(spec, category, count=count, seed=seed)
    system = build_system_prompt()

    if print_prompt or dry_run:
        console.print("\n[bold cyan]== System Prompt ==[/]")
        console.print(system)
        console.print("\n[bold cyan]== User Prompt ==[/]")
        console.print(prompt)

    if dry_run:
        console.print("\n[dim]Dry run — no API call made.[/]")
        return GenerationSummary(app_name=spec.app_name, category=category)

    resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not resolved_key:
        console.print("[red]ANTHROPIC_API_KEY not set. Use --dry-run to preview prompts.[/]")
        raise typer.Exit(code=1)

    console.print(
        f"[dim]Generating {count} '{category}' cases for {spec.app_name} "
        f"with {model}...[/]"
    )

    raw_text = _call_claude(
        prompt=prompt,
        system=system,
        api_key=resolved_key,
        model=model,
        temperature=temperature,
    )

    try:
        raw_dicts = _extract_json_array(raw_text)
    except ValueError as e:
        console.print(f"[red]Failed to parse LLM response: {e}[/]")
        console.print(f"[dim]Raw response (first 500 chars):[/]")
        console.print(raw_text[:500])
        return GenerationSummary(
            app_name=spec.app_name,
            category=category,
            issues=[
                ValidationIssue(
                    case_id="<parse>",
                    field="response",
                    message=str(e),
                )
            ],
        )

    parsed_cases = _parse_cases(raw_dicts)
    console.print(f"[dim]Parsed {len(parsed_cases)} cases from LLM response.[/]")

    out_path = Path(out) if out else None
    existing_ids = _load_existing_ids(out_path) if out_path and not overwrite else set()

    valid, invalid, all_issues = validate_batch(
        parsed_cases, spec, existing_ids=existing_ids
    )

    duplicate_count = sum(
        1 for i in all_issues if "Duplicate ID" in i.message
    )

    summary = GenerationSummary(
        app_name=spec.app_name,
        category=category,
        generated_count=len(parsed_cases),
        valid_count=len(valid),
        invalid_count=len(invalid),
        duplicate_count=duplicate_count,
        issues=all_issues,
    )

    if invalid:
        console.print(f"\n[yellow]Invalid cases ({len(invalid)}):[/]")
        for case in invalid:
            case_issues = [i for i in all_issues if i.case_id == case.id and i.severity == "error"]
            for issue in case_issues:
                console.print(f"  [{issue.severity}] {issue.case_id}.{issue.field}: {issue.message}")

    if valid and out_path:
        _write_jsonl(valid, out_path, overwrite=overwrite)
        summary.written_path = str(out_path)
        console.print(f"\n[green]Wrote {len(valid)} cases to {out_path}[/]")
    elif valid and not out_path:
        console.print("\n[bold]Generated cases (no --out specified):[/]")
        for case in valid:
            console.print(json.dumps(case.to_jsonl_dict(), indent=2, ensure_ascii=False))

    _print_summary_table(summary)
    return summary


def _print_summary_table(summary: GenerationSummary) -> None:
    table = Table(title=f"Generation: {summary.app_name} / {summary.category}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Generated", str(summary.generated_count))
    table.add_row("Valid", f"[green]{summary.valid_count}[/]")
    table.add_row("Invalid", f"[red]{summary.invalid_count}[/]" if summary.invalid_count else "0")
    table.add_row("Duplicates", str(summary.duplicate_count))
    if summary.written_path:
        table.add_row("Written to", summary.written_path)
    console.print(table)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@app.command()
def main(
    app_spec: str = typer.Option(
        ..., "--app-spec", help="Path to app spec YAML file"
    ),
    category: str = typer.Option(
        ..., "--category", help="Category to generate (routing, tool, rag, safety, quality)"
    ),
    count: int = typer.Option(10, "--count", help="Number of cases to generate"),
    out: Optional[str] = typer.Option(
        None, "--out", help="Output JSONL file path"
    ),
    model: str = typer.Option(
        "claude-sonnet-4-5-20250929", "--model", help="Claude model to use"
    ),
    temperature: float = typer.Option(
        0.7, "--temperature", help="Sampling temperature"
    ),
    seed: Optional[int] = typer.Option(
        None, "--seed", help="Seed for prompt variation"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print prompt without calling API"
    ),
    print_prompt: bool = typer.Option(
        False, "--print-prompt", help="Print the constructed prompt"
    ),
    overwrite: bool = typer.Option(
        False, "--overwrite", help="Overwrite output file instead of appending"
    ),
) -> None:
    """Generate app-specific eval cases using Claude."""
    generate(
        app_spec_path=app_spec,
        category=category,
        count=count,
        out=out,
        model=model,
        temperature=temperature,
        seed=seed,
        dry_run=dry_run,
        print_prompt=print_prompt,
        overwrite=overwrite,
    )


if __name__ == "__main__":
    app()
