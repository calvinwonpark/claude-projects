"""Rough token estimation when exact counts are unavailable."""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Estimate token count using a simple character-based heuristic.

    Claude tokenization averages ~4 characters per token for English.
    This is intentionally a conservative approximation for cost estimation.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_cost(tokens_in: int, tokens_out: int, cost_per_1k_in: float, cost_per_1k_out: float) -> float:
    """Estimate USD cost from token counts and per-1K rates."""
    return (tokens_in / 1000.0) * cost_per_1k_in + (tokens_out / 1000.0) * cost_per_1k_out
