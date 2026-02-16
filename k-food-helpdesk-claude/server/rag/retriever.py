import os
import re
from dataclasses import dataclass
from typing import Any

import psycopg2
import psycopg2.extras

from server.cache import LruTtlCache
from server.providers.embeddings import EmbeddingsProvider


@dataclass
class RetrievedDoc:
    doc_id: int
    title: str
    source: str
    chunk_index: int
    content_snippet: str
    score: float
    doc_type: str


class Retriever:
    """Deterministic retrieval: query embed -> pgvector top-k -> threshold filter."""

    def __init__(
        self,
        embeddings: EmbeddingsProvider,
        *,
        threshold: float | None = None,
    ) -> None:
        self._embeddings = embeddings
        self._threshold = threshold if threshold is not None else float(os.getenv("RAG_THRESHOLD", "0.45"))
        self._fallback_floor = float(os.getenv("RAG_FALLBACK_FLOOR", "0.15"))
        self._fallback_min_docs = int(os.getenv("RAG_FALLBACK_MIN_DOCS", "1"))
        self._lexical_fallback_enabled = os.getenv("RAG_ENABLE_LEXICAL_FALLBACK", "true").lower() == "true"
        self._embedding_cache = LruTtlCache[str, list[float]](
            max_size=int(os.getenv("EMBEDDING_CACHE_SIZE", "2048")),
            ttl_seconds=int(os.getenv("EMBEDDING_CACHE_TTL_SECONDS", str(60 * 60 * 24))),
        )
        self._retrieval_cache = LruTtlCache[str, list[RetrievedDoc]](
            max_size=int(os.getenv("RETRIEVAL_CACHE_SIZE", "2048")),
            ttl_seconds=int(os.getenv("RETRIEVAL_CACHE_TTL_SECONDS", str(60 * 10))),
        )
        self._pg = {
            "host": os.getenv("PGHOST", "db"),
            "port": int(os.getenv("PGPORT", "5432")),
            "dbname": os.getenv("PGDATABASE", "helpdesk"),
            "user": os.getenv("PGUSER", "postgres"),
            "password": os.getenv("PGPASSWORD", "postgres"),
        }

    def _conn(self):
        return psycopg2.connect(**self._pg)

    @staticmethod
    def _normalize_query(text: str) -> str:
        return " ".join((text or "").strip().lower().split())

    @staticmethod
    def _cache_key(query: str, k: int, doc_type: str | None) -> str:
        return f"q={query}|k={k}|doc_type={doc_type or 'all'}"

    def embed_query(self, text: str) -> list[float]:
        normalized = self._normalize_query(text)
        cached = self._embedding_cache.get(normalized)
        if cached is not None:
            return cached
        vector = self._embeddings.embed_text(text)
        self._embedding_cache.set(normalized, vector)
        return vector

    def retrieve_top_k(
        self,
        vector: list[float],
        k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievedDoc]:
        filters = filters or {}
        doc_type = filters.get("doc_type")
        vec_str = "[" + ",".join(str(v) for v in vector) + "]"

        base_sql = """
            SELECT
                id,
                title,
                source,
                chunk_index,
                content,
                doc_type,
                1 - (embedding <=> %s::vector) AS score
            FROM docs
        """
        params: list[Any] = [vec_str]
        if doc_type:
            base_sql += " WHERE doc_type = %s "
            params.append(doc_type)
        base_sql += " ORDER BY embedding <=> %s::vector LIMIT %s "
        params.extend([vec_str, k])

        with self._conn() as con, con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(base_sql, params)
            rows = cur.fetchall()

        docs = [
            RetrievedDoc(
                doc_id=row["id"],
                title=row["title"],
                source=row["source"],
                chunk_index=row["chunk_index"],
                content_snippet=row["content"],
                score=float(row["score"]),
                doc_type=row["doc_type"],
            )
            for row in rows
        ]
        filtered = self.filter_by_threshold(docs)
        # Keep thresholding as primary behavior, but avoid empty context on obvious matches.
        if filtered:
            return filtered
        if self._fallback_min_docs > 0:
            fallback = [d for d in docs if d.score >= self._fallback_floor][: self._fallback_min_docs]
            if fallback:
                return fallback
        return []

    def retrieve_top_k_from_text(
        self,
        query_text: str,
        k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievedDoc]:
        filters = filters or {}
        doc_type = filters.get("doc_type")
        cache_key = self._cache_key(self._normalize_query(query_text), k, doc_type)
        cached = self._retrieval_cache.get(cache_key)
        if cached is not None:
            return cached

        vector = self.embed_query(query_text)
        docs = self.retrieve_top_k(vector, k=k, filters=filters)
        if docs:
            self._retrieval_cache.set(cache_key, docs)
            return docs
        if not self._lexical_fallback_enabled:
            self._retrieval_cache.set(cache_key, [])
            return []
        lexical = self._retrieve_lexical(query_text=query_text, k=max(k, self._fallback_min_docs), filters=filters)
        self._retrieval_cache.set(cache_key, lexical)
        return lexical

    def _retrieve_lexical(
        self,
        *,
        query_text: str,
        k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievedDoc]:
        filters = filters or {}
        doc_type = filters.get("doc_type")
        terms = [t.lower() for t in re.findall(r"[a-zA-Z0-9_]+", query_text) if len(t) >= 3]
        if not terms:
            return []

        like_terms = [f"%{t}%" for t in terms]
        sql = """
            SELECT
                id, title, source, chunk_index, content, doc_type
            FROM docs
            WHERE (
                lower(title) LIKE ANY(%s)
                OR lower(source) LIKE ANY(%s)
                OR lower(content) LIKE ANY(%s)
            )
        """
        params: list[Any] = [like_terms, like_terms, like_terms]
        if doc_type:
            sql += " AND doc_type = %s "
            params.append(doc_type)
        sql += " ORDER BY id ASC LIMIT %s "
        params.append(k)

        with self._conn() as con, con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        return [
            RetrievedDoc(
                doc_id=row["id"],
                title=row["title"],
                source=row["source"],
                chunk_index=row["chunk_index"],
                content_snippet=row["content"],
                score=self._fallback_floor,
                doc_type=row["doc_type"],
            )
            for row in rows
        ]

    def filter_by_threshold(self, docs: list[RetrievedDoc]) -> list[RetrievedDoc]:
        return [doc for doc in docs if doc.score >= self._threshold]

    def cache_stats(self) -> dict[str, Any]:
        return {
            "embedding_cache": self._embedding_cache.stats(),
            "retrieval_cache": self._retrieval_cache.stats(),
        }
