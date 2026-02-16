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
