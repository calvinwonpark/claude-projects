#!/usr/bin/env python3
"""Compare two run directories and print diff summary."""

import json
import sys
from pathlib import Path

from evalkit.reporting.diff import compute_diff, render_diff_md


def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/compare_runs.py <baseline_dir> <run_dir>")
        sys.exit(1)

    baseline_dir = Path(sys.argv[1])
    run_dir = Path(sys.argv[2])

    base_summary = json.loads((baseline_dir / "summary.json").read_text())
    run_summary = json.loads((run_dir / "summary.json").read_text())

    diff = compute_diff(base_summary, run_summary)
    print(render_diff_md(diff))

    if diff["regression"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
