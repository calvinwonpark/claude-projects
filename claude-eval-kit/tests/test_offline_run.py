"""End-to-end offline run test on a small suite."""

import asyncio
import json
from pathlib import Path

from evalkit.runners.runner import execute_run


def test_offline_run_rag_core():
    summary = asyncio.run(
        execute_run(
            suite_path="cases/suites/rag_core.jsonl",
            mode="offline",
            adapter_name="offline",
            max_cases=5,
        )
    )
    assert summary.total_cases == 5
    assert summary.passed + summary.failed == 5
    assert summary.run_id

    # Check artifacts were written
    run_dir = Path("runs") / summary.run_id
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "results.jsonl").exists()
    assert (run_dir / "summary.json").exists()

    # Verify summary.json is valid
    data = json.loads((run_dir / "summary.json").read_text())
    assert data["run_id"] == summary.run_id
    assert "metric_aggregates" in data
