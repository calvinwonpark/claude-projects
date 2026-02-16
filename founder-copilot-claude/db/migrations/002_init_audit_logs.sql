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
);

CREATE INDEX IF NOT EXISTS audit_logs_ts_idx ON audit_logs (timestamp DESC);
