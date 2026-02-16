import os
import re
from dataclasses import dataclass

from server.rag.retriever import RetrievedDoc

CITATION_RE = re.compile(r"\[doc:(\d+)\]")
ANY_CITATION_TOKEN_RE = re.compile(r"\[doc:[^\]]*\]")


@dataclass
class CitationAssessment:
    answer: str
    valid_citations: list[str]
    verified: bool
    reason: str | None


def _clean_citation_tokens(answer: str) -> str:
    return ANY_CITATION_TOKEN_RE.sub(
        lambda m: m.group(0) if CITATION_RE.fullmatch(m.group(0)) else "",
        answer or "",
    ).strip()


def _split_claim_lines(answer: str) -> list[str]:
    parts = re.split(r"[\n\.!?]+", answer)
    return [p.strip() for p in parts if p.strip()]


def _looks_factual(line: str) -> bool:
    if line.endswith("?"):
        return False
    factual_markers = re.compile(
        r"\b(refund|delivery|hours|fee|allergen|accept|process|district|policy|restaurant|within|days|minutes)\b|\d",
        re.IGNORECASE,
    )
    return bool(factual_markers.search(line))


def _has_uncited_claims(answer: str) -> bool:
    lines = _split_claim_lines(answer)
    factual_lines = [line for line in lines if _looks_factual(line)]
    if not factual_lines:
        return False
    cited_factual_lines = [line for line in factual_lines if CITATION_RE.search(line)]
    if len(cited_factual_lines) == 0:
        return True
    # Practical strictness: allow answers where citations are present but not repeated in every line.
    uncited_ratio = (len(factual_lines) - len(cited_factual_lines)) / len(factual_lines)
    return uncited_ratio > 0.7


def _strict_refusal(query: str, docs: list[RetrievedDoc]) -> str:
    if docs:
        top = docs[0]
        return (
            "I do not have enough evidence to provide a reliable answer from the retrieved sources. "
            f"Please confirm if you want information specifically from '{top.title}' ({top.source}), "
            f"or provide more details about your question: {query}"
        )
    return (
        "I do not have enough evidence in the retrieved sources to answer reliably. "
        "Please clarify your request or provide the policy/document you want me to use."
    )


def enforce_citation_policy(answer: str, docs: list[RetrievedDoc], user_query: str) -> CitationAssessment:
    """
    Enforce reliability policy.
    - strict (default): refuse if citations are missing/invalid or if factual lines are uncited
    - lenient: return as unverified when evidence is weak
    """
    mode = os.getenv("CITATION_MODE", "strict").lower()
    cleaned = _clean_citation_tokens(answer)
    allowed = {str(d.doc_id) for d in docs}
    found = CITATION_RE.findall(cleaned)
    valid_ids: list[str] = []
    for doc_id in found:
        if doc_id in allowed and doc_id not in valid_ids:
            valid_ids.append(doc_id)
    valid_citations = [f"doc:{doc_id}" for doc_id in valid_ids]

    missing_valid = len(valid_citations) == 0
    uncited_claims = _has_uncited_claims(cleaned)
    if mode == "strict" and (missing_valid or uncited_claims):
        return CitationAssessment(
            answer=_strict_refusal(user_query, docs),
            valid_citations=[],
            verified=False,
            reason="insufficient_evidence",
        )
    if mode == "lenient" and (missing_valid or uncited_claims):
        return CitationAssessment(
            answer=f"[Unverified] {cleaned}",
            valid_citations=valid_citations,
            verified=False,
            reason="unverified",
        )
    return CitationAssessment(answer=cleaned, valid_citations=valid_citations, verified=True, reason=None)
