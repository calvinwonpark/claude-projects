from server.rag.context_builder import build_retrieval_context
from server.rag.retriever import RetrievedDoc


def test_build_retrieval_context_respects_budget():
    docs = [
        RetrievedDoc(
            doc_id=1,
            title="Refund Policy",
            source="refund_policy.md",
            chunk_index=0,
            content_snippet="a" * 300,
            score=0.9,
            doc_type="policy",
        ),
        RetrievedDoc(
            doc_id=2,
            title="Delivery Areas",
            source="delivery_areas.md",
            chunk_index=0,
            content_snippet="b" * 300,
            score=0.8,
            doc_type="policy",
        ),
    ]

    result = build_retrieval_context(docs, max_chars=350, snippet_chars=250)
    assert len(result.included_docs) == 1
    assert result.included_docs[0].doc_id == 1
