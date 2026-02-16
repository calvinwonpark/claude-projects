from server.rag.retriever import RetrievedDoc, Retriever


def test_filter_by_threshold():
    retriever = Retriever.__new__(Retriever)
    retriever._threshold = 0.5
    docs = [
        RetrievedDoc(
            doc_id=1,
            title="A",
            source="a.md",
            chunk_index=0,
            content_snippet="text",
            score=0.9,
            doc_type="policy",
        ),
        RetrievedDoc(
            doc_id=2,
            title="B",
            source="b.md",
            chunk_index=0,
            content_snippet="text",
            score=0.2,
            doc_type="policy",
        ),
    ]
    filtered = Retriever.filter_by_threshold(retriever, docs)
    assert [doc.doc_id for doc in filtered] == [1]
