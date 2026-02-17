from collections import deque
from dataclasses import dataclass


@dataclass
class TurnMetric:
    stt_latency_ms: float
    llm_latency_ms: float
    tts_latency_ms: float
    e2e_latency_ms: float


class MetricsTracker:
    def __init__(self) -> None:
        self.turns = deque(maxlen=5000)
        self.tool_calls_total = 0
        self.tool_failures_total = 0
        self.transcripts_low_confidence_total = 0

    @staticmethod
    def _percentile(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        arr = sorted(values)
        idx = min(int(len(arr) * p), len(arr) - 1)
        return round(arr[idx], 2)

    def record_turn(self, *, stt_latency_ms: float, llm_latency_ms: float, tts_latency_ms: float, e2e_latency_ms: float) -> None:
        self.turns.append(
            TurnMetric(
                stt_latency_ms=stt_latency_ms,
                llm_latency_ms=llm_latency_ms,
                tts_latency_ms=tts_latency_ms,
                e2e_latency_ms=e2e_latency_ms,
            )
        )

    def as_dict(self, active_sessions: int) -> dict:
        stt = [t.stt_latency_ms for t in self.turns]
        llm = [t.llm_latency_ms for t in self.turns]
        tts = [t.tts_latency_ms for t in self.turns]
        e2e = [t.e2e_latency_ms for t in self.turns]
        return {
            "stt_latency_ms": {"p50": self._percentile(stt, 0.5), "p95": self._percentile(stt, 0.95)},
            "llm_latency_ms": {"p50": self._percentile(llm, 0.5), "p95": self._percentile(llm, 0.95)},
            "tts_latency_ms": {"p50": self._percentile(tts, 0.5), "p95": self._percentile(tts, 0.95)},
            "end_to_end_turn_latency_ms": {"p50": self._percentile(e2e, 0.5), "p95": self._percentile(e2e, 0.95)},
            "tool_calls_total": self.tool_calls_total,
            "tool_failures_total": self.tool_failures_total,
            "transcripts_low_confidence_total": self.transcripts_low_confidence_total,
            "active_sessions": active_sessions,
        }


metrics = MetricsTracker()
