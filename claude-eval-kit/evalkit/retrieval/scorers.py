"""Retrieval quality scorers: recall@k, MRR, hit rate."""

from __future__ import annotations

from evalkit.types import Trace


def recall_at_k(trace: Trace, gold_ids: list[str]) -> float:
    """Fraction of gold_doc_ids found in trace.retrieval.selected."""
    if not gold_ids:
        return 1.0  # no expectation — vacuously correct
    selected = set(trace.retrieval.selected)
    hits = sum(1 for g in gold_ids if g in selected)
    return hits / len(gold_ids)


def mrr(trace: Trace, gold_ids: list[str]) -> float:
    """Mean Reciprocal Rank of first gold hit in selected list."""
    if not gold_ids:
        return 1.0
    gold_set = set(gold_ids)
    for rank, doc_id in enumerate(trace.retrieval.selected, start=1):
        if doc_id in gold_set:
            return 1.0 / rank
    return 0.0


def retrieval_hit_rate(trace: Trace) -> float:
    """1.0 if any doc was retrieved, 0.0 otherwise."""
    return 1.0 if trace.retrieval.selected else 0.0
