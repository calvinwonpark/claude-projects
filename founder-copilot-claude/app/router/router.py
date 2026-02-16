from typing import Any
import re

from app.config import settings
from app.router.strategies import AgentCandidate, consult_then_decide, ensemble_vote, winner_take_all

TECH_KEYWORDS = {"architecture", "api", "infra", "scalability", "backend", "ml", "llm", "security"}
MARKETING_KEYWORDS = {"marketing", "growth", "acquisition", "seo", "copy", "campaign", "channel"}
INVESTOR_KEYWORDS = {"fundraising", "investor", "deck", "valuation", "runway", "kpi", "arr", "mrr"}


def _score(query: str, words: set[str]) -> int:
    lower = query.lower()
    score = 0
    for w in words:
        kw = w.lower().strip()
        if not kw:
            continue
        if " " in kw:
            # Phrase-style keywords still use substring semantics.
            if kw in lower:
                score += 1
            continue
        # Single-token keywords should match on token boundaries only.
        if re.search(rf"\b{re.escape(kw)}\b", lower):
            score += 1
    return score


def _build_candidates(query: str) -> list[AgentCandidate]:
    scores = {
        "tech": _score(query, TECH_KEYWORDS),
        "marketing": _score(query, MARKETING_KEYWORDS),
        "investor": _score(query, INVESTOR_KEYWORDS),
    }
    total = max(sum(scores.values()), 1)
    return [AgentCandidate(label=label, confidence=score / total) for label, score in scores.items()]


def route_query(query: str) -> dict[str, Any]:
    candidates = _build_candidates(query)
    ranked = sorted(candidates, key=lambda c: c.confidence, reverse=True)
    max_conf = ranked[0].confidence if ranked else 0.0
    second_conf = ranked[1].confidence if len(ranked) > 1 else 0.0
    gap = max_conf - second_conf

    strategy = settings.router.strategy
    selection_reason = "explicit override"
    if strategy == "auto":
        if max_conf >= settings.router.auto_high_conf and gap >= settings.router.auto_gap:
            strategy = "winner_take_all"
            selection_reason = "high confidence gap"
        elif max_conf >= settings.router.auto_mid_conf:
            strategy = "consult_then_decide"
            selection_reason = "medium confidence ambiguity"
        else:
            strategy = "ensemble_vote"
            selection_reason = "ambiguous query"

    if strategy == "consult_then_decide":
        trace = consult_then_decide(candidates)
    elif strategy == "ensemble_vote":
        trace = ensemble_vote(candidates)
    else:
        trace = winner_take_all(candidates)
    trace["strategy"] = strategy
    trace["strategy_selected"] = strategy
    trace["selection_reason"] = selection_reason
    trace["tool_calls_made"] = []
    trace["citations_used"] = []
    trace["latency_ms_breakdown"] = {"routing": trace.get("latency_ms", 0.0)}
    return trace
