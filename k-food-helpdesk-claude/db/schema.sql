CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS docs (
  id BIGSERIAL PRIMARY KEY,
  source TEXT NOT NULL,
  title TEXT NOT NULL,
  doc_type TEXT NOT NULL,
  chunk_index INT NOT NULL DEFAULT 0,
  content TEXT NOT NULL,
  embedding VECTOR(768) NOT NULL,
  meta JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS docs_embedding_idx
  ON docs USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

CREATE INDEX IF NOT EXISTS docs_doc_type_idx ON docs (doc_type);

CREATE TABLE IF NOT EXISTS audit_logs (
  id BIGSERIAL PRIMARY KEY,
  timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  session_id TEXT NOT NULL,
  user_id TEXT NULL,
  endpoint TEXT NOT NULL,
  model TEXT NULL,
  embedding_provider TEXT NOT NULL,
  retrieved_doc_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  cited_doc_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  latency_ms DOUBLE PRECISION NOT NULL,
  tokens_in INT NULL,
  tokens_out INT NULL,
  prompt_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS audit_logs_timestamp_idx ON audit_logs (timestamp DESC);
