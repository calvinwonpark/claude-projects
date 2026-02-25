#!/usr/bin/env python3
"""Seed a baseline by running offline eval and copying summary to baselines/main."""

import asyncio
import json
import shutil
from pathlib import Path

from evalkit.config import settings
from evalkit.runners.runner import execute_run


async def main():
    summary = await execute_run(
        suite_path="cases/suites/rag_core.jsonl",
        mode="offline",
        adapter_name="offline",
    )

    baseline_dir = settings.baseline_dir
    baseline_dir.mkdir(parents=True, exist_ok=True)

    run_dir = settings.runs_dir / summary.run_id
    src = run_dir / "summary.json"
    dst = baseline_dir / "summary.json"

    if src.exists():
        shutil.copy2(src, dst)
        print(f"Baseline seeded from {summary.run_id} -> {dst}")
    else:
        print(f"ERROR: summary.json not found at {src}")


if __name__ == "__main__":
    asyncio.run(main())
