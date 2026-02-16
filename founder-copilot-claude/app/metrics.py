from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass
class MetricEvent:
    total_ms: float
    retrieval_ms: float
    llm_ms: float
    tokens_in: int
    tokens_out: int
    error: bool


class MetricsTracker:
    def __init__(self) -> None:
        self.events = deque(maxlen=5000)
        self.request_count = 0
        self.embedding_cache_hits = 0
        self.embedding_cache_misses = 0
        self.query_embedding_cache_hits = 0
        self.query_embedding_cache_misses = 0
        self.query_embedding_cache_evictions = 0
        self.query_embedding_cache_expirations = 0
        self.retrieval_cache_hits = 0
        self.retrieval_cache_misses = 0
        self.retrieval_cache_evictions = 0
        self.retrieval_cache_expirations = 0

    def record(
        self,
        *,
        total_ms: float,
        retrieval_ms: float,
        llm_ms: float,
        tokens_in: int = 0,
        tokens_out: int = 0,
        error: bool = False,
    ) -> None:
        self.request_count += 1
        self.events.append(
            MetricEvent(
                total_ms=total_ms,
                retrieval_ms=retrieval_ms,
                llm_ms=llm_ms,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                error=error,
            )
        )

    @staticmethod
    def _percentile(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        arr = sorted(values)
        idx = min(int(len(arr) * p), len(arr) - 1)
        return round(arr[idx], 2)

    def _cache_rate(self, hits: int, misses: int) -> float:
        total = hits + misses
        return round(hits / total, 4) if total else 0.0

    def stats(self) -> dict[str, Any]:
        totals = [e.total_ms for e in self.events]
        retrievals = [e.retrieval_ms for e in self.events]
        llms = [e.llm_ms for e in self.events]
        return {
            "request_count": self.request_count,
            "latency_ms": {
                "overall_p50": self._percentile(totals, 0.5),
                "overall_p95": self._percentile(totals, 0.95),
                "retrieval_p50": self._percentile(retrievals, 0.5),
                "retrieval_p95": self._percentile(retrievals, 0.95),
                "llm_p50": self._percentile(llms, 0.5),
                "llm_p95": self._percentile(llms, 0.95),
            },
            "tokens": {
                "input": sum(e.tokens_in for e in self.events),
                "output": sum(e.tokens_out for e in self.events),
            },
            "cache_hit_rates": {
                "embedding": self._cache_rate(self.embedding_cache_hits, self.embedding_cache_misses),
                "query_embedding": self._cache_rate(self.query_embedding_cache_hits, self.query_embedding_cache_misses),
                "retrieval": self._cache_rate(self.retrieval_cache_hits, self.retrieval_cache_misses),
            },
            "cache_counters": {
                "embedding_cache_hits": self.embedding_cache_hits,
                "embedding_cache_misses": self.embedding_cache_misses,
                "query_embedding_cache_hits": self.query_embedding_cache_hits,
                "query_embedding_cache_misses": self.query_embedding_cache_misses,
                "query_embedding_cache_evictions": self.query_embedding_cache_evictions,
                "query_embedding_cache_expirations": self.query_embedding_cache_expirations,
                "retrieval_cache_hits": self.retrieval_cache_hits,
                "retrieval_cache_misses": self.retrieval_cache_misses,
                "retrieval_cache_evictions": self.retrieval_cache_evictions,
                "retrieval_cache_expirations": self.retrieval_cache_expirations,
            },
            "errors": sum(1 for e in self.events if e.error),
        }


metrics = MetricsTracker()
