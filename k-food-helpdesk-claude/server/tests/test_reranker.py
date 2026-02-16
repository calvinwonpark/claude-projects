from server.rag.reranker import heuristic_rerank
from server.rag.retriever import RetrievedDoc


def test_heuristic_rerank_boosts_title_keyword():
    docs = [
        RetrievedDoc(
            doc_id=1,
            title="General Account Help",
            source="account_help.md",
            chunk_index=0,
            content_snippet="...",
            score=0.7,
            doc_type="policy",
        ),
        RetrievedDoc(
            doc_id=5,
            title="Refund Policy",
            source="refund_policy.md",
            chunk_index=0,
            content_snippet="...",
            score=0.68,
            doc_type="policy",
        ),
    ]
    reranked = heuristic_rerank("what is the refund policy", docs, top_n=2)
    assert reranked[0].doc_id == 5
