import os
import re
from dataclasses import replace

from server.rag.retriever import RetrievedDoc

POLICY_HINTS = {"refund", "cancel", "delivery", "fee", "policy", "hours", "allergen"}


def _keywords(query: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[a-zA-Z0-9_]+", query) if len(w) >= 3}


def heuristic_rerank(query: str, docs: list[RetrievedDoc], top_n: int = 6) -> list[RetrievedDoc]:
    words = _keywords(query)
    policy_like = any(h in words for h in POLICY_HINTS)
    ranked: list[tuple[float, RetrievedDoc]] = []
    for doc in docs:
        boost = 0.0
        title_l = doc.title.lower()
        source_l = doc.source.lower()
        for w in words:
            if w in title_l:
                boost += 0.12
            if w in source_l:
                boost += 0.08
        if policy_like and doc.doc_type == "policy":
            boost += 0.08
        ranked.append((doc.score + boost, replace(doc, score=doc.score + boost)))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [doc for _, doc in ranked[:top_n]]


def rerank_docs(query: str, docs: list[RetrievedDoc], mode: str | None = None) -> list[RetrievedDoc]:
    selected = (mode or os.getenv("RERANK_MODE", "heuristic")).lower()
    top_n = int(os.getenv("RERANK_TOP_N", "6"))
    if selected == "off":
        return docs[:top_n]
    if selected in {"heuristic", "llm"}:
        # llm mode currently falls back to deterministic heuristic to keep latency bounded.
        return heuristic_rerank(query, docs, top_n=top_n)
    return docs[:top_n]
