from app.rag import RetrievedDoc, _rerank


def test_heuristic_rerank_boosts_title_keyword(monkeypatch):
    monkeypatch.setenv("RERANK_MODE", "heuristic")
    docs = [
        RetrievedDoc(
            doc_id="a",
            title="General Playbook",
            source="misc.md",
            chunk_index=0,
            content="generic",
            score=0.70,
        ),
        RetrievedDoc(
            doc_id="b",
            title="API Design Deep Dive",
            source="tech/api_design.md",
            chunk_index=0,
            content="api details",
            score=0.66,
        ),
    ]
    out = _rerank("api versioning strategy", docs)
    assert out[0].doc_id == "b"
