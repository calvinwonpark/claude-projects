"""Core evaluation runner: loads suites, executes cases, writes artifacts."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from evalkit.adapters.base import BaseAdapter
from evalkit.config import settings
from evalkit.logging import get_logger
from evalkit.reporting.aggregate import aggregate_results
from evalkit.scoring.registry import score_case
from evalkit.types import Case, CaseExpectations, CaseInput, RunSummary, Score, Trace

logger = get_logger(__name__)


def load_suite(path: str) -> list[Case]:
    """Load a JSONL suite file into Case objects."""
    cases: list[Case] = []
    suite_name = Path(path).stem
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)

            # Normalize: support flat JSONL or nested input/expectations
            if "input" in raw and isinstance(raw["input"], dict):
                case_input = CaseInput(**raw["input"])
            else:
                case_input = CaseInput(
                    prompt=raw.get("prompt", raw.get("input", "")),
                    language=raw.get("language", "en"),
                    system=raw.get("system"),
                    metadata=raw.get("metadata", {}),
                )

            if "expectations" in raw and isinstance(raw["expectations"], dict):
                expectations = CaseExpectations(**raw["expectations"])
            else:
                expectations = CaseExpectations(
                    expected_refusal=raw.get("expected_refusal"),
                    expected_tools=raw.get("expected_tools"),
                    required_citations=raw.get("required_citations"),
                    gold_doc_ids=raw.get("gold_doc_ids"),
                    output_schema=raw.get("output_schema"),
                    notes=raw.get("notes"),
                )

            cases.append(
                Case(
                    id=raw.get("id", f"{suite_name}_{len(cases):03d}"),
                    suite=suite_name,
                    category=raw.get("category", "general"),
                    input=case_input,
                    expectations=expectations,
                )
            )
    return cases


def _generate_run_id() -> str:
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%d_%H%M%S")
    h = hashlib.sha256(ts.encode()).hexdigest()[:8]
    return f"{ts}_{h}"


def resolve_adapter(adapter_name: str, mode: str) -> BaseAdapter:
    """Resolve adapter by explicit name.

    MODE controls *scoring* (offline = deterministic only, online = + judge).
    The adapter controls *execution* (where traces come from).

    Defaults:
      - MODE=offline + no explicit adapter -> offline_stub
      - MODE=online  + no explicit adapter -> anthropic
    """
    # Apply defaults when caller passes legacy "offline" name or empty string
    if adapter_name in ("offline", ""):
        adapter_name = "offline_stub" if mode == "offline" else "anthropic"

    if adapter_name == "offline_stub":
        from evalkit.adapters.offline_stub import OfflineStubAdapter
        return OfflineStubAdapter()

    if adapter_name == "http":
        from evalkit.adapters.http_app import HttpAppAdapter
        return HttpAppAdapter()

    if adapter_name == "anthropic":
        from evalkit.adapters.anthropic_messages import AnthropicMessagesAdapter
        return AnthropicMessagesAdapter()

    # Unknown adapter name — fall back to stub with a warning
    logger.warning(f"Unknown adapter '{adapter_name}', falling back to offline_stub")
    from evalkit.adapters.offline_stub import OfflineStubAdapter
    return OfflineStubAdapter()


async def _run_single(
    case: Case,
    adapter: BaseAdapter,
    run_id: str,
    mode: str,
) -> tuple[Trace, Score]:
    trace = await adapter.run_case(case, run_id)
    score = score_case(case, trace, mode)
    return trace, score


async def execute_run(
    suite_path: str,
    mode: str = "offline",
    adapter_name: str = "offline",
    max_cases: int = 0,
    concurrency: int = 4,
) -> RunSummary:
    """Execute a full evaluation run."""
    cases = load_suite(suite_path)
    if max_cases > 0:
        cases = cases[:max_cases]

    run_id = _generate_run_id()
    adapter = resolve_adapter(adapter_name, mode)

    logger.info(f"Run {run_id}: mode={mode}, adapter={adapter.name}, cases={len(cases)}")

    sem = asyncio.Semaphore(concurrency)
    results: list[tuple[Trace, Score]] = []

    async def bounded(case: Case):
        async with sem:
            return await _run_single(case, adapter, run_id, mode)

    tasks = [bounded(c) for c in cases]
    results = await asyncio.gather(*tasks)

    # Write artifacts
    run_dir = settings.runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Manifest
    manifest = {
        "run_id": run_id,
        "suite": suite_path,
        "mode": mode,
        "adapter": adapter.name,
        "max_cases": max_cases,
        "concurrency": concurrency,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # Results JSONL
    with open(run_dir / "results.jsonl", "w", encoding="utf-8") as f:
        for trace, score in results:
            f.write(json.dumps({
                "trace": trace.model_dump(mode="json"),
                "score": score.model_dump(mode="json"),
            }, ensure_ascii=False, default=str) + "\n")

    # Summary
    traces = [t for t, _ in results]
    scores = [s for _, s in results]
    summary = aggregate_results(run_id, suite_path, mode, scores, traces)

    (run_dir / "summary.json").write_text(
        json.dumps(summary.model_dump(mode="json"), indent=2, ensure_ascii=False, default=str)
    )

    logger.info(f"Artifacts written to {run_dir}")
    return summary
