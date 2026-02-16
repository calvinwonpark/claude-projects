from app.storage import append_audit_log


def test_append_audit_log_calls_db(monkeypatch):
    called = {}

    def fake_insert(row):
        called["row"] = row

    monkeypatch.setattr("app.db.insert_audit", fake_insert)

    row = {
        "session_id": "s1",
        "endpoint": "/chat",
        "model": "claude-3-5-sonnet-latest",
        "selected_agent": "tech",
        "retrieved_doc_ids": ["tech/api_design.md"],
        "cited_doc_ids": ["tech/api_design.md"],
        "latency_ms": 10.1,
    }
    append_audit_log(row)
    assert called["row"]["session_id"] == "s1"
