from server.audit import AuditRecord, insert_audit_log


class FakeCursor:
    def __init__(self):
        self.executed = None

    def execute(self, sql, params):
        self.executed = (sql, params)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class FakeConn:
    def __init__(self):
        self.cursor_obj = FakeCursor()
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def test_insert_audit_log_writes_row(monkeypatch):
    fake_conn = FakeConn()
    monkeypatch.setattr("server.audit._conn", lambda: fake_conn)

    insert_audit_log(
        AuditRecord(
            session_id="s1",
            user_id="u1",
            endpoint="/chat",
            model="claude-3-5-sonnet-latest",
            embedding_provider="gemini",
            retrieved_doc_ids=[1, 2],
            cited_doc_ids=[2],
            latency_ms=123.4,
            tokens_in=10,
            tokens_out=20,
            prompt_hash="abc",
        )
    )

    assert fake_conn.cursor_obj.executed is not None
    assert fake_conn.committed is True
