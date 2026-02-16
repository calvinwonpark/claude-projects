from server.rag.retriever import RetrievedDoc
from server.reliability.citations import enforce_citation_policy


def _docs():
    return [
        RetrievedDoc(
            doc_id=5,
            title="Refund Policy",
            source="refund_policy.md",
            chunk_index=0,
            content_snippet="Refund requests within 24 hours...",
            score=0.9,
            doc_type="policy",
        )
    ]


def test_citation_policy_strict_refuses_uncited(monkeypatch):
    monkeypatch.setenv("CITATION_MODE", "strict")
    assessed = enforce_citation_policy("Refunds are processed in 3-5 business days.", _docs(), "refund policy")
    assert assessed.verified is False
    assert assessed.reason == "insufficient_evidence"
    assert assessed.valid_citations == []


def test_citation_policy_lenient_marks_unverified(monkeypatch):
    monkeypatch.setenv("CITATION_MODE", "lenient")
    assessed = enforce_citation_policy("Refunds are processed in 3-5 business days.", _docs(), "refund policy")
    assert assessed.verified is False
    assert assessed.reason == "unverified"
    assert assessed.answer.startswith("[Unverified]")


def test_citation_policy_keeps_valid_ids(monkeypatch):
    monkeypatch.setenv("CITATION_MODE", "strict")
    assessed = enforce_citation_policy(
        "Refunds are processed in 3-5 business days [doc:5].",
        _docs(),
        "refund policy",
    )
    assert assessed.verified is True
    assert assessed.valid_citations == ["doc:5"]


def test_citation_policy_allows_partial_inline_citations(monkeypatch):
    monkeypatch.setenv("CITATION_MODE", "strict")
    assessed = enforce_citation_policy(
        "Refunds are accepted within 24 hours [doc:5]. "
        "Photo evidence may be required and processing takes 3-5 business days.",
        _docs(),
        "refund policy",
    )
    assert assessed.verified is True
    assert assessed.valid_citations == ["doc:5"]
