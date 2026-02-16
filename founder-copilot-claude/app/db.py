import json
import os
import re
from contextlib import contextmanager
from typing import Any, Iterable

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_POOL: ConnectionPool | None = None


def _dsn() -> str:
    return (
        f"host={os.getenv('PGHOST','db')} "
        f"port={os.getenv('PGPORT','5432')} "
        f"dbname={os.getenv('PGDATABASE','copilot')} "
        f"user={os.getenv('PGUSER','postgres')} "
        f"password={os.getenv('PGPASSWORD','postgres')}"
    )


def pool() -> ConnectionPool:
    global _POOL
    if _POOL is None:
        _POOL = ConnectionPool(conninfo=_dsn(), min_size=1, max_size=10, kwargs={"autocommit": True})
    return _POOL


@contextmanager
def conn_cursor():
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            yield cur


def execute(sql: str, params: tuple | list | None = None) -> None:
    with conn_cursor() as cur:
        cur.execute(sql, params or ())


def query_all(sql: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
    with conn_cursor() as cur:
        cur.execute(sql, params or ())
        return list(cur.fetchall())


def query_one(sql: str, params: tuple | list | None = None) -> dict[str, Any] | None:
    rows = query_all(sql, params)
    return rows[0] if rows else None


def vector_to_pg(embedding: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"


def insert_document(
    *,
    doc_id: str,
    source: str,
    title: str,
    chunk_index: int,
    content: str,
    content_hash: str,
    embedding: list[float],
    metadata: dict[str, Any],
) -> None:
    execute(
        """
        INSERT INTO documents (doc_id, source, title, chunk_index, content, content_hash, embedding, metadata)
        VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s::jsonb)
        """,
        (
            doc_id,
            source,
            title,
            chunk_index,
            content,
            content_hash,
            vector_to_pg(embedding),
            json.dumps(metadata, ensure_ascii=False),
        ),
    )


def document_exists_by_hash(content_hash: str) -> bool:
    row = query_one("SELECT 1 AS ok FROM documents WHERE content_hash=%s LIMIT 1", (content_hash,))
    return bool(row)


def search_similar(query_embedding: list[float], top_k: int, min_score: float) -> list[dict[str, Any]]:
    vec = vector_to_pg(query_embedding)
    return query_all(
        """
        SELECT
          doc_id, source, title, chunk_index, content, metadata,
          1 - (embedding <=> %s::vector) AS score
        FROM documents
        WHERE 1 - (embedding <=> %s::vector) >= %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (vec, vec, min_score, vec, top_k),
    )


def search_topk_no_threshold(query_embedding: list[float], top_k: int) -> list[dict[str, Any]]:
    vec = vector_to_pg(query_embedding)
    return query_all(
        """
        SELECT
          doc_id, source, title, chunk_index, content, metadata,
          1 - (embedding <=> %s::vector) AS score
        FROM documents
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (vec, vec, top_k),
    )


def lexical_search(query: str, top_k: int) -> list[dict[str, Any]]:
    q = (query or "").lower()
    tokens = [t for t in re.findall(r"[a-z0-9_]+", q) if len(t) >= 3][:10]
    if not tokens:
        tokens = [q] if q else []
    if not tokens:
        return []

    where_parts = []
    params: list[Any] = []
    for t in tokens:
        like = f"%{t}%"
        where_parts.append("(lower(title) LIKE %s OR lower(source) LIKE %s OR lower(content) LIKE %s)")
        params.extend([like, like, like])
    where_sql = " OR ".join(where_parts)
    params.append(top_k)
    sql = f"""
        SELECT
          doc_id, source, title, chunk_index, content, metadata, 0.0 AS score
        FROM documents
        WHERE {where_sql}
        LIMIT %s
    """
    return query_all(sql, tuple(params))


def insert_audit(row: dict[str, Any]) -> None:
    execute(
        """
        INSERT INTO audit_logs (
          session_id, user_id, endpoint, model, selected_agent, embedding_provider,
          retrieved_doc_ids, cited_doc_ids, latency_ms, tokens_in, tokens_out, request_id, prompt_hash,
          tool_calls, tool_results
        ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
        """,
        (
            row.get("session_id"),
            row.get("user_id"),
            row.get("endpoint"),
            row.get("model"),
            row.get("selected_agent"),
            row.get("embedding_provider", "unknown"),
            json.dumps(row.get("retrieved_doc_ids", [])),
            json.dumps(row.get("cited_doc_ids", [])),
            row.get("latency_ms", 0.0),
            row.get("tokens_in"),
            row.get("tokens_out"),
            row.get("request_id"),
            row.get("prompt_hash"),
            json.dumps(row.get("tool_calls", [])),
            json.dumps(row.get("tool_results", [])),
        ),
    )


def recent_audit(limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 200))
    return query_all(
        """
        SELECT
          id, timestamp, session_id, user_id, endpoint, model, selected_agent, embedding_provider,
          retrieved_doc_ids, cited_doc_ids, latency_ms, tokens_in, tokens_out, request_id, prompt_hash,
          tool_calls, tool_results
        FROM audit_logs
        ORDER BY id DESC
        LIMIT %s
        """,
        (safe_limit,),
    )


def ensure_schema() -> None:
    execute("CREATE EXTENSION IF NOT EXISTS vector")
    execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
          id BIGSERIAL PRIMARY KEY,
          doc_id TEXT NOT NULL,
          source TEXT NOT NULL,
          title TEXT NOT NULL,
          chunk_index INT NOT NULL,
          content TEXT NOT NULL,
          content_hash TEXT NOT NULL,
          embedding VECTOR(1536) NOT NULL,
          metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    execute("CREATE INDEX IF NOT EXISTS documents_doc_id_idx ON documents (doc_id)")
    execute("CREATE INDEX IF NOT EXISTS documents_source_idx ON documents (source)")
    execute("CREATE INDEX IF NOT EXISTS documents_content_hash_idx ON documents (content_hash)")
    execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
          id BIGSERIAL PRIMARY KEY,
          timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          session_id TEXT NOT NULL,
          user_id TEXT,
          endpoint TEXT NOT NULL,
          model TEXT,
          selected_agent TEXT,
          embedding_provider TEXT NOT NULL DEFAULT 'unknown',
          retrieved_doc_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
          cited_doc_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
          latency_ms DOUBLE PRECISION NOT NULL,
          tokens_in INT,
          tokens_out INT,
          request_id TEXT,
          prompt_hash TEXT,
          tool_calls JSONB NOT NULL DEFAULT '[]'::jsonb,
          tool_results JSONB NOT NULL DEFAULT '[]'::jsonb
        )
        """
    )
    execute("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS tool_calls JSONB NOT NULL DEFAULT '[]'::jsonb")
    execute("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS tool_results JSONB NOT NULL DEFAULT '[]'::jsonb")
    execute("CREATE INDEX IF NOT EXISTS audit_logs_ts_idx ON audit_logs (timestamp DESC)")
