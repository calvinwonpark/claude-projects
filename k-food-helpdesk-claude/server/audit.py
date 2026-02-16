import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any

import psycopg2
import psycopg2.extras


@dataclass
class AuditRecord:
    session_id: str
    user_id: str | None
    endpoint: str
    model: str | None
    embedding_provider: str
    retrieved_doc_ids: list[int]
    cited_doc_ids: list[int]
    latency_ms: float
    tokens_in: int | None
    tokens_out: int | None
    prompt_hash: str


def _conn():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "db"),
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "helpdesk"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "postgres"),
    )


def build_prompt_hash(system_prompt: str, context_text: str, user_message: str) -> str:
    payload = f"{system_prompt}\n---\n{context_text}\n---\n{user_message}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def insert_audit_log(record: AuditRecord) -> None:
    with _conn() as con, con.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_logs (
              session_id, user_id, endpoint, model, embedding_provider,
              retrieved_doc_ids, cited_doc_ids, latency_ms, tokens_in, tokens_out, prompt_hash
            )
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s)
            """,
            (
                record.session_id,
                record.user_id,
                record.endpoint,
                record.model,
                record.embedding_provider,
                json.dumps(record.retrieved_doc_ids),
                json.dumps(record.cited_doc_ids),
                record.latency_ms,
                record.tokens_in,
                record.tokens_out,
                record.prompt_hash,
            ),
        )
        con.commit()


def get_recent_audit_logs(limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 200))
    with _conn() as con, con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
              id, timestamp, session_id, user_id, endpoint, model, embedding_provider,
              retrieved_doc_ids, cited_doc_ids, latency_ms, tokens_in, tokens_out, prompt_hash
            FROM audit_logs
            ORDER BY id DESC
            LIMIT %s
            """,
            (safe_limit,),
        )
        return [dict(row) for row in cur.fetchall()]
