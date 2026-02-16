import json
import re
import time
from dataclasses import dataclass
from typing import Any

from app import db
from app.config import settings
from app.metrics import metrics
from app.providers.embeddings import EmbeddingsProvider


@dataclass
class RetrievedDoc:
    doc_id: str
    title: str
    source: str
    chunk_index: int
    content: str
    score: float


class Retriever:
    def __init__(self, embeddings: EmbeddingsProvider) -> None:
        self.embeddings = embeddings
        self._retrieval_cache: dict[str, tuple[float, list[RetrievedDoc]]] = {}
        self._query_embedding_cache: dict[str, tuple[float, list[float]]] = {}

    @staticmethod
    def _now() -> float:
        return time.time()

    @staticmethod
    def _norm(text: str) -> str:
        return " ".join((text or "").lower().split())

    def _embed_query_cached(self, text: str) -> list[float]:
        key = self._norm(text)
        ttl = 86400
        max_size = 3000
        hit = self._query_embedding_cache.get(key)
        if hit and hit[0] > self._now():
            metrics.embedding_cache_hits += 1
            return hit[1]
        metrics.embedding_cache_misses += 1
        vec = self.embeddings.embed_text(text)
        self._query_embedding_cache[key] = (self._now() + ttl, vec)
        if len(self._query_embedding_cache) > max_size:
            oldest = next(iter(self._query_embedding_cache))
            self._query_embedding_cache.pop(oldest, None)
        return vec

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        n = min(len(a), len(b))
        if n == 0:
            return 0.0
        dot = sum(a[i] * b[i] for i in range(n))
        na = sum(a[i] * a[i] for i in range(n)) ** 0.5
        nb = sum(b[i] * b[i] for i in range(n)) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def retrieve(self, query: str, top_k: int = 6) -> tuple[list[RetrievedDoc], float]:
        started = self._now()
        key = f"{self._norm(query)}|k={top_k}|min={settings.retrieval.min_score}"
        ttl = 600
        max_size = 5000
        hit = self._retrieval_cache.get(key)
        if hit and hit[0] > self._now():
            metrics.retrieval_cache_hits += 1
            return hit[1], round((self._now() - started) * 1000, 2)
        metrics.retrieval_cache_misses += 1
        qv = self._embed_query_cached(query)
        min_score = settings.retrieval.min_score
        rows = db.search_similar(qv, top_k=top_k, min_score=min_score)
        out = [
            RetrievedDoc(
                doc_id=str(r["doc_id"]),
                title=str(r["title"]),
                source=str(r["source"]),
                chunk_index=int(r["chunk_index"]),
                content=str(r["content"]),
                score=float(r["score"]),
            )
            for r in rows
        ]
        if not out and settings.retrieval.lexical_fallback:
            lrows = db.lexical_search(query, top_k=top_k)
            out = [
                RetrievedDoc(
                    doc_id=str(r["doc_id"]),
                    title=str(r["title"]),
                    source=str(r["source"]),
                    chunk_index=int(r["chunk_index"]),
                    content=str(r["content"]),
                    score=0.05,
                )
                for r in lrows
            ]
        if not out:
            fallback_rows = db.search_topk_no_threshold(qv, top_k=max(1, min(top_k, 3)))
            out = [
                RetrievedDoc(
                    doc_id=str(r["doc_id"]),
                    title=str(r["title"]),
                    source=str(r["source"]),
                    chunk_index=int(r["chunk_index"]),
                    content=str(r["content"]),
                    score=float(r["score"]),
                )
                for r in fallback_rows
            ]
        out = _rerank(query, out)[:top_k]
        self._retrieval_cache[key] = (self._now() + ttl, out)
        if len(self._retrieval_cache) > max_size:
            oldest = next(iter(self._retrieval_cache))
            self._retrieval_cache.pop(oldest, None)
        return out, round((self._now() - started) * 1000, 2)


def _rerank(query: str, docs: list[RetrievedDoc]) -> list[RetrievedDoc]:
    mode = settings.retrieval.rerank_mode
    if mode != "heuristic":
        return docs
    q = query.lower()
    terms = set(re.findall(r"[a-zA-Z0-9_]+", q))
    policy_like = any(t in q for t in ["policy", "refund", "investor", "kpi", "security", "pricing"])
    rescored = []
    for d in docs:
        boost = 0.0
        title_l = d.title.lower()
        for t in terms:
            if t in title_l:
                boost += 0.08
        if policy_like and any(t in d.source.lower() for t in ["investor", "tech", "marketing"]):
            boost += 0.05
        rescored.append(
            RetrievedDoc(
                doc_id=d.doc_id,
                title=d.title,
                source=d.source,
                chunk_index=d.chunk_index,
                content=d.content,
                score=d.score + boost,
            )
        )
    rescored.sort(key=lambda x: x.score, reverse=True)
    return rescored


def build_context(docs: list[RetrievedDoc], max_chars: int = 6000) -> str:
    items = []
    size = 0
    for d in docs:
        item = {
            "doc_id": d.doc_id,
            "title": d.title,
            "source": d.source,
            "chunk_index": d.chunk_index,
            "content": d.content[:700],
            "score": round(d.score, 6),
        }
        s = json.dumps(item, ensure_ascii=False)
        if size + len(s) > max_chars:
            break
        items.append(item)
        size += len(s)
    return json.dumps(items, ensure_ascii=False, indent=2)


CITATION_RE = re.compile(r"\[doc:([^\]\s]+)\]")


def validate_citations(answer: str, docs: list[RetrievedDoc]) -> list[str]:
    allowed = {d.doc_id for d in docs}
    found = CITATION_RE.findall(answer or "")
    kept: list[str] = []
    for doc_id in found:
        if doc_id in allowed and doc_id not in kept:
            kept.append(doc_id)
    return [f"doc:{x}" for x in kept]


def apply_citation_mode(answer: str, docs: list[RetrievedDoc], query: str) -> tuple[str, list[str], str]:
    citations = validate_citations(answer, docs)
    mode = settings.safety.citation_mode
    strict_claim_check = settings.safety.strict_claim_check
    uncited_claims = _has_uncited_factual_claims(answer) if strict_claim_check else False
    if citations and not uncited_claims:
        return answer, citations, "verified"
    if mode == "lenient":
        return f"[Unverified] {answer}".strip(), citations, "unverified"
    top = docs[0] if docs else None
    if top:
        msg = (
            "I do not have enough evidence in the retrieved sources to answer reliably. "
            f"Could you confirm if you want details from '{top.title}' ({top.source})?"
        )
    else:
        msg = (
            "I do not have enough evidence in retrieved sources to answer reliably. "
            "Could you clarify your request or provide a relevant document?"
        )
    return msg, [], "insufficient_evidence"


def _has_uncited_factual_claims(answer: str) -> bool:
    lines = [s.strip() for s in re.split(r"[\n\.!?]+", answer or "") if s.strip()]
    if not lines:
        return False
    factual = [
        line
        for line in lines
        if re.search(r"\b(should|must|kpi|arr|mrr|security|api|growth|fundraising|market|customer|retention)\b|\d", line, re.I)
    ]
    if not factual:
        return False
    cited = [line for line in factual if CITATION_RE.search(line)]
    if not cited:
        return True
    return ((len(factual) - len(cited)) / len(factual)) > 0.7
